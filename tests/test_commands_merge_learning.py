from __future__ import annotations

import copy
import json

import pytest

from tektizen import commands, learning, merge, pipeline, storage
from tektizen.runs import RunRecorder
from tektizen.settings import AUTO_PUBLISH, default_settings, load_settings

from .fakes import FakeLLM
from .test_publishing import POST, _item, _store


def _apply(cmd, actor="tester"):
    return commands.apply_command(cmd, actor, load_settings())


# ---------------------------------------------------------------- commands

def test_approve_moves_to_ready_and_logs(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    _store(item)
    res = _apply({"type": "approve", "content_id": item["id"]})
    assert res["publish"] is True
    saved = storage.find_item(storage.load("content"), item["id"])
    assert saved["status"] == "READY_TO_PUBLISH" and saved["approval"]["decision"] == "approved"
    log = storage.load("approvals")["items"][0]
    assert log["action"] == "approve" and log["actor"] == "tester" and saved["approval"]["approval_id"] == log["id"]


def test_approve_blocked_by_critical_fact_failure(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    item["evaluation"]["critical_fact_failure"] = True
    _store(item)
    with pytest.raises(commands.CommandError, match="critical"):
        _apply({"type": "approve", "content_id": item["id"]})
    assert storage.find_item(storage.load("content"), item["id"])["status"] == "PENDING_APPROVAL"
    assert storage.load("approvals")["items"][0]["status"] == "rejected_invalid"


def test_reject_requires_reason_and_stores_it(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    _store(item)
    with pytest.raises(commands.CommandError, match="reason"):
        _apply({"type": "reject", "content_id": item["id"]})
    _apply({"type": "reject", "content_id": item["id"], "reason": "Terlalu formal, guna korang"})
    saved = storage.find_item(storage.load("content"), item["id"])
    assert saved["status"] == "REJECTED" and saved["approval"]["reason"] == "Terlalu formal, guna korang"


def test_cannot_approve_published_or_rejected(repo):
    pub, rej = _item(status="PUBLISHED"), _item(status="REJECTED")
    _store(pub, rej)
    for it in (pub, rej):
        with pytest.raises(commands.CommandError):
            _apply({"type": "approve", "content_id": it["id"]})


def test_edit_approve_keeps_original_and_validates(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    _store(item)
    with pytest.raises(commands.CommandError, match="500"):
        _apply({"type": "edit_approve", "content_id": item["id"], "posts": ["x" * 600]})
    _apply({"type": "edit_approve", "content_id": item["id"], "posts": ["Versi baru yang lebih santai untuk korang"]})
    saved = storage.find_item(storage.load("content"), item["id"])
    assert saved["status"] == "READY_TO_PUBLISH"
    assert saved["original_draft"]["posts"] == [POST]
    assert saved["draft"]["posts"] == ["Versi baru yang lebih santai untuk korang"]


def test_edit_approve_with_critical_failure_requires_recheck(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    item["evaluation"]["critical_fact_failure"] = True
    _store(item)
    res = _apply({"type": "edit_approve", "content_id": item["id"], "posts": ["Versi tanpa statistik palsu"]})
    assert res["publish"] is False and res["ai"]["op"] == "evaluate" and res["ai"]["then_approve"]


def test_switching_to_auto_requires_confirmation(repo):
    with pytest.raises(commands.CommandError, match="confirmation"):
        _apply({"type": "update_settings", "patch": {"approval": {"mode": AUTO_PUBLISH}}})
    assert load_settings()["approval"]["mode"] == "human_approval"
    _apply({"type": "update_settings", "patch": {"approval": {"mode": AUTO_PUBLISH}}, "confirm_auto_publish": True})
    s = load_settings()
    assert s["approval"]["mode"] == AUTO_PUBLISH and s["approval"]["auto_publish_enabled_by"] == "tester"


def test_invalid_settings_patch_rejected(repo):
    with pytest.raises(commands.CommandError):
        _apply({"type": "update_settings", "patch": {"quality": {"min_overall": 500}}})
    with pytest.raises(commands.CommandError):
        _apply({"type": "update_settings", "patch": {"publishing": {"kill_switch": "yes"}}})


def test_memory_commands(repo):
    _apply({"type": "memory_add", "category": "preferred_styles", "text": "Guna 'korang', bukan 'anda'"})
    item = storage.load("learning_memory")["categories"]["preferred_styles"][0]
    assert item["source"] == "user"
    _apply({"type": "memory_update", "category": "preferred_styles", "item_id": item["id"], "confidence": "high"})
    with pytest.raises(commands.CommandError, match="confirm"):
        _apply({"type": "memory_reset", "category": "preferred_styles"})
    _apply({"type": "memory_delete", "category": "preferred_styles", "item_id": item["id"]})
    assert storage.load("learning_memory")["categories"]["preferred_styles"] == []


def test_prompt_update_validated_and_written(repo):
    with pytest.raises(commands.CommandError, match="missing sections"):
        _apply({"type": "update_prompt", "agent": "content_creator", "markdown": "# Agent: X\n\n## Role\n\nhi"})
    md = (repo / "agents/prompts/content_creator.md").read_text(encoding="utf-8") + "\n<!-- edited -->\n"
    _apply({"type": "update_prompt", "agent": "content_creator", "markdown": md})
    assert "<!-- edited -->" in (repo / "agents/prompts/content_creator.md").read_text(encoding="utf-8")
    with pytest.raises(commands.CommandError):
        _apply({"type": "update_prompt", "agent": "../../x", "markdown": md})


def test_save_draft_and_submit(repo):
    res = _apply({"type": "save_draft", "topic": "Prompt", "format": "single", "posts": ["Draf pertama korang"]})
    saved = storage.find_item(storage.load("content"), res["content_id"])
    assert saved["status"] == "DRAFT" and saved["origin"] == "studio"
    res = _apply({"type": "submit_for_review", "content_id": saved["id"]})
    assert res["ai"] == {"op": "evaluate", "content_id": saved["id"], "user_notes": "", "force_edit": False}


def test_reconcile_not_published_allows_retry_with_new_key(repo):
    item = _item(status="PUBLISH_UNCERTAIN", publishing={"zernio_post_id": "x", "key_generation": 0})
    _store(item)
    res = _apply({"type": "reconcile_publish", "content_id": item["id"], "resolution": "not_published"})
    saved = storage.find_item(storage.load("content"), item["id"])
    assert res["publish"] and saved["status"] == "READY_TO_PUBLISH" and saved["publishing"]["key_generation"] == 1


def test_unknown_command_rejected(repo):
    with pytest.raises(commands.CommandError):
        _apply({"type": "rm -rf"})


# ---------------------------------------------------------------- merge driver

def _doc(items):
    return {"schema_version": 1, "updated_at": "2026-11-01T00:00:00Z", "items": items}


def test_merge_keeps_concurrent_additions_and_edits():
    a, b = _item(status="PENDING_APPROVAL"), _item(status="PENDING_APPROVAL")
    base = _doc([a, b])
    ours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    ours["items"][0]["status"] = "READY_TO_PUBLISH"
    ours["items"][0]["updated_at"] = "2026-11-01T10:00:01Z"
    theirs["items"][1]["status"] = "REJECTED"
    theirs["items"][1]["updated_at"] = "2026-11-01T10:00:02Z"
    new_ours, new_theirs = _item(), _item()
    ours["items"].append(new_ours)
    theirs["items"].append(new_theirs)
    merged = merge.merge_documents("content", base, ours, theirs)
    by_id = {i["id"]: i for i in merged["items"]}
    assert by_id[a["id"]]["status"] == "READY_TO_PUBLISH" and by_id[b["id"]]["status"] == "REJECTED"
    assert new_ours["id"] in by_id and new_theirs["id"] in by_id


def test_merge_same_record_both_sides_prefers_newer():
    a = _item(status="PENDING_APPROVAL")
    base = _doc([a])
    ours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    ours["items"][0].update(status="ARCHIVED", updated_at="2026-11-01T10:00:00Z")
    theirs["items"][0].update(status="READY_TO_PUBLISH", updated_at="2026-11-01T11:00:00Z")
    assert merge.merge_documents("content", base, ours, theirs)["items"][0]["status"] == "READY_TO_PUBLISH"


def test_merge_counters_add_deltas():
    base = {"schema_version": 1, "updated_at": None, "agents": {"fact_checker": {"executions": 5, "successes": 5, "failures": 0}}}
    ours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    ours["agents"]["fact_checker"].update(executions=7, successes=7)
    theirs["agents"]["fact_checker"].update(executions=6, failures=1)
    merged = merge.merge_documents("agent_metrics", base, ours, theirs)
    assert merged["agents"]["fact_checker"] == {"executions": 8, "successes": 7, "failures": 1}


def test_merge_driver_files(tmp_path):
    a = _item()
    base, ours, theirs = _doc([a]), _doc([a, _item()]), _doc([a, _item()])
    paths = {}
    for name, doc in (("base", base), ("ours", ours), ("theirs", theirs)):
        paths[name] = tmp_path / name
        paths[name].write_text(json.dumps(doc), encoding="utf-8")
    assert merge.run_driver(str(paths["base"]), str(paths["ours"]), str(paths["theirs"]), "data/content.json") == 0
    assert len(json.loads(paths["ours"].read_text(encoding="utf-8"))["items"]) == 3
    paths["theirs"].write_text("{broken", encoding="utf-8")
    assert merge.run_driver(str(paths["base"]), str(paths["ours"]), str(paths["theirs"]), "data/content.json") == 1


# ---------------------------------------------------------------- learning

def test_learning_skips_ai_without_new_signals(repo):
    llm = FakeLLM()
    ctx = pipeline.build_context(RunRecorder("t", "local"), client=llm, settings=default_settings())
    assert learning.run_learning(ctx.rec, ctx.runner) == 0
    assert llm.calls == []


def test_learning_applies_capped_operations(repo):
    item = _item(status="PENDING_APPROVAL", decision=None)
    _store(item)
    _apply({"type": "reject", "content_id": item["id"], "reason": "Terlalu formal"})
    apr = storage.load("approvals")["items"][0]["id"]
    llm = FakeLLM({"learning_analyst": {"operations": [
        {"op": "add", "category": "rejection_feedback", "text": "Owner rejects formal register",
         "confidence": "high", "evidence_ids": [apr]}], "notes": "one signal"}})
    ctx = pipeline.build_context(RunRecorder("t", "local"), client=llm, settings=default_settings())
    assert learning.run_learning(ctx.rec, ctx.runner) == 1
    mem = storage.load("learning_memory")
    stored = mem["categories"]["rejection_feedback"][0]
    assert stored["confidence"] == "low" and stored["evidence_ids"] == [apr]
    assert mem["last_analysis_at"]
    # Nothing new since → no second AI call
    assert learning.run_learning(ctx.rec, ctx.runner) == 0 and len(llm.calls) == 1


def test_run_recorder_persists_on_failure(repo):
    from tektizen.runs import recorded_run

    with pytest.raises(RuntimeError):
        with recorded_run("unit-test", trigger="local") as rec:
            rec.agent_result("fact_checker", False, 10, "boom")
            raise RuntimeError("x")
    run = storage.load("automation_runs")["items"][0]
    assert run["status"] == "failed" and "RuntimeError" in run["errors"][0]
    assert storage.load("agent_metrics")["agents"]["fact_checker"]["failures"] == 1
