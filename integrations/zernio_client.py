"""Zernio API client for Threads publishing and analytics.

This is the ONLY module that knows Zernio's request/response shapes. Verified
against https://docs.zernio.com on 2026-11-01:

* Base URL https://zernio.com/api/v1, header ``Authorization: Bearer <key>``.
* ``GET /v1/accounts?platform=threads`` → ``{"accounts": [{"_id", "platform", "username", ...}]}``.
* ``POST /v1/posts`` with ``platforms: [{platform, accountId, platformSpecificData}]``,
  ``publishNow: true``. A Threads sequence uses
  ``platformSpecificData.threadItems = [{content}, ...]`` where item 0 is the root post;
  top-level ``content`` is then display-only.
* ``Idempotency-Key`` header: a retry with the same key within 24h returns the original post.
* 409 = duplicate content (24h hash) or ``idempotency_conflict`` (original still processing).
* ``GET /v1/posts/{id}`` → post status.
* ``GET /v1/analytics?postId=…`` → metrics (``views``, ``likes``, ``comments``, ``shares``, …);
  202 = sync pending; 402 ``analytics_addon_required``.

publish() NEVER retries. Callers must treat ``uncertain`` as "may have been published".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import requests

BASE_URL = "https://zernio.com/api/v1"
THREADS_MAX_CHARS = 500
THREADS_MAX_ITEMS = 20

# Outcomes
PUBLISHED = "published"        # confirmed by the API response
FAILED = "failed"              # definitively NOT published (request rejected)
RATE_LIMITED = "rate_limited"  # rejected before processing; safe to try again later
UNCERTAIN = "uncertain"        # request may have been processed; do not retry blindly
DUPLICATE = "duplicate"        # Zernio says identical content was already posted


class ZernioError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class PublishResult:
    outcome: str
    http_status: int | None = None
    post_id: str | None = None
    platform_post_ids: list[str] = field(default_factory=list)
    url: str | None = None
    error: str | None = None
    raw_status: str | None = None


@dataclass
class AnalyticsResult:
    status: str  # "ok" | "pending" | "unavailable" | "error"
    metrics: dict[str, float | None] | None = None
    error: str | None = None


def validate_posts(posts: list[str], max_items: int = THREADS_MAX_ITEMS) -> list[str]:
    errors = []
    if not isinstance(posts, list) or not posts:
        return ["at least one post is required"]
    if len(posts) > max_items:
        errors.append(f"too many posts in thread ({len(posts)} > {max_items})")
    for i, post in enumerate(posts, 1):
        if not isinstance(post, str) or not post.strip():
            errors.append(f"post {i} is empty")
        elif len(post) > THREADS_MAX_CHARS:
            errors.append(f"post {i} has {len(post)} characters (Threads limit {THREADS_MAX_CHARS})")
    return errors


def build_post_payload(posts: list[str], account_id: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Request body for an immediate Threads post (single) or connected thread (2+ posts)."""
    errors = validate_posts(posts)
    if errors:
        raise ZernioError("; ".join(errors))
    if not account_id:
        raise ZernioError("Threads account ID is not configured")
    platform: dict[str, Any] = {"platform": "threads", "accountId": account_id}
    if len(posts) > 1:
        platform["platformSpecificData"] = {"threadItems": [{"content": p} for p in posts]}
    body: dict[str, Any] = {"content": posts[0], "platforms": [platform], "publishNow": True}
    if metadata:
        body["metadata"] = metadata
    return body


def _error_text(resp: requests.Response) -> tuple[str, str | None]:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300] or f"HTTP {resp.status_code}", None
    if isinstance(body, dict):
        return str(body.get("error") or body.get("message") or body)[:300], body.get("code")
    return str(body)[:300], None


def parse_publish_response(status: int, body: Any) -> PublishResult:
    """Interpret a 2xx create-post response. Success requires explicit 'published' confirmation."""
    post = body.get("post") if isinstance(body, dict) else None
    if not isinstance(post, dict):
        return PublishResult(UNCERTAIN, status, error="response has no 'post' object")
    post_id = post.get("_id") or post.get("id")
    entries = [p for p in post.get("platforms") or [] if isinstance(p, dict) and p.get("platform") == "threads"]
    entry = entries[0] if entries else {}
    post_status = str(post.get("status") or "")
    entry_status = str(entry.get("status") or "")
    ids = [str(entry["platformPostId"])] if entry.get("platformPostId") else []
    url = entry.get("platformPostUrl")
    if post_status == "published" and entry_status in ("published", ""):
        return PublishResult(PUBLISHED, status, post_id, ids, url, raw_status=post_status)
    if post_status == "failed" or entry_status == "failed":
        err = entry.get("error") or entry.get("errorMessage") or body.get("message")
        return PublishResult(FAILED, status, post_id, ids, url, error=str(err)[:300] if err else "Zernio reported failed",
                             raw_status=post_status)
    # publishing / scheduled / partial / pending / processing: the post exists but isn't confirmed.
    return PublishResult(UNCERTAIN, status, post_id, ids, url,
                         error=f"post status '{post_status or '?'}' / threads '{entry_status or '?'}'",
                         raw_status=post_status)


