"""Agent runner and per-agent output validators.

Each agent = Markdown prompt (agents/prompts/<name>.md) + a validator here.
Validators normalise the model output and return a list of errors. On errors
the runner makes at most one repair request, then fails the stage.

Anything that can be computed in code (overall score, fact-check status,
confidence caps) is recomputed here rather than trusted from the model.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import checks, prompts
from .memory import CONFIDENCE_LEVELS, MEMORY_CATEGORIES
from .openrouter import BudgetExceeded, OpenRouterClient, OpenRouterError, extract_json
from .util import utcnow_iso

Validator = Callable[[dict[str, Any]], list[str]]

AGENT_TEMPERATURE = {
    "quality_evaluator": 0.2, "fact_checker": 0.1, "learning_analyst": 0.3,
    "content_strategist": 0.5, "trend_researcher": 0.4, "content_editor": 0.4,
    "malay_localizer": 0.6, "content_creator": 0.8,
}

QUALITY_WEIGHTS = {
    "brand_compliance": 0.15, "hook_strength": 0.15, "specificity": 0.15, "natural_language": 0.10,
    "audience_relevance": 0.10, "originality": 0.10, "topic_relevance": 0.10, "readability": 0.05,
    "engagement_potential": 0.05, "cta_quality": 0.05,
}
SEVERITIES = ("low", "medium", "high", "critical")
FACT_VERDICTS = ("supported", "unsupported", "contradicted", "outdated", "opinion", "hypothetical")
FACT_PENALTY = {"critical": 40, "high": 20, "medium": 8, "low": 2}
FORMATS = ("single", "thread", "question", "opinion", "educational", "storytelling",
           "tools_recommendation", "news_commentary")


class AgentFailure(Exception):
    def __init__(self, message: str, stage: dict[str, Any]):
        super().__init__(message)
        self.stage = stage


class AgentRunner:
    def __init__(self, client: OpenRouterClient, settings: dict[str, Any], recorder: Any):
        self.client = client
        self.settings = settings
        self.rec = recorder

    def model_for(self, agent: str) -> str:
        ai = self.settings["ai"]
        return ai.get("agent_models", {}).get(agent) or ai["model"]

    def run(self, agent: str, payload: dict[str, Any], validator: Validator, *,
            stage_name: str | None = None, extra_system: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (validated output, stage record). Raises AgentFailure with the stage record."""
        stage: dict[str, Any] = {"stage": stage_name or agent, "agent": agent, "status": "failed",
                                 "started_at": utcnow_iso(), "completed_at": None, "model": None,
                                 "usage": None, "output": None, "error": None}
        model = self.model_for(agent)
        try:
            system = prompts.build_system_prompt(agent)
        except prompts.PromptError as exc:
            return self._fail(stage, f"prompt error: {exc}")
        if extra_system:
            system += "\n\n---\n\n" + extra_system
        user = ("Input:\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n```\n\n"
                "Return ONLY the JSON object described in the Output Format section. No explanations.")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        temperature = AGENT_TEMPERATURE.get(agent, self.settings["ai"]["temperature"])
        usage_total = 0
        errors: list[str] = []
        for attempt in range(2):  # first try + at most one repair
            try:
                completion = self.client.chat(messages, model=model, temperature=temperature,
                                              max_tokens=self.settings["ai"]["max_tokens"])
            except BudgetExceeded as exc:
                return self._fail(stage, str(exc))
            except OpenRouterError as exc:
                return self._fail(stage, f"OpenRouter: {exc}")
            stage["model"] = completion.model
            usage_total += completion.usage.get("total_tokens") or 0
            stage["usage"] = {**completion.usage, "total_tokens": usage_total or None, "attempts": attempt + 1}
            try:
                output = extract_json(completion.content)
                errors = validator(output)
            except ValueError as exc:
                output, errors = None, [str(exc)]
            if not errors and output is not None:
                stage.update(status="success", output=output, completed_at=utcnow_iso())
                self.rec.agent_result(agent, True, usage_total)
                self.rec.info(f"{agent}: ok ({completion.model}, {usage_total or '?'} tokens)")
                return output, stage
            self.rec.warn(f"{agent}: invalid output (attempt {attempt + 1}): {'; '.join(errors)[:300]}")
            if attempt == 0 and self.client.remaining > 0:
                messages += [{"role": "assistant", "content": completion.content[:6000]},
                             {"role": "user", "content": "Your output was invalid:\n- " + "\n- ".join(errors[:10])
                              + "\n\nReturn the corrected JSON object only."}]
        return self._fail(stage, "invalid output: " + "; ".join(errors)[:500])

    def _fail(self, stage: dict[str, Any], error: str):
        stage.update(status="failed", error=error[:1000], completed_at=utcnow_iso())
        self.rec.agent_result(stage["agent"], False, (stage.get("usage") or {}).get("total_tokens"), error)
        self.rec.error(f"{stage['agent']}: {error[:300]}")
        raise AgentFailure(error, stage)


# ---------------------------------------------------------------- validators

