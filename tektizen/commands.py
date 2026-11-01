"""Dashboard commands — the only way the UI changes repository data.

The dashboard sends ``{"type": ..., ...}`` through the dashboard-command
workflow. Every command is validated against the current state; invalid
commands change nothing except an audit entry (for content actions).
"""

from __future__ import annotations

import copy
from typing import Any

from . import checks, memory, prompts, storage
from .settings import AUTO_PUBLISH, HUMAN_APPROVAL, _merge, default_settings
from .util import content_hash, new_id, utcnow_iso

MAX_REASON = 2000
APPROVABLE = {"PENDING_APPROVAL", "FAILED"}
# Human decisions recorded in approvals.json (the learning signal).
AUDITED = {"approve", "edit_approve", "reject", "archive", "refine", "regenerate"}


class CommandError(ValueError):
    pass


class Result(dict):
    """{'ok': bool, 'message': str, 'publish': bool, 'ai': {...}} — ai = follow-up work needing OpenRouter."""


def _require(cmd: dict[str, Any], key: str, kind: type = str, *, max_len: int = 64000) -> Any:
    value = cmd.get(key)
    if not isinstance(value, kind) or (isinstance(value, str) and not value.strip()):
        raise CommandError(f"'{key}' is required")
    if isinstance(value, str) and len(value) > max_len:
        raise CommandError(f"'{key}' is too long")
    return value.strip() if isinstance(value, str) else value


def _audit(content_id: str, action: str, *, reason: str | None, actor: str, edited_posts: list[str] | None = None,
           error: str | None = None) -> str:
    rec_id = new_id("apr")
    with storage.transaction("approvals") as doc:
        doc["items"].append({"id": rec_id, "created_at": utcnow_iso(), "content_id": content_id, "action": action,
                             "reason": (reason or None) and reason[:MAX_REASON], "edited_posts": edited_posts,
                             "actor": actor, "status": "rejected_invalid" if error else "applied", "error": error})
    return rec_id


def _content_action(cmd: dict[str, Any], actor: str, settings: dict[str, Any]) -> Result:
    action = cmd["type"]
    cid = _require(cmd, "content_id", max_len=60)
    reason = cmd.get("reason") if isinstance(cmd.get("reason"), str) else None
    publish = False
    ai: dict[str, Any] | None = None
    edited_posts = None
    try:
        with storage.transaction("content") as doc:
            item = storage.find_item(doc, cid)
            if item is None:
                raise CommandError(f"content {cid} not found")
            status = item["status"]
            ev = item.get("evaluation") or {}
            now = utcnow_iso()

            if action == "approve":
                if status not in APPROVABLE:
                    raise CommandError(f"cannot approve content in status {status}")
                if ev.get("critical_fact_failure"):
                    raise CommandError("critical fact-check failure: edit the content (Edit & approve) first")
                if not item.get("draft"):
                    raise CommandError("content has no draft")
                _set_approved(item, now)
                publish = True

            elif action == "edit_approve":
                if status not in APPROVABLE | {"DRAFT"}:
                    raise CommandError(f"cannot edit-approve content in status {status}")
                posts = _require(cmd, "posts", list)
                posts = [p.strip() for p in posts if isinstance(p, str) and p.strip()]
                errs = checks.check_posts_shape(posts, item["format"], settings["publishing"]["max_thread_posts"])
                if errs:
                    raise CommandError("; ".join(errs))
                draft = item.get("draft") or {"hook": "", "body": "", "cta": "", "posts": posts}
                if item.get("original_draft") is None and item.get("draft"):
                    item["original_draft"] = copy.deepcopy(item["draft"])
                item["draft"] = {"hook": str(cmd.get("hook") or posts[0].split("\n")[0])[:500],
                                 "body": str(cmd.get("body") if cmd.get("body") is not None else draft.get("body", "")),
                                 "cta": str(cmd.get("cta") if cmd.get("cta") is not None else draft.get("cta", "")),
                                 "posts": posts}
                item.setdefault("versions", []).append({"version": len(item.get("versions") or []) + 1,
                                                        "created_at": now, "author": f"user:{actor}",
                                                        "note": (reason or "edited before approval")[:300],
                                                        "draft": copy.deepcopy(item["draft"])})
                item["content_hash"] = content_hash(posts)
                edited_posts = posts
                if ev.get("critical_fact_failure"):
                    # The edit may have fixed it, but only a re-check can clear the flag.
                    item["status"] = "EVALUATION"
                    ai = {"op": "evaluate", "content_id": cid, "then_approve": True}
                else:
                    _mark_reviewed(ev)
                    _set_approved(item, now)
                    publish = True

            elif action == "reject":
                if status not in APPROVABLE | {"READY_TO_PUBLISH", "DRAFT"}:
                    raise CommandError(f"cannot reject content in status {status}")
                if not reason or len(reason.strip()) < 3:
                    raise CommandError("a rejection reason is required (it is used for learning)")
                item["status"] = "REJECTED"
                item["approval"] = {**(item.get("approval") or {}), "required": True, "decision": "rejected",
                                    "decided_at": now, "reason": reason.strip()[:MAX_REASON]}

            elif action == "archive":
                if status in ("PUBLISHING", "PUBLISH_UNCERTAIN"):
                    raise CommandError(f"cannot archive content in status {status}; reconcile it first")
                item["status"] = "ARCHIVED"

            elif action in ("refine", "submit_for_review"):
                if status not in APPROVABLE | {"DRAFT", "REJECTED"}:
                    raise CommandError(f"cannot {action} content in status {status}")
                if action == "submit_for_review":
                    _apply_draft_fields(item, cmd, settings)
                item["status"] = "REFINEMENT" if action == "refine" else "EVALUATION"
                ai = {"op": "evaluate", "content_id": cid, "user_notes": (reason or "")[:MAX_REASON],
                      "force_edit": action == "refine"}

            elif action == "regenerate":
                if status in ("PUBLISHED", "PUBLISHING", "PUBLISH_UNCERTAIN"):
                    raise CommandError(f"cannot regenerate content in status {status}")
                ai = {"op": "regenerate", "content_id": cid, "topic": item["topic"], "format": item["format"],
                      "tone": item.get("tone", ""), "instructions": item.get("instructions", ""),
                      "feedback": [reason] if reason else []}

            elif action == "reconcile_publish":
                if status != "PUBLISH_UNCERTAIN":
                    raise CommandError("only PUBLISH_UNCERTAIN content can be reconciled")
                resolution = cmd.get("resolution")
                pub = item["publishing"] = item.get("publishing") or {}
                if resolution == "published":
                    url = cmd.get("url")
                    if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
                        raise CommandError("url must start with https://")
                    item["status"] = "PUBLISHED"
                    pub["published_at"] = pub.get("published_at") or now
                    pub["url"] = url or pub.get("url")
                elif resolution == "not_published":
                    # The owner checked Threads and it's not there: allow publishing again with a fresh key.
                    item["status"] = "READY_TO_PUBLISH"
                    pub["key_generation"] = pub.get("key_generation", 0) + 1
                    pub["zernio_post_id"] = None
                    publish = True
                else:
                    raise CommandError("resolution must be 'published' or 'not_published'")
            else:
                raise CommandError(f"unknown content action {action}")
            item["updated_at"] = now
    except CommandError as exc:
        if action in AUDITED:
            _audit(cid, action, reason=reason, actor=actor, error=str(exc))
        raise
    apr = _audit(cid, action, reason=reason, actor=actor, edited_posts=edited_posts) if action in AUDITED else None
    if apr and action in ("approve", "edit_approve", "reject"):
        with storage.transaction("content") as doc:
            item = storage.find_item(doc, cid)
            if item.get("approval"):
                item["approval"]["approval_id"] = apr
    return Result(ok=True, message=f"{action} applied to {cid}", publish=publish, ai=ai)


