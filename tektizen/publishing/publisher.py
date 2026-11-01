"""Publish READY_TO_PUBLISH content through Zernio, with duplicate and uncertainty protection.

State machine per item:
  READY_TO_PUBLISH → PUBLISHING (saved before the API call)
    → PUBLISHED          confirmed by the API
    → FAILED             definitively rejected (a human may re-approve after fixing)
    → READY_TO_PUBLISH   rate limited (nothing created; tried again next run)
    → PUBLISH_UNCERTAIN  may or may not be live — never retried automatically

An item found in PUBLISHING at the start of a run means a previous run died
mid-request; it becomes PUBLISH_UNCERTAIN.
"""

from __future__ import annotations

from typing import Any

from integrations import zernio_client as zc

from .. import storage
from ..runs import RunRecorder
from ..util import content_hash, new_id, utcnow_iso
from ..settings import threads_account_id
from . import gate


def _history(item: dict[str, Any], result: str, *, key: str, res: zc.PublishResult | None, mode: str,
             run_id: str, error: str | None = None) -> dict[str, Any]:
    now = utcnow_iso()
    err = error or (res.error if res else None)
    return {"id": new_id("pub"), "content_id": item["id"], "attempted_at": now, "completed_at": now,
            "result": result, "mode": mode, "idempotency_key": key,
            "zernio_post_id": res.post_id if res else None,
            "platform_post_ids": res.platform_post_ids if res else [], "url": res.url if res else None,
            "post_count": max(1, len((item.get("draft") or {}).get("posts") or [])),
            "http_status": res.http_status if res else None,
            "error": err[:500] if err else None,
            "run_id": run_id}


def _idempotency_key(item: dict[str, Any]) -> str:
    gen = (item.get("publishing") or {}).get("key_generation", 0)
    return f"tektizen-{item['id']}-{gen}"


def recover_interrupted(rec: RunRecorder) -> int:
    with storage.transaction("content") as doc:
        stuck = [i for i in doc["items"] if i["status"] == "PUBLISHING"]
        for item in stuck:
            item["status"] = "PUBLISH_UNCERTAIN"
            item["updated_at"] = utcnow_iso()
            pub = item["publishing"] = item.get("publishing") or {}
            pub["last_error"] = "previous publishing run was interrupted mid-request"
            rec.warn(f"{item['id']}: was left in PUBLISHING; marked PUBLISH_UNCERTAIN")
    return len(stuck)


def publish_ready(rec: RunRecorder, settings: dict[str, Any], client: zc.ZernioClient,
                  *, only_ids: set[str] | None = None) -> dict[str, int]:
    stats = {"published": 0, "failed": 0, "uncertain": 0, "blocked": 0, "rate_limited": 0}
    recover_interrupted(rec)
    sent = 0
    content = storage.load("content")
    ready = sorted((i for i in content["items"] if i["status"] == "READY_TO_PUBLISH"
                    and (only_ids is None or i["id"] in only_ids)),
                   key=lambda i: ((i.get("approval") or {}).get("decided_at") or i["updated_at"]))
    if not ready:
        rec.info("no content is ready to publish")
        return stats
    published = [i for i in content["items"] if i["status"] in ("PUBLISHED", "PUBLISH_UNCERTAIN") and i.get("draft")]
    published_hashes = {i.get("content_hash") or content_hash(i["draft"]["posts"]) for i in published}
    published_texts = ["\n".join(i["draft"]["posts"]) for i in published][-100:]

    for snapshot in ready:
        verdict = gate.publish_gate(snapshot, settings, published_hashes=published_hashes,
                                    published_texts=published_texts, published_this_run=sent)
        if not verdict.allowed:
            stats["blocked"] += 1
            rec.info(f"{snapshot['id']}: not published — " + "; ".join(verdict.reasons)[:400])
            continue
        mode = "human_approved" if (snapshot.get("approval") or {}).get("decision") == "approved" else "auto"

        # Commit the PUBLISHING state locally before the network call.
        with storage.transaction("content") as doc:
            item = storage.find_item(doc, snapshot["id"])
            if item is None or item["status"] != "READY_TO_PUBLISH":
                continue
            pub = item.get("publishing") or {}
            item["publishing"] = pub
            pub.setdefault("key_generation", 0)
            key = _idempotency_key(item)
            pub.update(idempotency_key=key, attempts=pub.get("attempts", 0) + 1, last_error=None)
            pub.setdefault("zernio_post_id", None)
            pub.setdefault("platform_post_ids", [])
            pub.setdefault("url", None)
            pub.setdefault("published_at", None)
            item["status"] = "PUBLISHING"
            item["updated_at"] = utcnow_iso()
            posts = list(item["draft"]["posts"])

        rec.info(f"{snapshot['id']}: publishing {len(posts)} post(s) to Threads ({mode})")
        result = client.publish(posts, threads_account_id(settings) or "", key,
                                metadata={"tektizen_content_id": snapshot["id"]})
        sent += 1
        _apply_result(rec, snapshot["id"], result, key, mode, stats)
        if result.outcome == zc.PUBLISHED:
            published_hashes.add(content_hash(posts))
            published_texts.append("\n".join(posts))
        if result.outcome == zc.RATE_LIMITED:
            break
    return stats


