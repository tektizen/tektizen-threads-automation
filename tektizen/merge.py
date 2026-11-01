"""Git merge driver for data/*.json: three-way merge at the record level.

Workflows run concurrently (e.g. two dashboard commands a second apart). When
the second one pushes, ``git pull --rebase`` calls this driver instead of
producing text conflicts:

* Lists of records with ``id`` are merged by id. Records changed on one side
  take that side; changed on both sides take the newer ``updated_at`` (ours on ties).
* Objects are merged key by key, recursively.
* Plain values changed on both sides: counters in agent_metrics add their
  deltas; anything else prefers ours (the change being pushed now).

The result is schema-validated; if it is invalid the driver reports a conflict
and the push loop fails loudly rather than committing bad data.

Registered in .gitattributes + ``git config merge.tektizen-json.driver``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import storage

_MISSING = object()


def _is_record_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, dict) and "id" in v for v in value)


def _merge_records(base: list[dict], ours: list[dict], theirs: list[dict], counters: bool) -> list[dict]:
    b = {r["id"]: r for r in base}
    o = {r["id"]: r for r in ours}
    t = {r["id"]: r for r in theirs}
    order = [r["id"] for r in theirs] + [r["id"] for r in ours if r["id"] not in t]
    out = []
    for rid in order:
        ov, tv, bv = o.get(rid, _MISSING), t.get(rid, _MISSING), b.get(rid, _MISSING)
        if ov is _MISSING or tv is _MISSING:
            # Present on one side only: added there, or deleted on the other.
            present = tv if ov is _MISSING else ov
            if bv is not _MISSING and present == bv:
                continue  # unchanged on the side that kept it, deleted on the other → delete
            out.append(present)
            continue
        out.append(merge_values(bv if bv is not _MISSING else None, ov, tv, counters))
    return out


def merge_values(base: Any, ours: Any, theirs: Any, counters: bool = False) -> Any:
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    if isinstance(ours, dict) and isinstance(theirs, dict):
        if "id" in ours and ours.get("id") == theirs.get("id") and "updated_at" in ours and "updated_at" in theirs:
            # Same record edited on both sides: merge fields, preferring the newer edit on clashes.
            newer_is_theirs = str(theirs.get("updated_at") or "") > str(ours.get("updated_at") or "")
            merged = _merge_dicts(base if isinstance(base, dict) else {}, ours, theirs, counters)
            if newer_is_theirs:
                for key in theirs:
                    if ours.get(key) != theirs.get(key) and not (isinstance(base, dict) and base.get(key) == theirs.get(key)):
                        merged[key] = theirs[key]
            return merged
        return _merge_dicts(base if isinstance(base, dict) else {}, ours, theirs, counters)
    if _is_record_list(ours) and _is_record_list(theirs):
        return _merge_records(base if _is_record_list(base) else [], ours, theirs, counters)
    if counters and all(isinstance(v, int) and not isinstance(v, bool) for v in (base, ours, theirs)):
        return ours + theirs - base
    return ours


def _merge_dicts(base: dict, ours: dict, theirs: dict, counters: bool) -> dict:
    out: dict[str, Any] = {}
    for key in list(theirs) + [k for k in ours if k not in theirs]:
        ov, tv, bv = ours.get(key, _MISSING), theirs.get(key, _MISSING), base.get(key, _MISSING)
        if ov is _MISSING or tv is _MISSING:
            present = tv if ov is _MISSING else ov
            if bv is not _MISSING and present == bv:
                continue
            out[key] = present
        else:
            out[key] = merge_values(None if bv is _MISSING else bv, ov, tv, counters)
    return out


def merge_documents(name: str, base: Any, ours: Any, theirs: Any) -> Any:
    merged = merge_values(base, ours, theirs, counters=(name == "agent_metrics"))
    if isinstance(merged, dict):
        stamps = [d.get("updated_at") for d in (ours, theirs) if isinstance(d, dict) and d.get("updated_at")]
        if stamps:
            merged["updated_at"] = max(stamps)
    return merged


def run_driver(base_path: str, ours_path: str, theirs_path: str, file_path: str) -> int:
    """git merge driver entry point. Writes the result to ours_path. Returns 0 on success, 1 on conflict."""
    name = Path(file_path).stem
    if name not in storage.DATA_FILES:
        return 1

    def read(p: str) -> Any:
        try:
            text = Path(p).read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else None
        except (OSError, json.JSONDecodeError):
            return None

    base, ours, theirs = read(base_path), read(ours_path), read(theirs_path)
    if ours is None or theirs is None:
        return 1
    merged = merge_documents(name, base, ours, theirs)
    errors = storage.validation_errors(name, merged)
    if errors:
        print(f"tektizen merge driver: merged {name}.json is invalid: {errors[:3]}")
        return 1
    Path(ours_path).write_text(storage.serialize(merged), encoding="utf-8", newline="\n")
    return 0
