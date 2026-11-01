"""Settings with fail-safe defaults.

Safety invariant: anything other than an explicit, valid ``"auto_publish"``
approval mode is treated as human approval. A missing, unreadable, or invalid
settings file can never enable automatic publishing.
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any

from . import storage

HUMAN_APPROVAL = "human_approval"
AUTO_PUBLISH = "auto_publish"

ALL_FORMATS = [
    "single", "thread", "question", "opinion", "educational",
    "storytelling", "tools_recommendation", "news_commentary",
]

_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "updated_at": None,
    "approval": {
        "mode": HUMAN_APPROVAL,
        "auto_publish_enabled_at": None,
        "auto_publish_enabled_by": None,
    },
    "publishing": {
        "kill_switch": False,
        "max_posts_per_run": 1,
        "threads_account_id": None,
        "threads_username": "tektizen",
        "max_thread_posts": 6,
        "repetition_threshold": 0.6,
    },
    "ai": {
        "model": "openrouter/free",
        "temperature": 0.7,
        "max_tokens": 1800,
        "timeout_seconds": 90,
        "max_requests_per_run": 20,
        "max_retries": 2,
        "allow_paid_models": False,
        "agent_models": {},
    },
    "quality": {
        "min_overall": 80,
        "min_factuality": 90,
        "min_brand": 90,
        "max_refinement_rounds": 1,
    },
    "generation": {
        "items_per_daily_run": 1,
        "default_tone": "santai tapi berilmu",
        "enabled_formats": list(ALL_FORMATS),
        "topics": [
            "AI untuk pekerja pejabat",
            "AI untuk pelajar",
            "AI untuk freelancer",
            "AI untuk perniagaan kecil Malaysia",
            "AI untuk content creator",
            "Automasi kerja harian",
            "Produktiviti digital",
        ],
    },
    "research": {
        # Verified reachable 2026-11-01. `ai_only` feeds are filtered by `keywords`.
        "feeds": [
            {"name": "OpenAI News", "url": "https://openai.com/news/rss.xml",
             "tier": "official", "language": "en", "enabled": True},
            {"name": "Google AI Blog", "url": "https://blog.google/innovation-and-ai/technology/ai/rss/",
             "tier": "official", "language": "en", "enabled": True},
            {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml",
             "tier": "official", "language": "en", "enabled": True},
            {"name": "GitHub Blog", "url": "https://github.blog/feed/",
             "tier": "official", "language": "en", "enabled": True, "ai_only": True},
            {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
             "tier": "media", "language": "en", "enabled": True},
            {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
             "tier": "media", "language": "en", "enabled": True},
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
             "tier": "media", "language": "en", "enabled": True, "ai_only": True},
            {"name": "MIT Technology Review AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
             "tier": "media", "language": "en", "enabled": True},
            {"name": "Amanz", "url": "https://cms.amanz.my/feed/",
             "tier": "malaysia", "language": "ms", "enabled": True, "ai_only": True},
            {"name": "SoyaCincau", "url": "https://soyacincau.com/feed/",
             "tier": "malaysia", "language": "en", "enabled": True, "ai_only": True},
            {"name": "Lowyat.NET", "url": "https://www.lowyat.net/feed/",
             "tier": "malaysia", "language": "en", "enabled": True, "ai_only": True},
            {"name": "Google News — AI Malaysia",
             "url": "https://news.google.com/rss/search?q=artificial+intelligence+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
             "tier": "malaysia", "language": "en", "enabled": True},
            {"name": "Google News — Kecerdasan Buatan",
             "url": "https://news.google.com/rss/search?q=kecerdasan+buatan&hl=ms-MY&gl=MY&ceid=MY:ms",
             "tier": "malaysia", "language": "ms", "enabled": True},
        ],
        "hn_enabled": True,
        "keywords": [
            "AI", "artificial intelligence", "kecerdasan buatan", "ChatGPT", "OpenAI", "Gemini", "Claude",
            "Copilot", "LLM", "chatbot", "automation", "automasi", "machine learning", "generative",
            "agent", "prompt", "Perplexity", "DeepSeek", "Llama", "Qwen",
        ],
        "max_items_per_feed": 8,
        "max_age_days": 7,
        "max_candidates": 12,
        "fulltext_articles": 4,
        "fulltext_max_chars": 2500,
    },
}


def default_settings() -> dict[str, Any]:
    return copy.deepcopy(_DEFAULTS)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key != "agent_models":
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_settings() -> dict[str, Any]:
    """Load settings; missing keys fall back to defaults. Raises DataError on a corrupt file."""
    stored = storage.load("settings")
    merged = _merge(_DEFAULTS, stored)
    storage.validate("settings", merged)
    return merged


def approval_mode(settings: dict[str, Any] | None) -> str:
    try:
        mode = settings["approval"]["mode"]  # type: ignore[index]
    except (TypeError, KeyError):
        return HUMAN_APPROVAL
    return AUTO_PUBLISH if mode == AUTO_PUBLISH else HUMAN_APPROVAL


def auto_publish_allowed(settings: dict[str, Any] | None) -> bool:
    """True only when auto mode is explicitly on and the kill switch is off."""
    if approval_mode(settings) != AUTO_PUBLISH:
        return False
    return publishing_enabled(settings)


_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def threads_account_id(settings: dict[str, Any] | None) -> str | None:
    """Zernio account ID: the THREADS_ACCOUNT_ID repository variable wins; settings.json is a fallback."""
    env = os.environ.get("THREADS_ACCOUNT_ID", "").strip()
    if env:
        return env if _ACCOUNT_ID.match(env) else None
    try:
        value = settings["publishing"].get("threads_account_id")  # type: ignore[index]
    except (TypeError, KeyError, AttributeError):
        return None
    return value if isinstance(value, str) and _ACCOUNT_ID.match(value) else None


def publishing_enabled(settings: dict[str, Any] | None) -> bool:
    try:
        return settings["publishing"]["kill_switch"] is False  # type: ignore[index]
    except (TypeError, KeyError):
        return False
