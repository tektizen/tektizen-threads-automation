from __future__ import annotations

import pytest
import requests

from integrations import zernio_client as zc
from tektizen import storage
from tektizen.publishing import gate, publisher
from tektizen.runs import RunRecorder
from tektizen.settings import AUTO_PUBLISH, default_settings
from tektizen.util import new_id, utcnow_iso

from .fakes import FakeResponse, FakeSession

POST = "Pening tulis formula lagi? Sekarang Sheets boleh tolong korang."


def _published_body(post_id="65f1c0a9e2b5af0012ab34cd"):
    return {"message": "Post published successfully", "post": {
        "_id": post_id, "status": "published",
        "platforms": [{"platform": "threads", "accountId": {"_id": "acc"}, "status": "published",
                       "platformPostId": "3456789", "platformPostUrl": "https://threads.net/@tektizen/post/ABC"}]}}


def _settings(**pub):
    s = default_settings()
    s["publishing"].update({"threads_account_id": "66b2e19d8c3f5a7e9d0b1c2d", "max_posts_per_run": 3, **pub})
    return s


def _item(status="READY_TO_PUBLISH", posts=None, decision="approved", **extra):
    now = utcnow_iso()
    posts = posts or [POST]
    item = {"id": new_id("cnt"), "created_at": now, "updated_at": now, "status": status,
            "format": "thread" if len(posts) > 1 else "single", "topic": "t", "origin": "scheduled",
            "draft": {"hook": "h", "body": "b", "cta": "c", "posts": posts},
            "evaluation": {"overall_score": 92, "factuality_score": 100, "brand_score": 95,
                           "fact_check_status": "passed", "critical_fact_failure": False, "warnings": []},
            "approval": {"required": decision is not None, "decision": decision, "decided_at": now},
            "publishing": None, "auto_publish": decision is None}
    item.update(extra)
    return item


def _store(*items):
    with storage.transaction("content") as doc:
        doc["items"].extend(items)


# ---------------------------------------------------------------- Zernio client

def test_payload_single_and_thread():
    single = zc.build_post_payload([POST], "acc1")
    assert single == {"content": POST, "platforms": [{"platform": "threads", "accountId": "acc1"}], "publishNow": True}
    thread = zc.build_post_payload(["one", "two", "three"], "acc1")
    items = thread["platforms"][0]["platformSpecificData"]["threadItems"]
    assert items == [{"content": "one"}, {"content": "two"}, {"content": "three"}]
    assert thread["content"] == "one"


def test_payload_rejects_over_limit_and_missing_account():
    with pytest.raises(zc.ZernioError, match="500"):
        zc.build_post_payload(["x" * 501], "acc1")
    with pytest.raises(zc.ZernioError, match="account"):
        zc.build_post_payload([POST], "")


@pytest.mark.parametrize("response, outcome", [
    (FakeResponse(201, _published_body()), zc.PUBLISHED),
    (FakeResponse(201, {"post": {"_id": "p", "status": "publishing", "platforms": [
        {"platform": "threads", "status": "processing"}]}}), zc.UNCERTAIN),
    (FakeResponse(207, {"post": {"_id": "p", "status": "failed", "platforms": [
        {"platform": "threads", "status": "failed", "error": "token expired"}]}}), zc.FAILED),
    (FakeResponse(201, {"message": "weird"}), zc.UNCERTAIN),
    (FakeResponse(201, None, text="<html>"), zc.UNCERTAIN),
    (FakeResponse(409, {"error": "dup", "existingPostId": "old"}), zc.DUPLICATE),
    (FakeResponse(409, {"error": "processing", "code": "idempotency_conflict"}), zc.UNCERTAIN),
    (FakeResponse(429, {"error": "too many"}), zc.RATE_LIMITED),
    (FakeResponse(403, {"error": "no", "code": "ACCOUNT_DISCONNECTED"}), zc.FAILED),
    (FakeResponse(503, {"error": "busy"}), zc.UNCERTAIN),
    (requests.Timeout(), zc.UNCERTAIN),
    (requests.ConnectionError(), zc.UNCERTAIN),
])
def test_publish_outcomes(response, outcome):
    session = FakeSession(response)
    res = zc.ZernioClient("k", session=session).publish([POST], "acc", "tektizen-cnt-0")
    assert res.outcome == outcome
    assert len(session.calls) == 1  # never retried
    assert session.calls[0]["headers"]["Idempotency-Key"] == "tektizen-cnt-0"


def test_publish_success_extracts_ids():
    res = zc.ZernioClient("k", session=FakeSession(FakeResponse(201, _published_body("abc")))).publish([POST], "a", "k")
    assert (res.post_id, res.platform_post_ids, res.url) == ("abc", ["3456789"], "https://threads.net/@tektizen/post/ABC")


def test_analytics_mapping_keeps_unavailable_as_none():
    body = {"analytics": {"views": 1200, "likes": 40, "comments": 0, "shares": 5, "reposts": 0}}
    m = zc.extract_threads_metrics(body)
    assert m["views"] == 1200 and m["replies"] == 0  # a real zero stays zero
    assert m["reposts"] is None and m["quotes"] is None  # not reported on Threads → unavailable
    nested = {"posts": [{"platforms": [{"platform": "x", "likes": 9, "views": 9},
                                       {"platform": "threads", "likes": 3, "views": 7}]}]}
    assert zc.extract_threads_metrics(nested)["likes"] == 3