def _str(d: dict[str, Any], key: str, errors: list[str], *, required: bool = True, max_len: int = 4000) -> str:
    value = d.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        errors.append(f"{key} must be a non-empty string")
        return ""
    return value.strip()[:max_len]


def trend_researcher(source_text: dict[str, str], max_ideas: int) -> Validator:
    """source_text maps each allowed URL to the text (full text or summary) the agent saw."""
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        ideas = out.get("ideas")
        if not isinstance(ideas, list):
            return ["ideas must be a list"]
        kept = []
        for idea in ideas[:max_ideas]:
            if not isinstance(idea, dict):
                continue
            e: list[str] = []
            topic = _str(idea, "topic", e, max_len=200)
            urls = [u for u in idea.get("source_urls") or [] if u in source_text]
            if not urls:
                e.append("no valid source_urls")
            facts = []
            for f in idea.get("facts") or []:
                if not isinstance(f, dict) or not isinstance(f.get("text"), str):
                    continue
                url = f.get("source_url")
                if url not in source_text:
                    continue
                quote = str(f.get("quote") or "")
                facts.append({"text": f["text"].strip()[:400], "quote": quote[:300], "source_url": url,
                              "verified_quote": checks.quote_found(quote, source_text[url])})
            verified = [f for f in facts if f["verified_quote"]]
            if not verified:
                e.append(f"idea '{topic[:40]}' has no fact whose quote appears in its source")
            if e:
                errors.extend(e)
                continue
            fmt = idea.get("suggested_format")
            kept.append({"topic": topic, "angle": str(idea.get("angle") or "")[:400],
                         "rationale": str(idea.get("rationale") or "")[:600],
                         "audience": str(idea.get("audience") or "general")[:40],
                         "suggested_format": fmt if fmt in FORMATS else None,
                         "source_urls": urls, "facts": verified[:8]})
        out["ideas"] = kept
        # Partial success is fine; only fail when the model proposed ideas and none survived.
        return errors if (ideas and not kept) else []
    return validate


def content_strategist(idea_ids: set[str], enabled_formats: list[str], count: int,
                       max_thread_posts: int, manual: bool) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        briefs = out.get("briefs")
        if not isinstance(briefs, list) or not briefs:
            return ["briefs must be a non-empty list"]
        clean = []
        for b in briefs[:count]:
            if not isinstance(b, dict):
                errors.append("brief must be an object")
                continue
            e: list[str] = []
            idea_id = b.get("idea_id")
            if not manual and idea_id not in idea_ids:
                e.append(f"idea_id {idea_id!r} is not one of the provided ideas")
            fmt = b.get("format")
            if fmt not in enabled_formats:
                e.append(f"format {fmt!r} is not enabled")
            topic = _str(b, "topic", e, max_len=300)
            lo, hi = checks.post_count_bounds(fmt or "single", max_thread_posts)
            try:
                post_count = int(b.get("post_count") or lo)
            except (TypeError, ValueError):
                post_count = lo
            if e:
                errors.extend(e)
                continue
            clean.append({
                "idea_id": idea_id if not manual else None, "topic": topic,
                "angle": str(b.get("angle") or "")[:400], "format": fmt,
                "post_count": min(max(post_count, lo), hi), "audience": str(b.get("audience") or "general")[:40],
                "hook_strategy": str(b.get("hook_strategy") or "")[:300],
                "key_points": [str(k)[:300] for k in (b.get("key_points") or [])][:8],
                "cta_direction": str(b.get("cta_direction") or "")[:300],
                "avoid": [str(k)[:200] for k in (b.get("avoid") or [])][:8],
                "rationale": str(b.get("rationale") or "")[:600],
            })
        out["briefs"] = clean
        return errors if not clean else []
    return validate


def _draft(out: dict[str, Any], errors: list[str]) -> None:
    for key in ("hook", "body", "cta"):
        value = out.get(key)
        out[key] = value.strip() if isinstance(value, str) else ""
    if not out["hook"]:
        errors.append("hook is required")
    posts = out.get("posts")
    if isinstance(posts, list):
        out["posts"] = [p.strip() for p in posts if isinstance(p, str) and p.strip()]


def content_creator(fmt: str, max_thread_posts: int, fact_ids: set[int]) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        _draft(out, errors)
        # post_count is guidance; any thread length within bounds is accepted.
        errors += checks.check_posts_shape(out.get("posts"), fmt, max_thread_posts, checks.EN_DRAFT_MAX_CHARS)
        claims = []
        for c in out.get("claims") or []:
            if isinstance(c, dict) and isinstance(c.get("text"), str):
                fid = c.get("fact_id")
                if fid is not None and fid not in fact_ids:
                    errors.append(f"claim references unknown fact_id {fid}")
                claims.append({"text": c["text"][:400], "fact_id": fid})
        out["claims"] = claims
        return errors
    return validate


def malay_localizer(expected_posts: int) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        _draft(out, errors)
        posts = out.get("posts")
        if not isinstance(posts, list) or len(posts) != expected_posts:
            errors.append(f"must return exactly {expected_posts} posts")
        else:
            errors += [e for e in checks.check_posts_shape(posts, "thread" if expected_posts > 1 else "single", 20)
                       if "characters" in e or "empty" in e]
        indo = checks.find_indonesian("\n".join(posts or []))
        if indo:
            errors.append("replace Indonesian vocabulary: " + ", ".join(f"{w}→{checks.INDONESIAN_VOCAB[w]}" for w in indo))
        return errors
    return validate


