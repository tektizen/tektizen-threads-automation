"""OpenRouter chat-completions client (OpenAI-compatible).

* Per-run request budget: every HTTP attempt counts, retries included.
* Bounded retries with exponential backoff on 429 / 5xx / timeouts only.
* Refuses paid models unless settings explicitly allow them; never falls back
  to another model on its own.
* Never logs the API key.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 60.0


class OpenRouterError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class BudgetExceeded(OpenRouterError):
    pass


@dataclass
class Completion:
    content: str
    model: str
    usage: dict[str, int | None]
    provider: str | None = None


@dataclass
class UsageTotals:
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    models: list[str] = field(default_factory=list)


def is_free_model(model: str) -> bool:
    return model == "openrouter/free" or model.endswith(":free")


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, *, max_requests: int = 20, timeout: float = 90,
                 max_retries: int = 2, allow_paid_models: bool = False,
                 session: requests.Session | None = None, sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self.max_requests = max_requests
        self.timeout = timeout
        self.max_retries = max_retries
        self.allow_paid_models = allow_paid_models
        self.session = session or requests.Session()
        self.sleep = sleep
        self.totals = UsageTotals()

    @classmethod
    def from_settings(cls, ai: dict[str, Any], **kwargs: Any) -> "OpenRouterClient":
        return cls(max_requests=ai["max_requests_per_run"], timeout=ai["timeout_seconds"],
                   max_retries=ai.get("max_retries", 2), allow_paid_models=ai.get("allow_paid_models", False),
                   **kwargs)

    @property
    def remaining(self) -> int:
        return self.max_requests - self.totals.requests

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if os.environ.get("OPENROUTER_APP_URL"):
            headers["HTTP-Referer"] = os.environ["OPENROUTER_APP_URL"]
        headers["X-Title"] = os.environ.get("OPENROUTER_APP_NAME", "TektiZen Content Intelligence")
        return headers

    def chat(self, messages: list[dict[str, str]], *, model: str, temperature: float = 0.7,
             max_tokens: int = 1800) -> Completion:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        if not self.allow_paid_models and not is_free_model(model):
            raise OpenRouterError(f"model {model!r} is not a free model and paid models are disabled in settings")
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        last_error: OpenRouterError | None = None
        for attempt in range(self.max_retries + 1):
            if self.totals.requests >= self.max_requests:
                raise BudgetExceeded(f"request budget of {self.max_requests} per run exhausted")
            self.totals.requests += 1
            try:
                return self._attempt(payload)
            except OpenRouterError as exc:
                last_error = exc
                if not exc.retryable or attempt == self.max_retries:
                    raise
                self.sleep(self._backoff(attempt, getattr(exc, "retry_after", None)))
        raise last_error or OpenRouterError("unreachable")

    @staticmethod
    def _backoff(attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(max(retry_after, 1.0), MAX_BACKOFF_SECONDS)
        return min(2.0 * (2 ** attempt), MAX_BACKOFF_SECONDS)

    def _attempt(self, payload: dict[str, Any]) -> Completion:
        try:
            resp = self.session.post(f"{BASE_URL}/chat/completions", headers=self._headers(),
                                     json=payload, timeout=self.timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise OpenRouterError(f"network error: {type(exc).__name__}", retryable=True) from exc

        if resp.status_code != 200:
            err = OpenRouterError(f"HTTP {resp.status_code}: {_error_message(resp)}",
                                  status=resp.status_code, retryable=resp.status_code in RETRYABLE_STATUS)
            ra = resp.headers.get("Retry-After")
            err.retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None  # type: ignore[attr-defined]
            raise err
        try:
            data = resp.json()
        except ValueError as exc:
            raise OpenRouterError("malformed JSON response from OpenRouter", retryable=True) from exc

        # OpenRouter can return 200 with an error object (e.g. upstream provider failure).
        if isinstance(data, dict) and data.get("error"):
            error = data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
            code = error.get("code")
            raise OpenRouterError(f"provider error: {str(error.get('message'))[:300]}",
                                  status=code if isinstance(code, int) else None,
                                  retryable=code in RETRYABLE_STATUS or code is None)
        try:
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise OpenRouterError("response missing choices[0].message", retryable=True) from exc
        if not content.strip():
            raise OpenRouterError(f"empty completion (finish_reason={choice.get('finish_reason')})", retryable=True)

        usage_raw = data.get("usage") or {}
        usage = {k: usage_raw.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        model = str(data.get("model") or payload["model"])
        self.totals.prompt_tokens += usage["prompt_tokens"] or 0
        self.totals.completion_tokens += usage["completion_tokens"] or 0
        self.totals.total_tokens += usage["total_tokens"] or 0
        if model not in self.totals.models:
            self.totals.models.append(model)
        return Completion(content=content, model=model, usage=usage, provider=data.get("provider"))


def _error_message(resp: requests.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return str(msg)[:300]
    except ValueError:
        return resp.text[:300]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply (tolerates fences, preambles, <think> blocks)."""
    text = _THINK.sub("", text).strip()
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        start = candidate.find("{")
        if start == -1:
            continue
        # Walk to the matching closing brace, respecting strings.
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(candidate[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(candidate[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
    raise ValueError("no JSON object found in model output")
