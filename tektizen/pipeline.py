"""Content pipeline: research → strategy → English draft → Malay → checks → evaluation → refinement → approval.

AI request budget for one daily item (no repairs): research 1 + strategy 1 +
creator 1 + localizer 1 + quality 1 + fact check 1 = 6, plus editor 1 and
re-evaluation 2 when refinement is needed = 9.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from . import agents, checks, memory, prompts, research, storage
from .agents import AgentFailure, AgentRunner
from .openrouter import OpenRouterClient
from .publishing import gate
from .runs import RunRecorder
from .settings import auto_publish_allowed, load_settings
from .util import content_hash, new_id, utcnow_iso

RECENT_WINDOW = 40
ACTIVE_STATUSES = {"PENDING_APPROVAL", "READY_TO_PUBLISH", "PUBLISHING", "PUBLISHED", "PUBLISH_UNCERTAIN"}


@dataclass
class Context:
    settings: dict[str, Any]
    client: OpenRouterClient
    runner: AgentRunner
    rec: RunRecorder
    memory_digest: str

    @property
    def today(self) -> str:
        return utcnow_iso()[:10]


def build_context(rec: RunRecorder, client: OpenRouterClient | None = None,
                  settings: dict[str, Any] | None = None) -> Context:
    settings = settings or load_settings()
    client = client or OpenRouterClient.from_settings(settings["ai"])
    rec.client = client
    digest = memory.summarize_for_prompt(storage.load("learning_memory"))
    return Context(settings=settings, client=client, runner=AgentRunner(client, settings, rec), rec=rec,
                   memory_digest=digest)


# ------------------------------------------------------------------ helpers

def _recent_items(limit: int = RECENT_WINDOW) -> list[dict[str, Any]]:
    items = [i for i in storage.load("content")["items"] if i.get("draft") and i["status"] in ACTIVE_STATUSES]
    return sorted(items, key=lambda i: i["created_at"], reverse=True)[:limit]


def _recent_context(exclude_id: str | None = None) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    recent = [i for i in _recent_items() if i["id"] != exclude_id]
    hooks = [i["draft"]["hook"] for i in recent if i["draft"].get("hook")]
    texts = ["\n".join(i["draft"]["posts"]) for i in recent]
    summary = [{"topic": i["topic"], "format": i["format"], "hook": i["draft"].get("hook", ""),
                "created_at": i["created_at"]} for i in recent[:20]]
    return hooks, texts, summary


def style_context() -> str:
    try:
        examples = prompts.load_config("style_examples")
    except prompts.PromptError:
        examples = ""
    approved = [i for i in _recent_items(60) if i["status"] in {"READY_TO_PUBLISH", "PUBLISHED"}
                and (i.get("approval") or {}).get("decision") == "approved"][:5]
    if approved:
        examples += "\n\n## Recently approved TektiZen posts (real voice)\n\n" + "\n\n---\n\n".join(
            "\n\n".join(i["draft"]["posts"]) for i in approved)
    return examples[:12000]


def upsert_content(item: dict[str, Any]) -> None:
    item["updated_at"] = utcnow_iso()
    with storage.transaction("content") as doc:
        existing = storage.find_item(doc, item["id"])
        if existing is None:
            doc["items"].append(item)
        else:
            existing.clear()
            existing.update(item)


def _add_version(item: dict[str, Any], draft: dict[str, Any], author: str, note: str = "") -> None:
    versions = item.setdefault("versions", [])
    versions.append({"version": len(versions) + 1, "created_at": utcnow_iso(), "author": author,
                     "note": note[:300], "draft": copy.deepcopy(draft)})


def _draft_of(out: dict[str, Any]) -> dict[str, Any]:
    return {"hook": out["hook"], "body": out["body"], "cta": out["cta"], "posts": list(out["posts"])}


def _fact_list(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": i, "text": f["text"], "quote": f.get("quote", ""), "source_url": f["source_url"]}
            for i, f in enumerate(item.get("facts") or [])]


def _code_stage(name: str, output: Any) -> dict[str, Any]:
    now = utcnow_iso()
    return {"stage": name, "agent": "code_checks", "status": "success", "started_at": now,
            "completed_at": now, "model": None, "usage": None, "output": output, "error": None}


# ------------------------------------------------------------------ research & strategy

def run_research(ctx: Context, *, focus: list[str] | None = None, max_ideas: int = 3) -> tuple[list[dict], dict]:
    """Fetch news, ask the Trend Researcher for grounded ideas, save them. Returns (ideas, stage)."""
    ideas_doc = storage.load("ideas")
    used_urls = {s["url"] for i in ideas_doc["items"] if i["status"] in ("used", "selected") for s in i.get("sources", [])}
    recent_topics = [i["topic"] for i in sorted(ideas_doc["items"], key=lambda i: i["created_at"])[-40:]]
    items = research.collect(ctx.settings["research"], used_urls=used_urls, recent_titles=[],
                             log_fn=ctx.rec.say)
    if focus:
        terms = [w for t in focus for w in t.lower().split() if len(w) > 3]
        for it in items:
            if any(w in f"{it.title} {it.summary}".lower() for w in terms):
                it.score += 3
        items.sort(key=lambda i: -i.score)
    if not items:
        ctx.rec.warn("research found no usable source items")
        return [], _code_stage("research", {"source_items": 0})
    source_text = {it.url: (it.text or it.summary or it.title) for it in items}
    payload = {"today": ctx.today, "max_ideas": max_ideas,
               "source_items": [it.for_agent(include_text=bool(it.text)) for it in items],
               "recent_topics": recent_topics[-25:],
               "focus_topics": focus or ctx.settings["generation"].get("topics", []),
               "memory": ctx.memory_digest}
    out, stage = ctx.runner.run("trend_researcher", payload, agents.trend_researcher(source_text, max_ideas),
                                stage_name="research")
    by_url = {it.url: it for it in items}
    now = utcnow_iso()
    ideas = []
    for idea in out["ideas"]:
        ideas.append({
            "id": new_id("idea"), "created_at": now, "updated_at": now, "topic": idea["topic"][:300],
            "angle": idea["angle"], "rationale": idea["rationale"], "audience": idea["audience"],
            "suggested_format": idea["suggested_format"], "status": "new", "run_id": ctx.rec.id,
            "sources": [by_url[u].as_source() for u in idea["source_urls"]],
            "facts": idea["facts"],
        })
    if ideas:
        with storage.transaction("ideas") as doc:
            doc["items"].extend(ideas)
    stage["output"] = {"source_items": len(items), "with_full_text": sum(1 for i in items if i.text),
                       "ideas": [{"id": i["id"], "topic": i["topic"], "facts": len(i["facts"])} for i in ideas]}
    ctx.rec.info(f"research produced {len(ideas)} idea(s)")
    return ideas, stage


def run_strategy(ctx: Context, ideas: list[dict[str, Any]], count: int,
                 manual: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gen = ctx.settings["generation"]
    max_thread = ctx.settings["publishing"]["max_thread_posts"]
    formats = gen["enabled_formats"]
    if manual and manual.get("format") and manual["format"] not in formats:
        formats = formats + [manual["format"]]
    _, _, recent = _recent_context()
    payload = {
        "count": count, "enabled_formats": formats, "max_thread_posts": max_thread,
        "ideas": [{"idea_id": i["id"], "topic": i["topic"], "angle": i.get("angle", ""),
                   "rationale": i.get("rationale", ""), "audience": i.get("audience", ""),
                   "suggested_format": i.get("suggested_format"),
                   "facts": [f["text"] for f in i.get("facts", [])]} for i in ideas],
        "recent_content": recent, "memory": ctx.memory_digest,
    }
    if manual:
        payload["manual_request"] = manual
    validator = agents.content_strategist({i["id"] for i in ideas}, formats, count, max_thread, bool(manual))
    out, stage = ctx.runner.run("content_strategist", payload, validator, stage_name="strategy")
    if manual and manual.get("format"):
        for b in out["briefs"]:  # the owner's explicit format always wins
            b["format"] = manual["format"]
            lo, hi = checks.post_count_bounds(b["format"], max_thread)
            b["post_count"] = min(max(b["post_count"], lo), hi)
    return out["briefs"], stage


# ------------------------------------------------------------------ creation & evaluation

def new_item(*, topic: str, fmt: str, origin: str, tone: str = "", instructions: str = "",
             idea_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    now = utcnow_iso()
    return {"id": new_id("cnt"), "created_at": now, "updated_at": now, "status": "GENERATION",
            "format": fmt, "topic": topic[:300], "angle": "", "tone": tone, "instructions": instructions[:2000],
            "origin": origin, "idea_id": idea_id, "run_id": run_id, "sources": [], "facts": [], "brief": None,
            "draft": None, "draft_en": None, "original_draft": None, "versions": [], "stages": [],
            "evaluation": None, "approval": None, "publishing": None, "content_hash": None,
            "auto_publish": False, "user_notes": None}


def create_content(ctx: Context, brief: dict[str, Any], *, facts: list[dict[str, Any]],
                   sources: list[dict[str, Any]], origin: str, tone: str = "", instructions: str = "",
                   pre_stages: list[dict[str, Any]] | None = None,
                   revision_feedback: list[str] | None = None) -> dict[str, Any]:
    tone = tone or ctx.settings["generation"]["default_tone"]
    item = new_item(topic=brief["topic"], fmt=brief["format"], origin=origin, tone=tone,
                    instructions=instructions, idea_id=brief.get("idea_id"), run_id=ctx.rec.id)
    item.update(angle=brief.get("angle", ""), brief=brief, facts=facts, sources=sources)
    item["stages"].extend(copy.deepcopy(pre_stages or []))
    ctx.rec.content_ids.append(item["id"])
    max_thread = ctx.settings["publishing"]["max_thread_posts"]
    hooks, _, _ = _recent_context()
    try:
        fact_list = _fact_list(item)
        out, stage = ctx.runner.run("content_creator", {
            "brief": brief, "facts": [{k: f[k] for k in ("id", "text", "source_url")} for f in fact_list],
            "instructions": instructions, "recent_hooks": hooks[:20], "memory": ctx.memory_digest,
            "revision_feedback": revision_feedback or [],
        }, agents.content_creator(brief["format"], max_thread, {f["id"] for f in fact_list}),
            stage_name="generation")
        item["stages"].append(stage)
        item["draft_en"] = _draft_of(out)

        out, stage = ctx.runner.run("malay_localizer", {
            "draft_en": item["draft_en"], "tone": tone, "style_examples": "(see system prompt)",
            "revision_feedback": [],
        }, agents.malay_localizer(len(item["draft_en"]["posts"])), stage_name="localization",
            extra_system="# Style examples (match this voice)\n\n" + style_context())
        item["stages"].append(stage)
        item["draft"] = _draft_of(out)
        item["original_draft"] = copy.deepcopy(item["draft"])
        _add_version(item, item["draft"], "malay_localizer", "initial Malay draft")
    except AgentFailure as exc:
        item["stages"].append(exc.stage)
        item["status"] = "FAILED"
        return item
    return evaluate(ctx, item)


def _run_evaluators(ctx: Context, item: dict[str, Any]) -> tuple[dict, dict, list[dict], float]:
    hooks, texts, _ = _recent_context(exclude_id=item["id"])
    draft = item["draft"]
    code_warnings, rep = checks.run_content_checks(
        draft["posts"], draft["hook"], item["format"],
        max_thread_posts=ctx.settings["publishing"]["max_thread_posts"], recent_texts=texts,
        recent_hooks=hooks, repetition_threshold=ctx.settings["publishing"]["repetition_threshold"])
    item["stages"].append(_code_stage("code_checks", {"warnings": code_warnings, "repetition_similarity": rep}))
    q, stage = ctx.runner.run("quality_evaluator", {
        "brief": item.get("brief") or {"topic": item["topic"], "format": item["format"]},
        "draft": draft, "recent_hooks": hooks[:20], "memory": ctx.memory_digest,
    }, agents.quality_evaluator, stage_name="evaluation")
    item["stages"].append(stage)
    facts = _fact_list(item)
    f, stage = ctx.runner.run("fact_checker", {
        "draft": draft, "facts": facts,
        "sources": [{k: s.get(k) for k in ("url", "title", "publisher", "published_at")} for s in item.get("sources", [])],
        "owner_provided_context": item.get("instructions", ""), "today": ctx.today,
    }, agents.fact_checker({fc["source_url"] for fc in facts}), stage_name="fact_check")
    item["stages"].append(stage)
    return q, f, code_warnings, rep


def _evaluation_record(q: dict, f: dict, code_warnings: list[dict], rep: float) -> dict[str, Any]:
    warnings = list(code_warnings)
    warnings += [{**checks.warning(i["code"], i["severity"], i["message"], "quality_evaluator")} for i in q["issues"]]
    for c in f["claims"]:
        if c["verdict"] not in ("supported", "opinion", "hypothetical") and c["severity"] != "low":
            msg = f"{c['verdict']}: {c['text']}" + (f" — fix: {c['fix']}" if c.get("fix") else "")
            warnings.append(checks.warning("FACT_" + c["verdict"].upper(), c["severity"], msg[:500], "fact_checker"))
    return {
        "overall_score": q["overall_score"], "factuality_score": f["factuality_score"],
        "brand_score": q["scores"]["brand_compliance"], "scores": q["scores"],
        "fact_check_status": f["status"], "critical_fact_failure": f["critical_failure"],
        "repetition_similarity": rep, "warnings": warnings, "suggestions": q["suggestions"],
    }


def _needs_refinement(ev: dict[str, Any], quality: dict[str, Any]) -> bool:
    return (ev["overall_score"] < quality["min_overall"] or ev["factuality_score"] < quality["min_factuality"]
            or ev["brand_score"] < quality["min_brand"] or ev["fact_check_status"] != "passed"
            or any(w["severity"] in ("high", "critical") for w in ev["warnings"]))


def evaluate(ctx: Context, item: dict[str, Any], *, user_notes: str | None = None,
             force_edit: bool = False) -> dict[str, Any]:
    """Evaluate (and if needed refine once) the item's current draft, then route it."""
    quality = ctx.settings["quality"]
    item["status"] = "EVALUATION"
    try:
        q, f, code_w, rep = _run_evaluators(ctx, item)
        ev = _evaluation_record(q, f, code_w, rep)
        rounds = quality["max_refinement_rounds"] if not force_edit else max(1, quality["max_refinement_rounds"])
        while rounds > 0 and (force_edit or _needs_refinement(ev, quality)):
            rounds -= 1
            item["status"] = "REFINEMENT"
            out, stage = ctx.runner.run("content_editor", {
                "brief": item.get("brief") or {"topic": item["topic"], "format": item["format"],
                                               "post_count": len(item["draft"]["posts"])},
                "draft": item["draft"], "quality": q, "fact_check": f, "min_overall": quality["min_overall"],
                "facts": [{k: x[k] for k in ("id", "text", "source_url")} for x in _fact_list(item)],
                "code_checks": code_w, "user_notes": user_notes or "",
            }, agents.content_editor(item["format"], len(item["draft"]["posts"]),
                                     ctx.settings["publishing"]["max_thread_posts"]), stage_name="refinement")
            item["stages"].append(stage)
            force_edit = False
            if not out["changed"]:
                break
            item["draft"] = _draft_of(out)
            _add_version(item, item["draft"], "content_editor", "; ".join(out["change_summary"])[:300])
            if ctx.client.remaining < 2:
                ev["warnings"].append(checks.warning("NOT_REEVALUATED", "high",
                                                     "Edited after evaluation; AI budget too low to re-check"))
                break
            q, f, code_w, rep = _run_evaluators(ctx, item)
            ev = _evaluation_record(q, f, code_w, rep)
    except AgentFailure as exc:
        item["stages"].append(exc.stage)
        item["status"] = "FAILED"
        return item

    item["evaluation"] = ev
    item["content_hash"] = content_hash(item["draft"]["posts"])
    item["approval"] = {"required": True, "decision": None, "decided_at": None, "reason": None, "approval_id": None}
    item["status"] = "PENDING_APPROVAL"
    if auto_publish_allowed(ctx.settings):
        verdict = gate.auto_publish_quality_gate(item, ctx.settings)
        if verdict.allowed:
            item["status"] = "READY_TO_PUBLISH"
            item["auto_publish"] = True
            item["approval"]["required"] = False
            ctx.rec.info(f"{item['id']}: passed auto-publish gate")
        else:
            ctx.rec.info(f"{item['id']}: held for human approval — " + "; ".join(verdict.reasons)[:300])
    return item


