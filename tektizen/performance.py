"""Collect post analytics from Zernio into performance.json (null = unavailable, never 0)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from integrations import zernio_client as zc

from . import storage
from .runs import RunRecorder
from .util import new_id, parse_iso, utcnow, utcnow_iso

TRACK_DAYS = 30


def collect_metrics(rec: RunRecorder, client: zc.ZernioClient) -> dict[str, int]:
    stats = {"checked": 0, "updated": 0, "pending": 0, "unavailable": 0, "errors": 0}
    cutoff = utcnow() - timedelta(days=TRACK_DAYS)
    items = [i for i in storage.load("content")["items"] if i["status"] == "PUBLISHED"
             and (i.get("publishing") or {}).get("zernio_post_id")
             and parse_iso(i["publishing"].get("published_at") or i["updated_at"]) >= cutoff]
    if not items:
        rec.info("no recently published content to collect metrics for")
        return stats
    latest = _latest_snapshots()
    new_snapshots: list[dict[str, Any]] = []
    for item in items:
        stats["checked"] += 1
        post_id = item["publishing"]["zernio_post_id"]
        result = client.get_analytics(post_id)
        if result.status == "unavailable":
            stats["unavailable"] += 1
            rec.warn(f"analytics unavailable: {result.error}")
            break  # plan-level; no point asking for every post
        if result.status == "pending":
            stats["pending"] += 1
            continue
        if result.status != "ok" or result.metrics is None:
            stats["errors"] += 1
            rec.warn(f"{item['id']}: analytics error: {result.error}")
            continue
        prev = latest.get(item["id"])
        if prev and prev["metrics"] == result.metrics:
            continue  # unchanged — avoid noise and commits
        new_snapshots.append({"id": new_id("perf"), "content_id": item["id"], "zernio_post_id": post_id,
                              "collected_at": utcnow_iso(), "published_at": item["publishing"].get("published_at"),
                              "metrics": result.metrics, "source": "zernio", "raw_status": "ok"})
    if new_snapshots:
        with storage.transaction("performance") as doc:
            doc["items"].extend(new_snapshots)
        stats["updated"] = len(new_snapshots)
    rec.info(f"metrics: {stats}")
    return stats


def _latest_snapshots() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for snap in storage.load("performance")["items"]:
        cur = latest.get(snap["content_id"])
        if cur is None or snap["collected_at"] >= cur["collected_at"]:
            latest[snap["content_id"]] = snap
    return latest


def latest_metrics() -> dict[str, dict[str, Any]]:
    return _latest_snapshots()