class ZernioClient:
    def __init__(self, api_key: str | None = None, *, timeout: float = 60, session: requests.Session | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("ZERNIO_API_KEY", "")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        if not self.api_key:
            raise ZernioError("ZERNIO_API_KEY is not set")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **(extra or {})}

    def list_accounts(self, platform: str = "threads") -> list[dict[str, Any]]:
        resp = self.session.get(f"{BASE_URL}/accounts", params={"platform": platform},
                                headers=self._headers(), timeout=self.timeout)
        if resp.status_code != 200:
            msg, code = _error_text(resp)
            raise ZernioError(f"list accounts failed: HTTP {resp.status_code}: {msg}", resp.status_code, code)
        accounts = resp.json().get("accounts") or []
        return [{"id": a.get("_id") or a.get("id"), "platform": a.get("platform"), "username": a.get("username"),
                 "display_name": a.get("displayName"), "is_active": a.get("isActive"),
                 "needs_reconnection": a.get("needsReconnection")} for a in accounts if isinstance(a, dict)]

    def publish(self, posts: list[str], account_id: str, idempotency_key: str,
                *, metadata: dict[str, Any] | None = None) -> PublishResult:
        """Publish once. Never retries; see module docstring for outcome semantics."""
        try:
            body = build_post_payload(posts, account_id, metadata=metadata)
            headers = self._headers({"Idempotency-Key": idempotency_key[:255]})
        except ZernioError as exc:
            return PublishResult(FAILED, error=str(exc))  # nothing was sent
        try:
            resp = self.session.post(f"{BASE_URL}/posts", json=body, headers=headers, timeout=self.timeout)
        except requests.Timeout:
            return PublishResult(UNCERTAIN, error="request timed out after sending")
        except requests.ConnectionError as exc:
            # A connection error may happen before or after the server received the request.
            return PublishResult(UNCERTAIN, error=f"connection error: {type(exc).__name__}")

        status = resp.status_code
        if status in (200, 201, 207):
            try:
                data = resp.json()
            except ValueError:
                return PublishResult(UNCERTAIN, status, error="unparseable success response")
            return parse_publish_response(status, data)
        msg, code = _error_text(resp)
        if status == 409:
            if code == "idempotency_conflict":
                return PublishResult(UNCERTAIN, status, error="original request still processing (idempotency_conflict)")
            existing = None
            try:
                existing = resp.json().get("existingPostId")
            except (ValueError, AttributeError):
                pass
            return PublishResult(DUPLICATE, status, post_id=existing, error=f"duplicate content: {msg}")
        if status == 429:
            return PublishResult(RATE_LIMITED, status, error=f"rate limited: {msg}")
        if status in (400, 401, 402, 403, 404, 422):
            return PublishResult(FAILED, status, error=f"{code or 'error'}: {msg}")
        # 5xx and anything unexpected: the write may have completed upstream.
        return PublishResult(UNCERTAIN, status, error=f"HTTP {status}: {msg}")

    def get_post(self, post_id: str) -> PublishResult:
        resp = self.session.get(f"{BASE_URL}/posts/{post_id}", headers=self._headers(), timeout=self.timeout)
        if resp.status_code != 200:
            msg, code = _error_text(resp)
            raise ZernioError(f"get post failed: HTTP {resp.status_code}: {msg}", resp.status_code, code)
        data = resp.json()
        if isinstance(data, dict) and "post" not in data and "_id" in data:
            data = {"post": data}
        return parse_publish_response(200, data)

    def get_analytics(self, post_id: str) -> AnalyticsResult:
        try:
            resp = self.session.get(f"{BASE_URL}/analytics", params={"postId": post_id},
                                    headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            return AnalyticsResult("error", error=type(exc).__name__)
        if resp.status_code == 202:
            return AnalyticsResult("pending")
        if resp.status_code == 402:
            return AnalyticsResult("unavailable", error="analytics add-on required on Zernio plan")
        if resp.status_code != 200:
            msg, _ = _error_text(resp)
            return AnalyticsResult("error", error=f"HTTP {resp.status_code}: {msg}")
        try:
            return AnalyticsResult("ok", metrics=extract_threads_metrics(resp.json()))
        except ValueError as exc:
            return AnalyticsResult("error", error=str(exc))


_METRIC_KEYS = ("views", "likes", "comments", "shares", "impressions", "reposts", "quotes", "replies")


def _find_metrics(node: Any, depth: int = 0) -> dict[str, Any] | None:
    """Locate the dict holding metric counters; prefers a Threads platform entry."""
    if depth > 5:
        return None
    if isinstance(node, dict):
        if node.get("platform") == "threads":
            inner = _find_metrics({k: v for k, v in node.items() if k != "platform"}, depth + 1)
            if inner:
                return inner
        if sum(1 for k in _METRIC_KEYS if isinstance(node.get(k), (int, float))) >= 2:
            return node
        for key in ("analytics", "metrics", "post", "data", "platforms", "posts"):
            if key in node:
                found = _find_metrics(node[key], depth + 1)
                if found:
                    return found
    elif isinstance(node, list):
        threads_first = sorted(node, key=lambda x: 0 if isinstance(x, dict) and x.get("platform") == "threads" else 1)
        for child in threads_first:
            found = _find_metrics(child, depth + 1)
            if found:
                return found
    return None


def extract_threads_metrics(body: Any) -> dict[str, float | None]:
    """Map Zernio fields to TektiZen metrics. Missing → None (unavailable), never 0.

    On Threads Zernio reports replies as ``comments`` and folds reposts into ``shares``;
    there is no separate quotes metric, so ``reposts`` and ``quotes`` stay None unless
    Zernio returns them explicitly.
    """
    found = _find_metrics(body)
    if found is None:
        raise ValueError("no metrics found in analytics response")

    def num(key: str) -> float | None:
        value = found.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    replies = num("replies")
    # Zernio documents `reposts` as always 0 on Threads (folded into shares), so a 0 is not a real zero.
    reposts = num("reposts")
    return {"views": num("views"), "likes": num("likes"),
            "replies": replies if replies is not None else num("comments"),
            "reposts": reposts if reposts else None,
            "quotes": num("quotes"), "shares": num("shares"), "impressions": num("impressions")}
