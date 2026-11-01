"""Learning memory: incremental, validated, history-tracked operations.

The AI never replaces the memory document wholesale. Every change is one of
add / update / delete / reset on a single category, and is recorded in
``history`` with the before/after value, actor, and reason.
"""

from __future__ import annotations

import copy
from typing import Any

from .util import new_id, normalize_text, utcnow_iso

MEMORY_CATEGORIES = (
    "brand_identity",
    "audience_interests",
    "preferred_styles",
    "successful_hooks",
    "weak_hooks",
    "high_performing_topics",
    "underperforming_topics",
    "content_formats",
    "rejection_feedback",
    "editing_patterns",
    "performance_insights",
    "repetition_warnings",
    "strategic_recommendations",
    "lessons_learned",
)

CONFIDENCE_LEVELS = ("low", "medium", "high")
MAX_ITEMS_PER_CATEGORY = 50
MAX_HISTORY = 1000


class MemoryOpError(ValueError):
    """Invalid memory operation."""


def _check_category(category: str) -> None:
    if category not in MEMORY_CATEGORIES:
        raise MemoryOpError(f"unknown memory category: {category!r}")


def _record(doc: dict[str, Any], op: str, category: str, item_id: str | None,
            before: Any, after: Any, actor: str, reason: str | None) -> None:
    doc["history"].append({
        "id": new_id("mh"), "at": utcnow_iso(), "op": op, "category": category,
        "item_id": item_id, "before": before, "after": after, "actor": actor, "reason": reason,
    })
    if len(doc["history"]) > MAX_HISTORY:
        del doc["history"][: len(doc["history"]) - MAX_HISTORY]


def find_similar(doc: dict[str, Any], category: str, text: str) -> dict[str, Any] | None:
    needle = normalize_text(text)
    return next((it for it in doc["categories"][category] if normalize_text(it["text"]) == needle), None)


def add_item(doc: dict[str, Any], category: str, text: str, *, confidence: str = "low",
             source: str = "learning_analyst", evidence_ids: list[str] | None = None,
             actor: str = "learning_analyst", reason: str | None = None) -> dict[str, Any]:
    """Add an insight, or reinforce an identical existing one (evidence +1)."""
    _check_category(category)
    text = text.strip()
    if not 3 <= len(text) <= 500:
        raise MemoryOpError("memory text must be 3–500 characters")
    if confidence not in CONFIDENCE_LEVELS:
        raise MemoryOpError(f"invalid confidence: {confidence!r}")
    evidence_ids = list(evidence_ids or [])
    existing = find_similar(doc, category, text)
    now = utcnow_iso()
    if existing:
        before = copy.deepcopy(existing)
        existing["evidence_count"] += max(1, len(evidence_ids))
        existing["evidence_ids"] = sorted(set(existing.get("evidence_ids", [])) | set(evidence_ids))[-50:]
        if CONFIDENCE_LEVELS.index(confidence) > CONFIDENCE_LEVELS.index(existing["confidence"]):
            existing["confidence"] = confidence
        existing["updated_at"] = now
        _record(doc, "update", category, existing["id"], before, copy.deepcopy(existing), actor, reason)
        return existing
    items = doc["categories"][category]
    if len(items) >= MAX_ITEMS_PER_CATEGORY:
        # Drop the weakest, oldest analyst-sourced item; never auto-drop user-entered memory.
        candidates = [it for it in items if it["source"] != "user"]
        if not candidates:
            raise MemoryOpError(f"{category} is full ({MAX_ITEMS_PER_CATEGORY} user items)")
        weakest = min(candidates, key=lambda it: (CONFIDENCE_LEVELS.index(it["confidence"]),
                                                  it["evidence_count"], it["updated_at"]))
        delete_item(doc, category, weakest["id"], actor="system", reason="category capacity reached")
    item = {
        "id": new_id("mem"), "text": text, "confidence": confidence,
        "evidence_count": max(1, len(evidence_ids)) if source != "user" else len(evidence_ids),
        "evidence_ids": evidence_ids[-50:], "source": source, "created_at": now, "updated_at": now,
    }
    items.append(item)
    _record(doc, "add", category, item["id"], None, copy.deepcopy(item), actor, reason)
    return item


def update_item(doc: dict[str, Any], category: str, item_id: str, *, text: str | None = None,
                confidence: str | None = None, actor: str = "user", reason: str | None = None) -> dict[str, Any]:
    _check_category(category)
    item = next((it for it in doc["categories"][category] if it["id"] == item_id), None)
    if item is None:
        raise MemoryOpError(f"memory item {item_id} not found in {category}")
    before = copy.deepcopy(item)
    if text is not None:
        text = text.strip()
        if not 3 <= len(text) <= 500:
            raise MemoryOpError("memory text must be 3–500 characters")
        item["text"] = text
    if confidence is not None:
        if confidence not in CONFIDENCE_LEVELS:
            raise MemoryOpError(f"invalid confidence: {confidence!r}")
        item["confidence"] = confidence
    if actor == "user":
        item["source"] = "user"
    item["updated_at"] = utcnow_iso()
    _record(doc, "update", category, item_id, before, copy.deepcopy(item), actor, reason)
    return item


def delete_item(doc: dict[str, Any], category: str, item_id: str, *, actor: str = "user",
                reason: str | None = None) -> None:
    _check_category(category)
    items = doc["categories"][category]
    idx = next((i for i, it in enumerate(items) if it["id"] == item_id), None)
    if idx is None:
        raise MemoryOpError(f"memory item {item_id} not found in {category}")
    removed = items.pop(idx)
    _record(doc, "delete", category, item_id, removed, None, actor, reason)


def reset_category(doc: dict[str, Any], category: str, *, actor: str = "user", reason: str | None = None) -> int:
    _check_category(category)
    removed = doc["categories"][category]
    doc["categories"][category] = []
    if removed:
        _record(doc, "reset", category, None, removed, None, actor, reason)
    return len(removed)


def strong_insights(doc: dict[str, Any], category: str) -> list[dict[str, Any]]:
    """High-confidence items — the only ones allowed to strongly steer strategy."""
    _check_category(category)
    return [it for it in doc["categories"][category] if it["confidence"] == "high"]


def summarize_for_prompt(doc: dict[str, Any], max_per_category: int = 6) -> str:
    """Compact Markdown digest of memory for agent context, strongest insights first."""
    rank = {c: i for i, c in enumerate(CONFIDENCE_LEVELS)}
    lines: list[str] = []
    for category in MEMORY_CATEGORIES:
        items = sorted(doc["categories"][category],
                       key=lambda it: (-rank[it["confidence"]], -it["evidence_count"]))[:max_per_category]
        if not items:
            continue
        lines.append(f"### {category.replace('_', ' ').title()}")
        lines.extend(f"- [{it['confidence']}, n={it['evidence_count']}] {it['text']}" for it in items)
    return "\n".join(lines) if lines else "(memory is empty — no learned patterns yet)"