# ------------------------------------------------------------------ entry points

def run_daily(ctx: Context) -> list[dict[str, Any]]:
    count = ctx.settings["generation"]["items_per_daily_run"]
    if count <= 0:
        ctx.rec.info("items_per_daily_run is 0; nothing to do")
        return []
    ideas, research_stage = run_research(ctx, max_ideas=max(3, count))
    if not ideas:
        return []
    try:
        briefs, strategy_stage = run_strategy(ctx, ideas, count)
    except AgentFailure:
        return []
    by_id = {i["id"]: i for i in ideas}
    produced = []
    for brief in briefs:
        idea = by_id[brief["idea_id"]]
        item = create_content(ctx, brief, facts=idea["facts"], sources=idea["sources"], origin="scheduled",
                              pre_stages=[research_stage, strategy_stage])
        upsert_content(item)
        _mark_idea(idea["id"], "used")
        produced.append(item)
        ctx.rec.info(f"{item['id']}: {item['status']}")
    return produced


def run_manual(ctx: Context, *, topic: str, fmt: str, tone: str = "", instructions: str = "",
               regenerate_of: str | None = None, feedback: list[str] | None = None) -> dict[str, Any] | None:
    topic = topic.strip()
    if not topic:
        raise ValueError("topic is required")
    stages: list[dict[str, Any]] = []
    try:
        ideas, stage = run_research(ctx, focus=[topic], max_ideas=2)
        stages.append(stage)
    except AgentFailure as exc:
        ideas = []
        stages.append(exc.stage)
        ctx.rec.warn("research failed; writing without fresh sources (opinion/evergreen only)")
    facts = [f for i in ideas for f in i["facts"]][:8]
    sources = [s for i in ideas for s in i["sources"]][:6]
    manual = {"topic": topic, "format": fmt, "tone": tone, "instructions": instructions}
    try:
        briefs, stage = run_strategy(ctx, ideas, 1, manual=manual)
        stages.append(stage)
        brief = briefs[0]
    except AgentFailure as exc:
        stages.append(exc.stage)
        lo, _ = checks.post_count_bounds(fmt, ctx.settings["publishing"]["max_thread_posts"])
        brief = {"idea_id": None, "topic": topic, "angle": "", "format": fmt, "post_count": max(lo, 4 if fmt == "thread" else 1),
                 "audience": "general", "hook_strategy": "", "key_points": [], "cta_direction": "", "avoid": [],
                 "rationale": "strategist unavailable; using the manual request directly"}
    brief["topic"] = topic
    item = create_content(ctx, brief, facts=facts, sources=sources,
                          origin="manual_workflow", tone=tone, instructions=instructions,
                          pre_stages=stages, revision_feedback=feedback)
    upsert_content(item)
    for idea in ideas:
        _mark_idea(idea["id"], "used")
    if regenerate_of:
        archive_with_note(regenerate_of, f"regenerated as {item['id']}")
    return item


def evaluate_existing(ctx: Context, content_id: str, *, user_notes: str | None = None,
                      force_edit: bool = False) -> dict[str, Any]:
    item = storage.find_item(storage.load("content"), content_id)
    if item is None:
        raise ValueError(f"content {content_id} not found")
    if not item.get("draft"):
        raise ValueError("content has no draft to evaluate")
    ctx.rec.content_ids.append(content_id)
    item["user_notes"] = user_notes
    item = evaluate(ctx, item, user_notes=user_notes, force_edit=force_edit)
    upsert_content(item)
    return item


def archive_with_note(content_id: str, note: str) -> None:
    with storage.transaction("content") as doc:
        item = storage.find_item(doc, content_id)
        if item and item["status"] not in ("PUBLISHED", "PUBLISHING", "PUBLISH_UNCERTAIN"):
            item["status"] = "ARCHIVED"
            item["user_notes"] = note[:2000]
            item["updated_at"] = utcnow_iso()


def _mark_idea(idea_id: str, status: str) -> None:
    with storage.transaction("ideas") as doc:
        idea = storage.find_item(doc, idea_id)
        if idea:
            idea["status"] = status
            idea["updated_at"] = utcnow_iso()
