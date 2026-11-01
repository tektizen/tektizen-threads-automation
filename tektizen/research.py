"""News collection: RSS/Atom feeds + Hacker News, scored and enriched with full article text.

All of this is plain code; no AI calls. The Trend Researcher agent only ever
sees items fetched here, with their real URLs and retrieval timestamps.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from .util import iso, utcnow

log = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (compatible; TektiZenBot/1.0; "
              "+https://github.com/tektizen/tektizen-threads-automation)")
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
TIER_WEIGHT = {"official": 3.0, "malaysia": 2.6, "media": 2.0, "community": 1.0}
MALAYSIA_TERMS = ("malaysia", "malaysian", "kuala lumpur", "mdec", "selangor", "penang", "johor",
                  "asean", "singapore", "ringgit", "rm", "kerajaan", "mcmc")
PRACTICAL_TERMS = ("how to", "tips", "guide", "free", "workflow", "productivity", "office", "student",
                   "small business", "sme", "freelance", "automation", "excel", "sheets", "email",
                   "cara", "percuma", "pelajar", "pekerja", "perniagaan")


@dataclass
class SourceItem:
    url: str
    title: str
    publisher: str
    tier: str
    language: str
    retrieved_at: str
    published_at: str | None = None
    summary: str = ""
    text: str = ""
    score: float = 0.0
    signals: dict[str, Any] = field(default_factory=dict)

    def as_source(self) -> dict[str, Any]:
        """Shape stored on ideas/content (schemas: source)."""
        out = {"url": self.url, "title": self.title, "publisher": self.publisher,
               "published_at": self.published_at, "retrieved_at": self.retrieved_at}
        if self.summary:
            out["summary"] = self.summary[:500]
        return out

    def for_agent(self, include_text: bool) -> dict[str, Any]:
        out = {"url": self.url, "title": self.title, "publisher": self.publisher, "tier": self.tier,
               "published_at": self.published_at, "summary": self.summary[:400]}
        if include_text and self.text:
            out["text"] = self.text
        return out


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#8217;|&rsquo;", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_time(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    lowered = f" {text.lower()} "
    for kw in keywords:
        k = kw.lower()
        if len(k) <= 3:  # short tokens like "AI" must match as whole words
            if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", lowered):
                return True
        elif k in lowered:
            return True
    return False


class Fetcher:
    def __init__(self, session: requests.Session | None = None, timeout: float = 20):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.timeout = timeout

    def get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=self.timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp


def fetch_feed(fetcher: Fetcher, feed: dict[str, Any], *, keywords: list[str], max_items: int,
               max_age_days: int, now: datetime) -> list[SourceItem]:
    import feedparser

    resp = fetcher.get(feed["url"])
    parsed = feedparser.parse(resp.content)
    cutoff = now - timedelta(days=max_age_days)
    retrieved = iso(now)
    items: list[SourceItem] = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = _clean_html(entry.get("title", ""))
        if not link or not title or not link.startswith("http"):
            continue
        published = _entry_time(entry)
        if published and published < cutoff:
            continue
        summary = _clean_html(entry.get("summary", ""))[:600]
        if feed.get("ai_only") and not _matches_keywords(f"{title} {summary}", keywords):
            continue
        publisher = feed["name"]
        source = entry.get("source")
        if isinstance(source, dict) and source.get("title"):  # Google News: real publisher
            publisher = source["title"]
        items.append(SourceItem(url=link, title=title, publisher=publisher, tier=feed.get("tier", "media"),
                                language=feed.get("language", "en"), retrieved_at=retrieved,
                                published_at=iso(published) if published else None, summary=summary))
        if len(items) >= max_items:
            break
    return items


def fetch_hn(fetcher: Fetcher, *, max_age_days: int, now: datetime, limit: int = 15) -> list[SourceItem]:
    since = int((now - timedelta(days=min(max_age_days, 3))).timestamp())
    resp = fetcher.get(f"{HN_SEARCH}?tags=story&query=AI&hitsPerPage={limit}"
                       f"&numericFilters=points%3E80,created_at_i%3E{since}")
    retrieved = iso(now)
    items = []
    for hit in resp.json().get("hits", []):
        url, title = hit.get("url"), hit.get("title")
        if not url or not title:
            continue
        items.append(SourceItem(url=url, title=title, publisher="Hacker News discussion", tier="community",
                                language="en", retrieved_at=retrieved, published_at=hit.get("created_at"),
                                signals={"hn_points": hit.get("points", 0), "hn_comments": hit.get("num_comments", 0)}))
    return items


def score_item(item: SourceItem, *, now: datetime, max_age_days: int, keywords: list[str]) -> float:
    score = TIER_WEIGHT.get(item.tier, 1.0)
    if item.published_at:
        try:
            age_h = (now - datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))).total_seconds() / 3600
            score += max(0.0, 2.0 * (1 - age_h / (max_age_days * 24)))
        except ValueError:
            pass
    text = f"{item.title} {item.summary}".lower()
    if any(t in text for t in MALAYSIA_TERMS) or item.language == "ms":
        score += 1.5
    if any(t in text for t in PRACTICAL_TERMS):
        score += 0.8
    if _matches_keywords(text, keywords):
        score += 0.7
    points = item.signals.get("hn_points") or 0
    score += min(points / 300, 1.5)
    if "news.google.com" in item.url:
        score -= 2.0  # discovery only: redirect links, no extractable article text
    return round(score, 3)


def dedupe(items: list[SourceItem], *, exclude_urls: set[str], recent_titles: list[str]) -> list[SourceItem]:
    from .checks import similarity

    seen_urls: set[str] = set()
    kept: list[SourceItem] = []
    for item in sorted(items, key=lambda i: -i.score):
        url_key = item.url.split("?")[0].rstrip("/")
        if url_key in seen_urls or item.url in exclude_urls or url_key in exclude_urls:
            continue
        if any(similarity(item.title, k.title) > 0.5 for k in kept):
            continue
        if any(similarity(item.title, t) > 0.6 for t in recent_titles):
            continue
        seen_urls.add(url_key)
        kept.append(item)
    return kept


def diversify(items: list[SourceItem], limit: int, per_publisher: int = 2) -> list[SourceItem]:
    """Keep the ranking but cap items per publisher so one busy feed can't crowd out the rest."""
    counts: dict[str, int] = {}
    out = []
    for item in items:
        key = item.publisher.lower()
        if counts.get(key, 0) >= per_publisher:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(item)
        if len(out) >= limit:
            break
    return out


