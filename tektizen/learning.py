"""Learning loop: turn approvals, edits, and performance into incremental memory updates.

Skips the AI call entirely when there is no new evidence since the last analysis.
"""

from __future__ import annotations

from typing import Any

from . import agents, memory, storage
from .agents import AgentFailure, AgentRunner
from .performance import latest_metrics
from .runs import RunRecorder
from .util import utcnow_iso

MAX_SIGNALS = 30


def gather_signals(since: str | None) -> dict[str, Any]:
    content = {i["id"]: i for i in storage.load("content")["items"]}
    approvals = [a for a in storage.load("approvals")["items"]
                 if a["status"] == "applied" and (since is None or a["created_at"] > since)]
    approvals_out, edits = [], []
    for a in approvals[-MAX_SIGNALS:]:
        item = content.get(a["content_id"]) or {}
        approvals_out.append({"id": a["id"], "content_id": a["content_id"], "action": a["action"],
                              "reason": a.get("reason"), "topic": item.get("topic"), "format": item.get("format"),
                              "hook": (item.get("draft") or {}).get("hook")})
        if a["action"] == "edit_approve" and item.get("original_draft") and item.get("draft"):
            edits.append({"content_id": item["id"], "original_posts": item["original_draft"]["posts"],
                          "approved_posts": item["draft"]["posts"]})
    perf = []
    metrics = latest_metrics()
    new_metrics = any(since is None or m["collected_at"] > since for m in metrics.values())
    for cid, snap in metrics.items():
        item = content.get(cid)
        if not item:
            continue
        perf.append({"content_id": cid, "perf_id": snap["id"], "topic": item["topic"], "format": item["format"],
                     "hook": (item.get("draft") or {}).get("hook"),
                     "published_at": snap.get("published_at"), "metrics": snap["metrics"]})
    published = sum(1 for i in content.values() if i["status"] == "PUBLISHED")
    return {"approvals": approvals_out, "edits": edits[-10:], "performance": perf[-MAX_SIGNALS:],
            "has_new": bool(approvals_out) or new_metrics,
            "summary_stats": {"published_count": published, "with_metrics_count": len(perf)}}


def run_learning(rec: RunRecorder, runner: AgentRunner) -> int:
    mem = storage.load("learning_memory")
    signals = gather_signals(mem.get("last_analysis_at"))
    if not signals["has_new"]:
        rec.info("learning: no new feedback or metrics since last analysis; skipping AI call")
        return 0
    evidence = {a["id"] for a in signals["approvals"]} | {a["content_id"] for a in signals["approvals"]}
    evidence |= {p["content_id"] for p in signals["performance"]} | {p["perf_id"] for p in signals["performance"]}
    payload = {"current_memory": memory.summarize_for_prompt(mem), "approvals": signals["approvals"],
               "edits": signals["edits"], "performance": signals["performance"],
               "summary_stats": signals["summary_stats"]}
    try:
        out, _ = runner.run("learning_analyst", payload, agents.learning_analyst(evidence), stage_name="learning")
    except AgentFailure:
        return 0
    applied = 0
    with storage.transaction("learning_memory") as doc:
        for op in out["operations"]:
            try:
                memory.add_item(doc, op["category"], op["text"], confidence=op["confidence"],
                                source="learning_analyst", evidence_ids=op["evidence_ids"],
                                actor="learning_analyst", reason=out.get("notes") or None)
                applied += 1
            except memory.MemoryOpError as exc:
                rec.warn(f"learning: skipped operation: {exc}")
        doc["last_analysis_at"] = utcnow_iso()
    rec.info(f"learning: applied {applied} memory update(s)")
    return applied
