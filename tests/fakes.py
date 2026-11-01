"""Test doubles for OpenRouter and HTTP."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import requests

from tektizen.openrouter import Completion, UsageTotals


class FakeResponse:
    def __init__(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None, text: str | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")
        self.content = self.text.encode()

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records requests."""

    def __init__(self, *responses: Any):
        self.queue = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def _next(self, method: str, url: str, **kw: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kw})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url: str, **kw: Any) -> Any:
        return self._next("POST", url, **kw)

    def get(self, url: str, **kw: Any) -> Any:
        return self._next("GET", url, **kw)


GOOD_POST = ("Pening tulis formula lagi? Sekarang Sheets boleh tolong.\n\nGemini dalam Google Sheets boleh tukar ayat "
             "biasa jadi formula. Ciri ni untuk akaun Workspace business.\n\nFormula mana paling buat korang pening?")


def default_responses() -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {
        "trend_researcher": lambda p: {"ideas": [{
            "topic": "Gemini dalam Google Sheets", "angle": "Jimat masa admin", "rationale": "Ramai guna Workspace",
            "audience": "office_workers", "suggested_format": "educational",
            "source_urls": [p["source_items"][0]["url"]],
            "facts": [{"text": "Gemini in Sheets generates formulas from plain language.",
                       "quote": "Gemini in Google Sheets can generate formulas from a plain-language description",
                       "source_url": p["source_items"][0]["url"]}]}]},
        "content_strategist": lambda p: {"briefs": [{
            "idea_id": p["ideas"][0]["idea_id"] if p["ideas"] else None, "topic": "Gemini dalam Google Sheets",
            "angle": "Jimat masa", "format": "educational", "post_count": 1, "audience": "office_workers",
            "hook_strategy": "situasi spesifik", "key_points": ["a"], "cta_direction": "tanya", "avoid": []}]},
        "content_creator": lambda p: {"hook": "Stuck on formulas?", "body": "Gemini in Sheets helps.",
                                      "cta": "Which formula?", "posts": ["Stuck on formulas? Gemini in Sheets helps. Which formula?"],
                                      "claims": [{"text": "Gemini in Sheets helps", "fact_id": 0}]},
        "malay_localizer": lambda p: {"hook": "Pening tulis formula lagi?", "body": "Gemini boleh tolong.",
                                      "cta": "Formula mana paling buat korang pening?", "posts": [GOOD_POST] * len(p["draft_en"]["posts"])},
        "quality_evaluator": lambda p: {"scores": {k: 92 for k in (
            "brand_compliance", "topic_relevance", "hook_strength", "specificity", "readability",
            "natural_language", "audience_relevance", "engagement_potential", "originality", "cta_quality")},
            "overall_score": 10, "issues": [], "suggestions": []},
        "fact_checker": lambda p: {"claims": [{"text": "Gemini boleh tukar ayat jadi formula", "verdict": "supported",
                                               "severity": "low", "source_url": p["facts"][0]["source_url"] if p["facts"] else None,
                                               "fix": None}],
                                   "fabricated_statistics": False, "fabricated_experience": False,
                                   "critical_failure": False, "status": "passed", "factuality_score": 100, "summary": "ok"},
        "content_editor": lambda p: {"changed": False, **p["draft"], "change_summary": []},
        "learning_analyst": lambda p: {"operations": [], "notes": "thin evidence"},
    }


class FakeLLM:
    """Stands in for OpenRouterClient; dispatches on the agent named in the system prompt."""

    def __init__(self, overrides: dict[str, Any] | None = None, max_requests: int = 50):
        self.handlers = default_responses()
        self.handlers.update(overrides or {})
        self.max_requests = max_requests
        self.totals = UsageTotals()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def remaining(self) -> int:
        return self.max_requests - self.totals.requests

    def chat(self, messages, *, model, temperature=0.7, max_tokens=1800) -> Completion:
        from tektizen.openrouter import BudgetExceeded

        if self.totals.requests >= self.max_requests:
            raise BudgetExceeded("budget")
        self.totals.requests += 1
        agent = re.search(r"# Agent: (.+)", messages[0]["content"]).group(1).strip().lower().replace(" ", "_")
        payload = json.loads(re.search(r"```json\n(.*)\n```", messages[1]["content"], re.S).group(1))
        self.calls.append((agent, payload))
        handler = self.handlers[agent]
        out = handler(payload) if callable(handler) else handler
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        self.totals.total_tokens += 100
        return Completion(content=content, model="test/free-model:free",
                          usage={"prompt_tokens": 60, "completion_tokens": 40, "total_tokens": 100})