def _set_approved(item: dict[str, Any], now: str) -> None:
    item["status"] = "READY_TO_PUBLISH"
    item["approval"] = {**(item.get("approval") or {}), "required": True, "decision": "approved",
                        "decided_at": now, "reason": None}


def _mark_reviewed(ev: dict[str, Any]) -> None:
    for w in ev.get("warnings") or []:
        if w.get("severity") != "critical":
            w["resolved"] = True


def _apply_draft_fields(item: dict[str, Any], cmd: dict[str, Any], settings: dict[str, Any]) -> None:
    posts = cmd.get("posts")
    if posts is None:
        return
    posts = [p.strip() for p in posts if isinstance(p, str) and p.strip()]
    errs = checks.check_posts_shape(posts, item["format"], settings["publishing"]["max_thread_posts"])
    if errs:
        raise CommandError("; ".join(errs))
    item["draft"] = {"hook": str(cmd.get("hook") or posts[0].split("\n")[0])[:500], "body": str(cmd.get("body") or ""),
                     "cta": str(cmd.get("cta") or ""), "posts": posts}


def save_draft(cmd: dict[str, Any], actor: str, settings: dict[str, Any]) -> Result:
    """Create or update a Content Studio draft (status DRAFT)."""
    from .pipeline import new_item  # local: pipeline imports heavy modules

    fmt = cmd.get("format")
    if fmt not in settings["generation"]["enabled_formats"] and fmt not in (
            "single", "thread", "question", "opinion", "educational", "storytelling", "tools_recommendation",
            "news_commentary"):
        raise CommandError("invalid format")
    posts = [p.strip() for p in (cmd.get("posts") or []) if isinstance(p, str) and p.strip()]
    errs = checks.check_posts_shape(posts, fmt, settings["publishing"]["max_thread_posts"]) if posts else ["posts are required"]
    if errs:
        raise CommandError("; ".join(errs))
    topic = _require(cmd, "topic", max_len=300)
    draft = {"hook": str(cmd.get("hook") or posts[0].split("\n")[0])[:500], "body": str(cmd.get("body") or ""),
             "cta": str(cmd.get("cta") or ""), "posts": posts}
    cid = cmd.get("content_id")
    with storage.transaction("content") as doc:
        if cid:
            item = storage.find_item(doc, cid)
            if item is None or item["status"] != "DRAFT":
                raise CommandError("only DRAFT content can be edited from the studio")
        else:
            item = new_item(topic=topic, fmt=fmt, origin="studio", tone=str(cmd.get("tone") or "")[:100],
                            instructions=str(cmd.get("instructions") or "")[:2000])
            doc["items"].append(item)
        item.update(topic=topic, format=fmt, status="DRAFT", draft=draft, updated_at=utcnow_iso())
        item.setdefault("versions", []).append({"version": len(item["versions"]) + 1, "created_at": utcnow_iso(),
                                                "author": f"user:{actor}", "note": "studio draft",
                                                "draft": copy.deepcopy(draft)})
        cid = item["id"]
    return Result(ok=True, message=f"draft {cid} saved", publish=False, ai=None, content_id=cid)


