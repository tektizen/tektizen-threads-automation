from __future__ import annotations

import json
import multiprocessing
import os

import pytest

from tektizen import storage
from tektizen.util import new_id, utcnow_iso


def _content_item(**overrides):
    now = utcnow_iso()
    item = {
        "id": new_id("cnt"), "created_at": now, "updated_at": now, "status": "PENDING_APPROVAL",
        "format": "single", "topic": "Prompt dengan konteks", "origin": "studio",
        "draft": {"hook": "h", "body": "b", "cta": "c", "posts": ["h b c"]},
    }
    item.update(overrides)
    return item


def test_empty_data_dir_reads_defaults_without_writing(repo):
    for name in storage.DATA_FILES:
        doc = storage.load(name)
        assert doc["schema_version"] == 1
    assert list((repo / "data").glob("*.json")) == []


def test_init_creates_valid_files_and_never_overwrites(repo):
    created = storage.init_data()
    assert set(created) == set(storage.DATA_FILES)
    assert all(err is None for err in storage.check_all().values())

    with storage.transaction("content") as doc:
        doc["items"].append(_content_item())
    before = (repo / "data" / "content.json").read_text(encoding="utf-8")
    assert storage.init_data() == []
    assert (repo / "data" / "content.json").read_text(encoding="utf-8") == before


def test_corrupted_file_raises_and_is_not_replaced(repo):
    path = repo / "data" / "content.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(storage.DataError, match="not valid JSON"):
        storage.load("content")
    storage.init_data()
    assert path.read_text(encoding="utf-8") == "{ not json"
    with pytest.raises(storage.DataError):
        with storage.transaction("content") as doc:
            doc["items"].append(_content_item())
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_empty_file_is_an_error_not_a_reset(repo):
    (repo / "data" / "ideas.json").write_text("   ", encoding="utf-8")
    with pytest.raises(storage.DataError, match="empty"):
        storage.load("ideas")


def test_invalid_write_is_rejected_and_file_unchanged(repo):
    storage.init_data()
    path = repo / "data" / "content.json"
    before = path.read_text(encoding="utf-8")
    with pytest.raises(storage.DataError, match="failed validation"):
        with storage.transaction("content") as doc:
            doc["items"].append(_content_item(status="YOLO"))
    assert path.read_text(encoding="utf-8") == before


def test_post_over_500_chars_is_rejected(repo):
    with pytest.raises(storage.DataError):
        with storage.transaction("content") as doc:
            doc["items"].append(_content_item(draft={"hook": "", "body": "", "cta": "", "posts": ["x" * 501]}))


def test_future_schema_version_refused(repo):
    (repo / "data" / "ideas.json").write_text(
        json.dumps({"schema_version": 99, "updated_at": None, "items": []}), encoding="utf-8")
    with pytest.raises(storage.DataError, match="Upgrade the engine"):
        storage.load("ideas")


def test_unchanged_document_is_not_rewritten(repo):
    storage.init_data()
    path = repo / "data" / "ideas.json"
    mtime = path.stat().st_mtime_ns
    with storage.transaction("ideas"):
        pass
    assert path.stat().st_mtime_ns == mtime


def test_atomic_write_leaves_no_temp_files(repo):
    for _ in range(3):
        with storage.transaction("content") as doc:
            doc["items"].append(_content_item())
    leftovers = [p.name for p in (repo / "data").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    assert len(storage.load("content")["items"]) == 3


def test_stale_lock_is_recovered(repo):
    lock = repo / "data" / ".locks" / "ideas.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("dead")
    old = os.path.getmtime(lock) - storage.STALE_LOCK_SECONDS - 5
    os.utime(lock, (old, old))
    with storage.transaction("ideas") as doc:
        doc["items"].append({"id": new_id("idea"), "created_at": utcnow_iso(), "topic": "t", "status": "new"})
    assert not lock.exists()


def _append_many(root: str, n: int) -> None:
    os.environ["TEKTIZEN_ROOT"] = root
    for _ in range(n):
        with storage.transaction("content") as doc:
            doc["items"].append(_content_item())


def test_concurrent_writers_do_not_lose_updates(repo):
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_append_many, args=(str(repo), 5)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    items = storage.load("content")["items"]
    assert len(items) == 20
    assert len({i["id"] for i in items}) == 20


def test_unknown_data_file_rejected(repo):
    with pytest.raises(ValueError):
        storage.load("../secrets")
