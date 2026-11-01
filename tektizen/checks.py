"""Deterministic content checks — enforced in code, independent of model quality."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .util import normalize_text

THREADS_MAX_CHARS = 500
EN_DRAFT_MAX_CHARS = 450  # prompt asks for 380; a little slack before rejecting

# Indonesian words that have a different Malaysian equivalent. Matched as whole words.
INDONESIAN_VOCAB = {
    "bisa": "boleh", "kamu": "korang/anda", "gimana": "macam mana", "banget": "sangat",
    "nggak": "tak", "gak": "tak", "enggak": "tak", "aja": "je", "udah": "dah", "kayak": "macam",
    "karena": "kerana/sebab", "berhasil": "berjaya", "kantor": "pejabat", "karyawan": "pekerja",
    "perusahaan": "syarikat", "uang": "duit", "ponsel": "telefon", "unduh": "muat turun",
    "mengunduh": "muat turun", "unggah": "muat naik", "mengunggah": "muat naik", "silakan": "sila",
    "dong": "(buang)", "sih": "(buang)", "kok": "(buang)", "segalanya": "semuanya", "nonton": "tengok",
    "cewek": "perempuan", "cowok": "lelaki", "bikin": "buat", "pengen": "nak",
    "lho": "(buang)", "kalian": "korang",
}

ROBOTIC_PHRASES = [
    "dalam era digital", "tidak dapat dinafikan", "justeru itu", "sesungguhnya", "mari kita terokai",
    "telah merevolusikan", "adalah dimaklumkan", "game-changer", "game changer", "unlock potensi",
    "revolusioner", "tahukah anda", "dalam dunia yang serba", "kesimpulannya",
]

def warning(code: str, severity: str, message: str, agent: str = "code_checks") -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "agent": agent, "resolved": False}


def post_count_bounds(fmt: str, max_thread_posts: int) -> tuple[int, int]:
    if fmt == "thread":
        return 2, max_thread_posts
    return 1, 1


def check_posts_shape(posts: list[str], fmt: str, max_thread_posts: int,
                      max_chars: int = THREADS_MAX_CHARS) -> list[str]:
    errors = []
    if not isinstance(posts, list) or not posts or not all(isinstance(p, str) for p in posts):
        return ["posts must be a non-empty list of strings"]
    lo, hi = post_count_bounds(fmt, max_thread_posts)
    if not lo <= len(posts) <= hi:
        errors.append(f"format {fmt!r} needs {lo}-{hi} posts, got {len(posts)}")
    for i, post in enumerate(posts, 1):
        if not post.strip():
            errors.append(f"post {i} is empty")
        if len(post) > max_chars:
            errors.append(f"post {i} is {len(post)} characters (max {max_chars})")
    return errors


def find_indonesian(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for word in INDONESIAN_VOCAB:
        if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", lowered):
            found.append(word)
    return found


def find_robotic(text: str) -> list[str]:
    lowered = text.lower()
    return [p for p in ROBOTIC_PHRASES if p in lowered]


def _shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = normalize_text(text).split()
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def max_similarity(text: str, others: Iterable[str]) -> float:
    return max((similarity(text, o) for o in others), default=0.0)


def run_content_checks(posts: list[str], hook: str, fmt: str, *, max_thread_posts: int,
                       recent_texts: list[str], recent_hooks: list[str],
                       repetition_threshold: float) -> tuple[list[dict[str, Any]], float]:
    """Return (warnings, repetition similarity) for final Bahasa Melayu content."""
    warnings: list[dict[str, Any]] = []
    for err in check_posts_shape(posts, fmt, max_thread_posts):
        warnings.append(warning("FORMAT_INVALID", "critical", err))
    full = "\n".join(posts)
    indo = find_indonesian(full)
    if indo:
        fixes = ", ".join(f"{w}→{INDONESIAN_VOCAB[w]}" for w in indo)
        warnings.append(warning("INDONESIAN_VOCAB", "high", f"Indonesian vocabulary: {fixes}"))
    robotic = find_robotic(full)
    if robotic:
        warnings.append(warning("ROBOTIC_PHRASING", "medium", "Robotic/generic phrasing: " + ", ".join(robotic)))
    rep = max_similarity(full, recent_texts)
    if rep >= repetition_threshold:
        warnings.append(warning("REPETITIVE", "high",
                                f"Content is {rep:.0%} similar to a recent post (threshold {repetition_threshold:.0%})"))
    hook_rep = max_similarity(hook, recent_hooks) if hook.strip() else 0.0
    if hook_rep >= 0.5:
        warnings.append(warning("REPEATED_HOOK", "high", f"Hook is {hook_rep:.0%} similar to a recent hook"))
    return warnings, round(rep, 3)


def quote_found(quote: str, source_text: str, min_ratio: float = 0.7) -> bool:
    """Fuzzy check that a 'quoted' fact really appears in the fetched source text."""
    q = normalize_text(quote).split()
    if len(q) < 3:
        return False
    src = normalize_text(source_text)
    if " ".join(q) in src:
        return True
    src_words = set(src.split())
    return sum(1 for w in q if w in src_words) / len(q) >= min_ratio and _has_run(q, src, 4)


def _has_run(words: list[str], src: str, n: int) -> bool:
    return any(" ".join(words[i:i + n]) in src for i in range(max(1, len(words) - n + 1)))
