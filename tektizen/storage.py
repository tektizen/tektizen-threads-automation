"""JSON file storage: schema validation, atomic writes, and cross-process locking.

Rules this module enforces:

* A missing data file reads as an empty default document. It is only written
  to disk when something is actually stored (or by ``init_data``).
* A corrupted or schema-invalid file is never replaced by defaults. Reads raise
  ``DataError`` so the caller aborts instead of silently losing user data.
* Every write is validated against ``schemas/<name>.schema.json`` first, then
  written to a temp file in the same directory and swapped in with
  ``os.replace`` so readers never see a half-written file.
* ``transaction()`` holds an exclusive lock file for the read-modify-write
  cycle and skips the write when nothing changed (avoiding empty commits).

Within GitHub Actions, workflows that mutate data additionally share one
``concurrency`` group, so the lock here guards against overlap inside a job
and during local development.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

from jsonschema import Draft202012Validator, FormatChecker

from . import paths
from .util import utcnow_iso

SCHEMA_VERSION = 1
LOCK_TIMEOUT_SECONDS = 30.0
STALE_LOCK_SECONDS = 600.0


class DataError(Exception):
    """A data file is unreadable, corrupted, or fails schema validation."""


class LockTimeout(DataError):
    pass


def _collection(key: str = "items") -> Callable[[], dict[str, Any]]:
    return lambda: {"schema_version": SCHEMA_VERSION, "updated_at": None, key: []}


def _empty_memory() -> dict[str, Any]:
    from .memory import MEMORY_CATEGORIES  # local import: memory depends on storage

    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "categories": {c: [] for c in MEMORY_CATEGORIES},
        "history": [],
    }


def _default_settings() -> dict[str, Any]:
    from .settings import default_settings

    return default_settings()


DEFAULTS: dict[str, Callable[[], dict[str, Any]]] = {
    "settings": _default_settings,
    "content": _collection(),
    "ideas": _collection(),
    "approvals": _collection(),
    "publishing_history": _collection(),
    "performance": _collection(),
    "learning_memory": _empty_memory,
    "automation_runs": _collection(),
    "agent_metrics": lambda: {"schema_version": SCHEMA_VERSION, "updated_at": None, "agents": {}},
}

DATA_FILES = tuple(DEFAULTS)


def _check_name(name: str) -> None:
    if name not in DEFAULTS:
        raise ValueError(f"unknown data file: {name!r}")


def data_path(name: str) -> Path:
    _check_name(name)
    return paths.data_dir() / f"{name}.json"


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema_file = paths.schemas_dir() / f"{name}.schema.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validation_errors(name: str, doc: Any) -> list[str]:
    _check_name(name)
    errors = sorted(_validator(name).iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors[:20]]


def validate(name: str, doc: Any) -> None:
    errors = validation_errors(name, doc)
    if errors:
        raise DataError(f"{name}.json failed validation:\n  " + "\n  ".join(errors))


def _migrate(name: str, doc: dict[str, Any]) -> dict[str, Any]:
    version = doc.get("schema_version")
    if version == SCHEMA_VERSION:
        return doc
    if isinstance(version, int) and version > SCHEMA_VERSION:
        raise DataError(f"{name}.json has schema_version {version}; this engine supports {SCHEMA_VERSION}. Upgrade the engine.")
    # Future migrations go here, keyed by version. No older versions exist yet.
    raise DataError(f"{name}.json has unsupported schema_version {version!r}")


def load(name: str) -> dict[str, Any]:
    """Read and validate a data file. Missing file → default document (not written)."""
    path = data_path(name)
    if not path.exists():
        return DEFAULTS[name]()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataError(f"cannot read {path.name}: {exc}") from exc
    if not raw.strip():
        raise DataError(f"{path.name} is empty; restore it from git history or delete it to start fresh")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise DataError(f"{path.name} must contain a JSON object")
    doc = _migrate(name, doc)
    validate(name, doc)
    return doc


def serialize(doc: Any) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # os.replace can transiently fail on Windows when another process has the file open.
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def save(name: str, doc: dict[str, Any], *, touch: bool = True) -> bool:
    """Validate and atomically write. Returns False when the file content is unchanged.

    Prefer ``transaction()``; call ``save`` directly only while holding the lock.
    """
    path = data_path(name)
    candidate = copy.deepcopy(doc)
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if current is not None:
            # Compare ignoring updated_at so a no-op touch doesn't create a commit.
            a = {k: v for k, v in current.items() if k != "updated_at"} if isinstance(current, dict) else current
            b = {k: v for k, v in candidate.items() if k != "updated_at"}
            if a == b:
                return False
    if touch:
        candidate["updated_at"] = utcnow_iso()
    validate(name, candidate)
    _atomic_write_text(path, serialize(candidate))
    doc["updated_at"] = candidate["updated_at"]
    return True


@contextmanager
def file_lock(name: str, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    lock_dir = paths.data_dir() / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{name}.lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise LockTimeout(f"timed out waiting for lock on {name}.json")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


@contextmanager
def transaction(name: str) -> Iterator[dict[str, Any]]:
    """Locked read-modify-write. Mutate the yielded document in place.

    Nothing is written if the block raises, or if the document is unchanged.
    """
    with file_lock(name):
        doc = load(name)
        yield doc
        save(name, doc)


def init_data() -> list[str]:
    """Create any missing data files with empty defaults. Existing files are never touched."""
    created = []
    for name in DATA_FILES:
        path = data_path(name)
        if path.exists():
            continue
        with file_lock(name):
            if path.exists():
                continue
            doc = DEFAULTS[name]()
            doc["updated_at"] = utcnow_iso()
            validate(name, doc)
            _atomic_write_text(path, serialize(doc))
            created.append(name)
    return created


def check_all() -> dict[str, str | None]:
    """Validate every data file. Returns {name: error message or None}."""
    report: dict[str, str | None] = {}
    for name in DATA_FILES:
        try:
            load(name)
            report[name] = None
        except DataError as exc:
            report[name] = str(exc)
    return report


# Convenience helpers for the common "list of records under items" files.

def find_item(doc: dict[str, Any], item_id: str, key: str = "items") -> dict[str, Any] | None:
    return next((it for it in doc[key] if it.get("id") == item_id), None)
