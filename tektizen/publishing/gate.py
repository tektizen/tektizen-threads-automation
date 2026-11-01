"""The single place that decides whether content may be published.

Rules are documented for humans in config/approval_policy.md; editing that file
does not change behaviour — this module does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import checks
from ..settings import AUTO_PUBLISH, approval_mode, publishing_enabled
from ..util import content_hash


@dataclass
class Verdict:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _unresolved_severe(item: dict[str, Any]) -> list[dict[str, Any]]:
    ev = item.get("evaluation") or {}
    return [w for w in ev.get("warnings") or [] if w.get("severity") in ("high", "critical") and not w.get("resolved")]


def auto_publish_quality_gate(item: dict[str, Any], settings: dict[str, Any]) -> Verdict:
    """Quality/safety requirements for publishing WITHOUT a human."""
    reasons = []
    q = settings["quality"]
    ev = item.get("evaluation")
    if not ev:
        return Verdict(False, ["no evaluation on record"])
    for key, minimum, label in (("overall_score", q["min_overall"], "overall"),
                                ("factuality_score", q["min_factuality"], "factuality"),
                                ("brand_score", q["min_brand"], "brand compliance")):
        value = ev.get(key)
        if not isinstance(value, (int, float)) or value < minimum:
            reasons.append(f"{label} score {value} < {minimum}")
    if ev.get("fact_check_status") != "passed":
        reasons.append(f"fact check status is {ev.get('fact_check_status')!r}")
    if ev.get("critical_fact_failure"):
        reasons.append("critical fact-check failure")
    severe = _unresolved_severe(item)
    if severe:
        reasons.append(f"{len(severe)} unresolved high/critical warning(s): " + ", ".join(w["code"] for w in severe[:5]))
    return Verdict(not reasons, reasons)


def publish_gate(item: dict[str, Any], settings: dict[str, Any], *, published_hashes: set[str],
                 published_texts: list[str], published_this_run: int) -> Verdict:
    """Final check immediately before calling the publishing API (both modes)."""
    reasons: list[str] = []
    pub = settings.get("publishing") or {}
    if not publishing_enabled(settings):
        return Verdict(False, ["publishing kill switch is ON"])
    if not pub.get("threads_account_id"):
        reasons.append("Threads account ID is not configured")
    if published_this_run >= int(pub.get("max_posts_per_run", 0)):
        reasons.append(f"per-run publishing limit reached ({pub.get('max_posts_per_run', 0)})")
    if item.get("status") != "READY_TO_PUBLISH":
        reasons.append(f"status is {item.get('status')}, not READY_TO_PUBLISH")
    if (item.get("publishing") or {}).get("zernio_post_id"):
        reasons.append("item already has a Zernio post ID")

    approval = item.get("approval") or {}
    human_approved = approval.get("decision") == "approved"
    if not human_approved:
        # Only explicit auto mode + a passed quality gate can stand in for a human.
        if approval_mode(settings) != AUTO_PUBLISH or not item.get("auto_publish"):
            reasons.append("no human approval and auto-publish is not enabled for this item")
        else:
            reasons += auto_publish_quality_gate(item, settings).reasons

    ev = item.get("evaluation") or {}
    if ev.get("critical_fact_failure"):
        reasons.append("critical fact-check failure blocks publishing in every mode")

    posts = (item.get("draft") or {}).get("posts") or []
    errors = checks.check_posts_shape(posts, item.get("format", "single"), int(pub.get("max_thread_posts", 6)))
    reasons += errors
    if posts:
        h = content_hash(posts)
        if h in published_hashes:
            reasons.append("identical content was already published")
        elif published_texts:
            sim = checks.max_similarity("\n".join(posts), published_texts)
            if sim >= 0.85:
                reasons.append(f"content is {sim:.0%} similar to an already published post")
    return Verdict(not reasons, reasons)