def _apply_result(rec: RunRecorder, content_id: str, res: zc.PublishResult, key: str, mode: str,
                  stats: dict[str, int]) -> None:
    now = utcnow_iso()
    with storage.transaction("content") as doc:
        item = storage.find_item(doc, content_id)
        pub = item["publishing"]
        if res.post_id:
            pub["zernio_post_id"] = res.post_id
        if res.platform_post_ids:
            pub["platform_post_ids"] = res.platform_post_ids
        if res.url:
            pub["url"] = res.url
        if res.outcome == zc.PUBLISHED:
            item["status"] = "PUBLISHED"
            pub["published_at"] = now
            result, stats_key = "success", "published"
        elif res.outcome == zc.FAILED:
            item["status"] = "FAILED"
            pub["key_generation"] = pub.get("key_generation", 0) + 1  # next attempt must use a fresh key
            result, stats_key = "failed", "failed"
        elif res.outcome == zc.RATE_LIMITED:
            item["status"] = "READY_TO_PUBLISH"
            result, stats_key = "failed", "rate_limited"
        elif res.outcome == zc.DUPLICATE:
            item["status"] = "PUBLISH_UNCERTAIN"
            result, stats_key = "duplicate", "uncertain"
        else:
            item["status"] = "PUBLISH_UNCERTAIN"
            result, stats_key = "uncertain", "uncertain"
        pub["last_error"] = res.error
        item["updated_at"] = now
        snapshot = dict(item)
    stats[stats_key] += 1
    with storage.transaction("publishing_history") as doc:
        doc["items"].append(_history(snapshot, result, key=key, res=res, mode=mode, run_id=rec.id))
    msg = f"{content_id}: {res.outcome}" + (f" ({res.error})" if res.error else "") + (f" {res.url}" if res.url else "")
    (rec.info if res.outcome == zc.PUBLISHED else rec.warn)(msg)


def reconcile_uncertain(rec: RunRecorder, client: zc.ZernioClient) -> int:
    """Read-only status check for uncertain items that have a Zernio post ID. Never re-publishes."""
    content = storage.load("content")
    todo = [i for i in content["items"] if i["status"] == "PUBLISH_UNCERTAIN"
            and (i.get("publishing") or {}).get("zernio_post_id")]
    resolved = 0
    for snapshot in todo:
        post_id = snapshot["publishing"]["zernio_post_id"]
        try:
            res = client.get_post(post_id)
        except zc.ZernioError as exc:
            rec.warn(f"{snapshot['id']}: could not check Zernio post {post_id}: {exc}")
            continue
        if res.outcome not in (zc.PUBLISHED, zc.FAILED):
            continue
        with storage.transaction("content") as doc:
            item = storage.find_item(doc, snapshot["id"])
            if item is None or item["status"] != "PUBLISH_UNCERTAIN":
                continue
            pub = item["publishing"]
            if res.outcome == zc.PUBLISHED:
                item["status"] = "PUBLISHED"
                pub["published_at"] = pub.get("published_at") or utcnow_iso()
                pub["url"] = res.url or pub.get("url")
                pub["platform_post_ids"] = res.platform_post_ids or pub.get("platform_post_ids", [])
            else:
                item["status"] = "FAILED"
                pub["key_generation"] = pub.get("key_generation", 0) + 1
                pub["last_error"] = res.error
            item["updated_at"] = utcnow_iso()
        resolved += 1
        rec.info(f"{snapshot['id']}: reconciled from Zernio as {res.outcome}")
    return resolved