def extract_text(fetcher: Fetcher, url: str, max_chars: int) -> str:
    import trafilatura

    resp = fetcher.get(url)
    text = trafilatura.extract(resp.text, include_comments=False, include_tables=False, favor_precision=True) or ""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def collect(research: dict[str, Any], *, used_urls: set[str], recent_titles: list[str],
            fetcher: Fetcher | None = None, now: datetime | None = None,
            log_fn: Callable[[str, str], None] | None = None) -> list[SourceItem]:
    """Fetch every enabled source, score, dedupe, and attach full text to the top items."""
    fetcher = fetcher or Fetcher()
    now = now or utcnow()
    say = log_fn or (lambda level, msg: log.log(logging.WARNING if level == "warning" else logging.INFO, msg))
    keywords = research.get("keywords", [])
    max_age = research["max_age_days"]
    items: list[SourceItem] = []
    for feed in research["feeds"]:
        if not feed.get("enabled", True):
            continue
        try:
            got = fetch_feed(fetcher, feed, keywords=keywords, max_items=research["max_items_per_feed"],
                             max_age_days=max_age, now=now)
            say("info", f"feed {feed['name']}: {len(got)} items")
            items.extend(got)
        except Exception as exc:  # one bad feed must not stop research
            say("warning", f"feed {feed['name']} failed: {type(exc).__name__}: {str(exc)[:150]}")
    if research.get("hn_enabled", True):
        try:
            got = fetch_hn(fetcher, max_age_days=max_age, now=now)
            say("info", f"Hacker News: {len(got)} items")
            items.extend(got)
        except Exception as exc:
            say("warning", f"Hacker News failed: {type(exc).__name__}")
    for item in items:
        item.score = score_item(item, now=now, max_age_days=max_age, keywords=keywords)
    ranked = diversify(dedupe(items, exclude_urls=used_urls, recent_titles=recent_titles),
                       research.get("max_candidates", 12))

    want = research.get("fulltext_articles", 4)
    got_text = 0
    for item in ranked:
        if got_text >= want:
            break
        if "news.google.com" in item.url:
            continue  # Google News links are JS redirects; no extractable text
        try:
            item.text = extract_text(fetcher, item.url, research.get("fulltext_max_chars", 2500))
            if len(item.text) >= 300:
                got_text += 1
            else:
                item.text = ""
        except Exception as exc:
            say("warning", f"full text failed for {item.url[:80]}: {type(exc).__name__}")
    say("info", f"research: {len(items)} fetched, {len(ranked)} candidates, {got_text} with full text")
    return ranked
