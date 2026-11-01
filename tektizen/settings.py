"""Settings with fail-safe defaults.

Safety invariant: anything other than an explicit, valid ``"auto_publish"``
approval mode is treated as human approval. A missing, unreadable, or invalid
settings file can never enable automatic publishing.
"""

from __future__ import annotations

import copy
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
        "feeds": [
            {"name": "Google News — AI Malaysia (EN)",
             "url": "https://news.google.com/rss/search?q=artificial+intelligence+Malaysia&hl=en-MY&gl=MY&ceid=MY:en",
             "enabled": True},
            {"name": "Google News — Kecerdasan Buatan (BM)",
             "url": "https://news.google.com/rss/search?q=kecerdasan+buatan&hl=ms&gl=MY&ceid=MY:ms",
             "enabled": True},
            {"name": "TechCrunch — AI",
             "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "enabled": True},
            {"name": "The Verge — AI",
             "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "enabled": True},
            {"name": "SoyaCincau", "url": "https://soyacincau.com/feed/", "enabled": True},
        ],
        "max_items_per_feed": 8,
        "max_age_days": 7,
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


def publishing_enabled(settings: dict[str, Any] | None) -> bool:
    try:
        return settings["publishing"]["kill_switch"] is False  # type: ignore[index]
    except (TypeError, KeyError):
        return False
