from __future__ import annotations

import pytest

from tektizen import memory, prompts, storage


def test_memory_add_reinforce_update_delete_reset_with_history(repo):
    with storage.transaction("learning_memory") as doc:
        a = memory.add_item(doc, "weak_hooks", "'Tahukah anda' hooks get rejected", evidence_ids=["apr_aaaaaaaa1"])
        b = memory.add_item(doc, "weak_hooks", "  'tahukah anda' hooks get REJECTED ", evidence_ids=["apr_bbbbbbbb2"])
        assert a is b and a["evidence_count"] == 2
        memory.update_item(doc, "weak_hooks", a["id"], confidence="medium")
        assert a["source"] == "user"
        memory.add_item(doc, "lessons_learned", "Threads under 300 chars read better on mobile")
        memory.delete_item(doc, "lessons_learned", doc["categories"]["lessons_learned"][0]["id"])
        assert memory.reset_category(doc, "weak_hooks") == 1
    doc = storage.load("learning_memory")
    assert [h["op"] for h in doc["history"]] == ["add", "update", "update", "add", "delete", "reset"]
    assert all(not v for v in doc["categories"].values())


def test_memory_rejects_unknown_category_and_bad_text():
    doc = storage.DEFAULTS["learning_memory"]()
    with pytest.raises(memory.MemoryOpError):
        memory.add_item(doc, "everything", "text here")
    with pytest.raises(memory.MemoryOpError):
        memory.add_item(doc, "weak_hooks", "x")


def test_memory_capacity_never_evicts_user_items():
    doc = storage.DEFAULTS["learning_memory"]()
    for i in range(memory.MAX_ITEMS_PER_CATEGORY):
        memory.add_item(doc, "lessons_learned", f"user lesson number {i}", source="user", actor="user")
    with pytest.raises(memory.MemoryOpError, match="full"):
        memory.add_item(doc, "lessons_learned", "analyst lesson")


def test_summary_puts_high_confidence_first():
    doc = storage.DEFAULTS["learning_memory"]()
    memory.add_item(doc, "successful_hooks", "low one", confidence="low")
    memory.add_item(doc, "successful_hooks", "high one", confidence="high")
    text = memory.summarize_for_prompt(doc)
    assert text.index("high one") < text.index("low one")
    assert "memory is empty" in memory.summarize_for_prompt(storage.DEFAULTS["learning_memory"]())


@pytest.mark.parametrize("agent", prompts.AGENTS)
def test_every_agent_prompt_has_required_sections(repo, agent):
    assert prompts.validate_prompt_markdown(prompts.load_prompt(agent)) == []
    system = prompts.build_system_prompt(agent)
    assert "TektiZen Brand Profile" in system and "Content Rules" in system


def test_prompt_validation_reports_missing_sections():
    problems = prompts.validate_prompt_markdown("# Agent\n\n## Role\n\nx")
    assert any("Objective" in p for p in problems)


def test_prompt_path_rejects_traversal():
    with pytest.raises(prompts.PromptError):
        prompts.prompt_path("../../etc/passwd")
