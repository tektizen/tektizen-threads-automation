"""Small shared helpers: IDs, timestamps, hashing."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _ALPHABET[r] + out
    return out or "0"


def new_id(prefix: str) -> str:
    """Roughly time-sortable unique ID, e.g. ``cnt_mh3k2x1a9f8e7d6c``."""
    if not re.fullmatch(r"[a-z]{2,5}", prefix):
        raise ValueError(f"invalid id prefix: {prefix!r}")
    stamp = _base36(int(time.time() * 1000)).rjust(9, "0")
    rand = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{prefix}_{stamp}{rand}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utcnow_iso() -> str:
    return iso(utcnow())


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(posts: list[str]) -> str:
    """Stable fingerprint of publishable text, used for duplicate-publish prevention."""
    joined = "\n---\n".join(normalize_text(p) for p in posts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