def quality_evaluator(out: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    scores = out.get("scores")
    if not isinstance(scores, dict):
        return ["scores must be an object"]
    clean: dict[str, float] = {}
    for key in QUALITY_WEIGHTS:
        value = scores.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            errors.append(f"scores.{key} must be a number 0-100")
        else:
            clean[key] = float(value)
    if errors:
        return errors
    out["scores"] = clean
    out["overall_score"] = round(sum(clean[k] * w for k, w in QUALITY_WEIGHTS.items()))
    issues = []
    for i in out.get("issues") or []:
        if isinstance(i, dict) and i.get("severity") in SEVERITIES and isinstance(i.get("message"), str):
            issues.append({"code": str(i.get("code") or "OTHER")[:40], "severity": i["severity"],
                           "message": i["message"][:400]})
    out["issues"] = issues
    out["suggestions"] = [str(s)[:400] for s in (out.get("suggestions") or []) if isinstance(s, str)][:8]
    return []


def fact_checker(fact_urls: set[str]) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        claims = out.get("claims")
        if not isinstance(claims, list):
            return ["claims must be a list"]
        clean = []
        for c in claims:
            if not isinstance(c, dict):
                continue
            verdict, severity = c.get("verdict"), c.get("severity")
            if verdict not in FACT_VERDICTS or severity not in SEVERITIES:
                errors.append(f"invalid verdict/severity: {verdict!r}/{severity!r}")
                continue
            url = c.get("source_url")
            if verdict == "supported" and url not in fact_urls:
                # A "supported" verdict must point at real evidence; otherwise it's unverified.
                verdict, severity = "unsupported", "high" if severity in ("low", "medium") else severity
            clean.append({"text": str(c.get("text") or "")[:400], "verdict": verdict, "severity": severity,
                          "source_url": url if url in fact_urls else None,
                          "fix": (str(c["fix"])[:400] if c.get("fix") else None)})
        if errors:
            return errors
        fab_stats = bool(out.get("fabricated_statistics"))
        fab_exp = bool(out.get("fabricated_experience"))
        critical = fab_stats or fab_exp or any(c["severity"] == "critical" for c in clean)
        score = 100
        for c in clean:
            if c["verdict"] not in ("supported", "opinion", "hypothetical") or c["severity"] in ("critical", "high"):
                score -= FACT_PENALTY[c["severity"]]
        if fab_stats or fab_exp:
            score = min(score, 60)
        out.update(claims=clean, fabricated_statistics=fab_stats, fabricated_experience=fab_exp,
                   critical_failure=critical, factuality_score=max(0, score),
                   summary=str(out.get("summary") or "")[:500])
        has_issue = any(c["severity"] in ("high", "medium") and c["verdict"] not in ("supported", "opinion", "hypothetical")
                        for c in clean)
        out["status"] = "failed" if critical else ("warnings" if has_issue else "passed")
        return []
    return validate


def content_editor(fmt: str, expected_posts: int, max_thread_posts: int) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(out.get("changed"), bool):
            errors.append("changed must be true or false")
        _draft(out, errors)
        errors += checks.check_posts_shape(out.get("posts"), fmt, max_thread_posts)
        if fmt == "thread" and isinstance(out.get("posts"), list) and len(out["posts"]) != expected_posts:
            errors.append(f"keep exactly {expected_posts} posts")
        out["change_summary"] = [str(s)[:300] for s in (out.get("change_summary") or [])][:12]
        return errors
    return validate


def evidence_confidence_cap(evidence_count: int) -> str:
    if evidence_count >= 5:
        return "high"
    if evidence_count >= 3:
        return "medium"
    return "low"


def learning_analyst(evidence_ids: set[str]) -> Validator:
    def validate(out: dict[str, Any]) -> list[str]:
        ops = out.get("operations")
        if not isinstance(ops, list):
            return ["operations must be a list"]
        clean = []
        for op in ops[:8]:
            if not isinstance(op, dict) or op.get("op") not in ("add", "reinforce"):
                continue
            if op.get("category") not in MEMORY_CATEGORIES:
                continue
            text = str(op.get("text") or "").strip()
            if not 3 <= len(text) <= 300:
                continue
            ev = [e for e in (op.get("evidence_ids") or []) if e in evidence_ids]
            if not ev:
                continue  # no evidence → not a learning
            wanted = op.get("confidence") if op.get("confidence") in CONFIDENCE_LEVELS else "low"
            cap = evidence_confidence_cap(len(set(ev)))
            confidence = min(wanted, cap, key=CONFIDENCE_LEVELS.index)
            clean.append({"op": "add", "category": op["category"], "text": text,
                          "confidence": confidence, "evidence_ids": sorted(set(ev))})
        out["operations"] = clean
        out["notes"] = str(out.get("notes") or "")[:500]
        return []
    return validate
