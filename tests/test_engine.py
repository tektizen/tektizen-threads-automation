from __future__ import annotations

import pytest
import requests

from tektizen import agents, checks, pipeline, storage
from tektizen.openrouter import BudgetExceeded, OpenRouterClient, OpenRouterError, extract_json
from tektizen.research import SourceItem
from tektizen.runs import RunRecorder
from tektizen.settings import AUTO_PUBLISH, default_settings

from .fakes import FakeLLM, FakeResponse, FakeSession

SOURCE_TEXT = ("Starting today, Gemini in Google Sheets can generate formulas from a plain-language description. "
               "The feature is available to Google Workspace business customers.")


# ---------------------------------------------------------------- OpenRouter client

def _ok(content='{"a": 1}'):
    return FakeResponse(200, {"model": "x/y:free", "choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})


def _client(*responses, **kw):
    return OpenRouterClient("key", session=FakeSession(*responses), sleep=lambda s: None, **kw)


def test_openrouter_retries_transient_then_succeeds():
    c = _client(FakeResponse(429, {"error": {"message": "slow down"}}), requests.Timeout(), _ok())
    out = c.chat([{"role": "user", "content": "hi"}], model="openrouter/free")
    assert out.content == '{"a": 1}' and out.model == "x/y:free"
    assert c.totals.requests == 3 and c.totals.total_tokens == 8


def test_openrouter_does_not_retry_client_errors():
    c = _client(FakeResponse(401, {"error": {"message": "bad key"}}))
    with pytest.raises(OpenRouterError, match="401"):
        c.chat([], model="openrouter/free")
    assert c.totals.requests == 1


def test_openrouter_budget_is_enforced_across_retries():
    c = _client(FakeResponse(503, {}), FakeResponse(503, {}), max_requests=2, max_retries=5)
    with pytest.raises(OpenRouterError):
        c.chat([], model="openrouter/free")
    with pytest.raises(BudgetExceeded):
        c.chat([], model="openrouter/free")


def test_openrouter_refuses_paid_models_by_default():
    with pytest.raises(OpenRouterError, match="not a free model"):
        _client().chat([], model="anthropic/claude-opus")


def test_openrouter_200_with_error_body_is_error():
    c = _client(FakeResponse(200, {"error": {"message": "provider down", "code": 400}}), max_retries=0)
    with pytest.raises(OpenRouterError, match="provider down"):
        c.chat([], model="openrouter/free")


@pytest.mark.parametrize("text", [
    '{"ok": true}', 'Sure! Here you go:\n```json\n{"ok": true}\n```', '<think>hmm {no}</think>{"ok": true}',
    'prefix {"ok": true, "s": "brace } in string"} suffix',
])
def test_extract_json_variants(text):
    assert extract_json(text)["ok"] is True


def test_extract_json_rejects_garbage():
    with pytest.raises(ValueError):
        extract_json("no json here")


# ---------------------------------------------------------------- checks & validators

def test_indonesian_vocab_detected_as_whole_words():
    assert set(checks.find_indonesian("Kamu bisa coba aja, karena gampang")) >= {"kamu", "bisa", "aja", "karena"}
    assert checks.find_indonesian("Korang boleh cuba sahaja, kebisaan") == []


def test_content_checks_flag_length_repetition_and_hooks():
    long_post = "x" * 501
    warns, _ = checks.run_content_checks([long_post], "Hook", "single", max_thread_posts=6, recent_texts=[],
                                         recent_hooks=[], repetition_threshold=0.6)
    assert any(w["code"] == "FORMAT_INVALID" and w["severity"] == "critical" for w in warns)
    text = "Ramai guna ChatGPT macam Google taip soalan dapat jawapan habis begitu sahaja"
    warns, rep = checks.run_content_checks([text], "Ramai guna ChatGPT macam Google", "single", max_thread_posts=6,
                                           recent_texts=[text], recent_hooks=["Ramai guna ChatGPT macam Google"],
                                           repetition_threshold=0.6)
    assert rep == 1.0 and {"REPETITIVE", "REPEATED_HOOK"} <= {w["code"] for w in warns}


def test_quote_verification():
    assert checks.quote_found("Gemini in Google Sheets can generate formulas", SOURCE_TEXT)
    assert not checks.quote_found("Gemini replaces all accountants in Malaysia by 2027", SOURCE_TEXT)


def test_quality_validator_recomputes_overall_score():
    out = {"scores": {k: 80 for k in agents.QUALITY_WEIGHTS}, "overall_score": 3, "issues": [
        {"code": "X", "severity": "bogus", "message": "m"}, {"code": "WEAK_HOOK", "severity": "medium", "message": "m"}]}
    assert agents.quality_evaluator(out) == []
    assert out["overall_score"] == 80 and len(out["issues"]) == 1


def test_fact_checker_validator_enforces_consistency():
    v = agents.fact_checker({"https://a"})
    out = {"claims": [{"text": "73% guna AI", "verdict": "unsupported", "severity": "critical", "source_url": None}],
           "critical_failure": False, "status": "passed", "factuality_score": 100}
    assert v(out) == []
    assert out["critical_failure"] is True and out["status"] == "failed" and out["factuality_score"] == 60
    out = {"claims": [{"text": "c", "verdict": "supported", "severity": "low", "source_url": "https://fake"}]}
    v(out)
    assert out["claims"][0]["verdict"] == "unsupported" and out["status"] == "warnings"


def test_researcher_validator_drops_unverifiable_facts():
    v = agents.trend_researcher({"https://s": SOURCE_TEXT}, 3)
    out = {"ideas": [
        {"topic": "Good", "source_urls": ["https://s"], "facts": [
            {"text": "t", "quote": "Gemini in Google Sheets can generate formulas", "source_url": "https://s"},
            {"text": "made up", "quote": "Gemini will cost RM5 per month for students", "source_url": "https://s"}]},
        {"topic": "Invented", "source_urls": ["https://not-fetched"], "facts": []},
    ]}
    assert v(out) == []
    assert len(out["ideas"]) == 1 and len(out["ideas"][0]["facts"]) == 1


def test_learning_validator_caps_confidence_by_evidence():
    v = agents.learning_analyst({"apr_1", "apr_2", "apr_3", "apr_4", "apr_5"})
    out = {"operations": [
        {"op": "add", "category": "rejection_feedback", "text": "Too formal gets rejected", "confidence": "high",
         "evidence_ids": ["apr_1", "apr_2"]},
        {"op": "add", "category": "weak_hooks", "text": "Questions as hooks underperform", "confidence": "high",
         "evidence_ids": ["apr_1", "apr_2", "apr_3", "apr_4", "apr_5"]},
        {"op": "delete", "category": "weak_hooks", "text": "nope", "evidence_ids": ["apr_1"]},
        {"op": "add", "category": "weak_hooks", "text": "No evidence", "confidence": "low", "evidence_ids": ["x"]},
    ]}
    v(out)
    assert [o["confidence"] for o in out["operations"]] == ["low", "high"]


# ---------------------------------------------------------------- pipeline

@pytest.fixture
def fake_research(monkeypatch):
    def collect(research, **kw):
        return [SourceItem(url="https://example.com/gemini-sheets", title="Gemini in Sheets writes formulas",
                           publisher="Google", tier="official", language="en", retrieved_at="2026-11-01T00:00:00Z",
                           published_at="2026-10-31T00:00:00Z", summary="Gemini formulas", text=SOURCE_TEXT)]
    monkeypatch.setattr(pipeline.research, "collect", collect)


def _ctx(llm, settings=None):
    rec = RunRecorder("test", trigger="local")
    return pipeline.build_context(rec, client=llm, settings=settings or default_settings())


def test_daily_pipeline_end_to_end_pending_approval(repo, fake_research):
    llm = FakeLLM()
    items = pipeline.run_daily(_ctx(llm))
    assert len(items) == 1
    item = storage.load("content")["items"][0]
    assert item["status"] == "PENDING_APPROVAL" and item["approval"]["required"] is True
    assert item["draft"]["posts"] and item["draft_en"]["posts"] and item["facts"]
    assert item["evaluation"]["overall_score"] == 92 and item["evaluation"]["fact_check_status"] == "passed"
    assert [s["stage"] for s in item["stages"]][:4] == ["research", "strategy", "generation", "localization"]
    assert [a for a, _ in llm.calls] == ["trend_researcher", "content_strategist", "content_creator",
                                         "malay_localizer", "quality_evaluator", "fact_checker"]
    assert storage.load("ideas")["items"][0]["status"] == "used"
    assert storage.load("ideas")["items"][0]["sources"][0]["retrieved_at"]


def test_auto_mode_marks_ready_only_when_gates_pass(repo, fake_research):
    s = default_settings()
    s["approval"]["mode"] = AUTO_PUBLISH
    items = pipeline.run_daily(_ctx(FakeLLM(), s))
    assert items[0]["status"] == "READY_TO_PUBLISH" and items[0]["auto_publish"] is True

    bad_fc = {"fact_checker": {"claims": [{"text": "73%", "verdict": "unsupported", "severity": "critical",
                                           "source_url": None}], "critical_failure": True}}
    items = pipeline.run_daily(_ctx(FakeLLM(bad_fc), s))
    assert items[0]["status"] == "PENDING_APPROVAL"
    assert items[0]["evaluation"]["critical_fact_failure"] is True


def test_refinement_runs_editor_and_reevaluates(repo, fake_research):
    scores = iter([60, 95])

    def qe(p):
        v = next(scores)
        return {"scores": {k: v for k in agents.QUALITY_WEIGHTS}, "issues": [], "suggestions": ["better hook"]}

    def editor(p):
        return {"changed": True, **p["draft"], "hook": "Hook baru",
                "posts": [p["draft"]["posts"][0].replace("Pening", "Penat")], "change_summary": ["WEAK_HOOK"]}

    llm = FakeLLM({"quality_evaluator": qe, "content_editor": editor})
    item = pipeline.run_daily(_ctx(llm))[0]
    assert item["evaluation"]["overall_score"] == 95
    assert item["draft"]["posts"][0].startswith("Penat")
    assert item["original_draft"]["posts"][0].startswith("Pening")
    assert len(item["versions"]) == 2


def test_agent_failure_marks_item_failed_and_run_continues(repo, fake_research):
    llm = FakeLLM({"malay_localizer": "this is not json"})
    item = pipeline.run_daily(_ctx(llm))[0]
    assert item["status"] == "FAILED"
    assert item["stages"][-1]["status"] == "failed" and item["stages"][-1]["agent"] == "malay_localizer"
    assert [a for a, _ in llm.calls].count("malay_localizer") == 2  # one repair attempt, then stop


def test_budget_exhaustion_fails_gracefully(repo, fake_research):
    item = pipeline.run_daily(_ctx(FakeLLM(max_requests=3)))[0]
    assert item["status"] == "FAILED"
    assert "budget" in item["stages"][-1]["error"]


def test_research_with_no_sources_produces_nothing(repo, monkeypatch):
    monkeypatch.setattr(pipeline.research, "collect", lambda *a, **k: [])
    llm = FakeLLM()
    assert pipeline.run_daily(_ctx(llm)) == []
    assert llm.calls == []  # no unnecessary AI calls


def test_manual_generation_honours_format_and_records(repo, fake_research):
    llm = FakeLLM({"content_creator": lambda p: {
        "hook": "h", "body": "b", "cta": "c", "posts": ["Post one hook", "Post two body", "Post three cta"],
        "claims": []}})
    item = pipeline.run_manual(_ctx(llm), topic="AI untuk pelajar", fmt="thread", instructions="fokus SPM")
    assert item["format"] == "thread" and len(item["draft"]["posts"]) == 3
    assert item["origin"] == "manual_workflow" and item["topic"] == "AI untuk pelajar"