def update_settings(cmd: dict[str, Any], actor: str) -> Result:
    patch = _require(cmd, "patch", dict)
    with storage.transaction("settings") as doc:
        current = _merge(default_settings(), doc)
        before_mode = current["approval"]["mode"]
        merged = _merge(current, patch)
        if "schema_version" in patch or "updated_at" in patch:
            raise CommandError("cannot change schema_version/updated_at")
        new_mode = merged["approval"]["mode"]
        if new_mode not in (HUMAN_APPROVAL, AUTO_PUBLISH):
            raise CommandError("invalid approval mode")
        if new_mode == AUTO_PUBLISH and before_mode != AUTO_PUBLISH:
            if cmd.get("confirm_auto_publish") is not True:
                raise CommandError("switching to automatic publishing requires explicit confirmation")
            merged["approval"]["auto_publish_enabled_at"] = utcnow_iso()
            merged["approval"]["auto_publish_enabled_by"] = actor
        if new_mode == HUMAN_APPROVAL:
            merged["approval"]["auto_publish_enabled_at"] = None
            merged["approval"]["auto_publish_enabled_by"] = None
        errors = storage.validation_errors("settings", merged)
        if errors:
            raise CommandError("invalid settings: " + "; ".join(errors[:5]))
        doc.clear()
        doc.update(merged)
    return Result(ok=True, message="settings updated", publish=False, ai=None)


def memory_command(cmd: dict[str, Any], actor: str) -> Result:
    kind = cmd["type"]
    category = _require(cmd, "category", max_len=60)
    reason = cmd.get("reason") if isinstance(cmd.get("reason"), str) else None
    try:
        with storage.transaction("learning_memory") as doc:
            if kind == "memory_add":
                memory.add_item(doc, category, _require(cmd, "text", max_len=500),
                                confidence=cmd.get("confidence") or "medium", source="user", actor=actor,
                                reason=reason)
            elif kind == "memory_update":
                memory.update_item(doc, category, _require(cmd, "item_id", max_len=60),
                                   text=cmd.get("text"), confidence=cmd.get("confidence"), actor=actor, reason=reason)
            elif kind == "memory_delete":
                memory.delete_item(doc, category, _require(cmd, "item_id", max_len=60), actor=actor, reason=reason)
            elif kind == "memory_reset":
                if cmd.get("confirm") is not True:
                    raise CommandError("reset requires confirm: true")
                memory.reset_category(doc, category, actor=actor, reason=reason)
    except memory.MemoryOpError as exc:
        raise CommandError(str(exc)) from exc
    return Result(ok=True, message=f"{kind} applied to {category}", publish=False, ai=None)


def update_markdown(cmd: dict[str, Any]) -> Result:
    markdown = _require(cmd, "markdown", max_len=prompts.MAX_MARKDOWN_BYTES)
    markdown = markdown.replace("\r\n", "\n").rstrip() + "\n"
    if cmd["type"] == "update_prompt":
        path = prompts.prompt_path(_require(cmd, "agent", max_len=60))
        problems = prompts.validate_prompt_markdown(markdown)
        if problems:
            raise CommandError("; ".join(problems))
    else:
        path = prompts.config_path(_require(cmd, "name", max_len=60))
    storage._atomic_write_text(path, markdown)
    return Result(ok=True, message=f"updated {path.name}", publish=False, ai=None)


def apply_command(cmd: dict[str, Any], actor: str, settings: dict[str, Any]) -> Result:
    if not isinstance(cmd, dict) or not isinstance(cmd.get("type"), str):
        raise CommandError("command must be an object with a 'type'")
    kind = cmd["type"]
    try:
        if kind in ("approve", "edit_approve", "reject", "archive", "refine", "submit_for_review",
                    "regenerate", "reconcile_publish"):
            return _content_action(cmd, actor, settings)
        if kind == "save_draft":
            return save_draft(cmd, actor, settings)
        if kind == "update_settings":
            return update_settings(cmd, actor)
        if kind in ("memory_add", "memory_update", "memory_delete", "memory_reset"):
            return memory_command(cmd, actor)
        if kind in ("update_prompt", "update_config"):
            return update_markdown(cmd)
    except prompts.PromptError as exc:
        raise CommandError(str(exc)) from exc
    raise CommandError(f"unknown command type {kind!r}")