@pytest.mark.parametrize("status, expected", [(202, "pending"), (402, "unavailable"), (500, "error")])
def test_analytics_statuses(status, expected):
    client = zc.ZernioClient("k", session=FakeSession(FakeResponse(status, {"error": "x"})))
    assert client.get_analytics("p").status == expected


# ---------------------------------------------------------------- gate

def _gate(item, settings, **kw):
    kw.setdefault("published_hashes", set())
    kw.setdefault("published_texts", [])
    kw.setdefault("published_this_run", 0)
    return gate.publish_gate(item, settings, **kw)


def test_gate_allows_human_approved():
    assert _gate(_item(), _settings()).allowed


def test_gate_kill_switch_blocks_everything():
    v = _gate(_item(), _settings(kill_switch=True))
    assert not v.allowed and "kill switch" in v.reasons[0]


def test_gate_blocks_unapproved_in_human_mode_even_if_flagged_auto():
    v = _gate(_item(decision=None), _settings())
    assert not v.allowed and any("auto-publish is not enabled" in r for r in v.reasons)


def test_gate_auto_mode_requires_quality():
    s = _settings()
    s["approval"]["mode"] = AUTO_PUBLISH
    assert _gate(_item(decision=None), s).allowed
    weak = _item(decision=None)
    weak["evaluation"]["factuality_score"] = 70
    weak["evaluation"]["warnings"] = [{"code": "X", "severity": "high", "message": "m", "resolved": False}]
    v = _gate(weak, s)
    assert not v.allowed and any("factuality" in r for r in v.reasons) and any("unresolved" in r for r in v.reasons)


def test_gate_critical_fact_failure_blocks_even_human_approval():
    item = _item()
    item["evaluation"]["critical_fact_failure"] = True
    assert not _gate(item, _settings()).allowed


@pytest.mark.parametrize("status", ["PENDING_APPROVAL", "REJECTED", "ARCHIVED", "FAILED", "DRAFT", "PUBLISHED"])
def test_gate_never_publishes_other_statuses(status):
    assert not _gate(_item(status=status), _settings()).allowed


def test_gate_duplicates_limit_and_missing_account():
    from tektizen.util import content_hash

    item = _item()
    assert not _gate(item, _settings(), published_hashes={content_hash([POST])}).allowed
    assert not _gate(item, _settings(), published_texts=[POST]).allowed
    assert not _gate(item, _settings(max_posts_per_run=1), published_this_run=1).allowed
    assert not _gate(item, _settings(threads_account_id=None)).allowed


# ---------------------------------------------------------------- publisher

def _run(session, settings=None):
    rec = RunRecorder("test", trigger="local")
    return publisher.publish_ready(rec, settings or _settings(), zc.ZernioClient("k", session=session)), rec


def test_publisher_success_records_history(repo):
    item = _item()
    _store(item)
    stats, _ = _run(FakeSession(FakeResponse(201, _published_body())))
    assert stats["published"] == 1
    saved = storage.find_item(storage.load("content"), item["id"])
    assert saved["status"] == "PUBLISHED" and saved["publishing"]["url"].startswith("https://threads.net")
    assert saved["publishing"]["idempotency_key"] == f"tektizen-{item['id']}-0"
    hist = storage.load("publishing_history")["items"]
    assert hist[0]["result"] == "success" and hist[0]["mode"] == "human_approved"


def test_publisher_uncertain_is_not_retried(repo):
    item = _item()
    _store(item)
    session = FakeSession(requests.Timeout())
    _run(session)
    assert storage.find_item(storage.load("content"), item["id"])["status"] == "PUBLISH_UNCERTAIN"
    _run(session)  # a second run must not call the API again (queue is empty → would raise)
    assert len(session.calls) == 1


def test_publisher_recovers_interrupted_run(repo):
    item = _item(status="PUBLISHING")
    _store(item)
    _run(FakeSession())
    assert storage.find_item(storage.load("content"), item["id"])["status"] == "PUBLISH_UNCERTAIN"


def test_publisher_failed_bumps_key_and_rate_limit_keeps_ready(repo):
    a, b = _item(), _item(posts=["Another different post about AI tools for students"])
    _store(a, b)
    _run(FakeSession(FakeResponse(400, {"error": "bad"}), FakeResponse(429, {"error": "slow"})))
    sa = storage.find_item(storage.load("content"), a["id"])
    sb = storage.find_item(storage.load("content"), b["id"])
    assert sa["status"] == "FAILED" and sa["publishing"]["key_generation"] == 1
    assert sb["status"] == "READY_TO_PUBLISH"


def test_publisher_respects_per_run_limit(repo):
    _store(_item(), _item(posts=["Totally different second post about automation"]))
    session = FakeSession(FakeResponse(201, _published_body("a")))
    stats, _ = _run(session, _settings(max_posts_per_run=1))
    assert stats["published"] == 1 and stats["blocked"] == 1 and len(session.calls) == 1


def test_reconcile_uses_read_only_status(repo):
    item = _item(status="PUBLISH_UNCERTAIN", publishing={"zernio_post_id": "abc", "attempts": 1})
    _store(item)
    session = FakeSession(FakeResponse(200, _published_body("abc")))
    publisher.reconcile_uncertain(RunRecorder("t", "local"), zc.ZernioClient("k", session=session))
    assert storage.find_item(storage.load("content"), item["id"])["status"] == "PUBLISHED"
    assert session.calls[0]["method"] == "GET"
