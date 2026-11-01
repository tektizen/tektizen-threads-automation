from __future__ import annotations

import json

import pytest

from tektizen import settings, storage


def test_defaults_require_human_approval(repo):
    s = settings.load_settings()
    assert settings.approval_mode(s) == settings.HUMAN_APPROVAL
    assert settings.auto_publish_allowed(s) is False
    assert s["ai"]["model"] == "openrouter/free"
    assert s["quality"] == {"min_overall": 80, "min_factuality": 90, "min_brand": 90, "max_refinement_rounds": 1}


@pytest.mark.parametrize("value", [None, {}, {"approval": {}}, {"approval": {"mode": "AUTO_PUBLISH"}},
                                   {"approval": {"mode": True}}, {"approval": None}])
def test_missing_or_malformed_mode_is_never_auto(value):
    assert settings.approval_mode(value) == settings.HUMAN_APPROVAL
    assert settings.auto_publish_allowed(value) is False


def test_auto_publish_requires_explicit_mode_and_kill_switch_off():
    s = settings.default_settings()
    s["approval"]["mode"] = settings.AUTO_PUBLISH
    assert settings.auto_publish_allowed(s) is True
    s["publishing"]["kill_switch"] = True
    assert settings.auto_publish_allowed(s) is False


def test_partial_settings_file_merges_with_defaults(repo):
    (repo / "data" / "settings.json").write_text(json.dumps({
        "schema_version": 1, "updated_at": None,
        "approval": {"mode": "human_approval"},
        "publishing": {"kill_switch": True, "max_posts_per_run": 2},
        "ai": {"model": "meta-llama/llama-3.3-70b-instruct:free", "temperature": 0.5, "max_tokens": 1500,
               "timeout_seconds": 60, "max_requests_per_run": 10},
        "quality": {"min_overall": 85, "min_factuality": 95, "min_brand": 90, "max_refinement_rounds": 1},
        "generation": {"items_per_daily_run": 1, "default_tone": "x", "enabled_formats": ["single"]},
        "research": {"feeds": [], "max_items_per_feed": 5, "max_age_days": 3},
    }), encoding="utf-8")
    s = settings.load_settings()
    assert s["publishing"]["kill_switch"] is True
    assert s["publishing"]["threads_username"] == "tektizen"  # filled from defaults
    assert s["quality"]["min_overall"] == 85


def test_invalid_mode_in_file_is_rejected(repo):
    doc = settings.default_settings()
    doc["approval"]["mode"] = "yolo"
    (repo / "data" / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(storage.DataError):
        settings.load_settings()


def test_threads_account_id_prefers_repository_variable(monkeypatch):
    s = settings.default_settings()
    monkeypatch.delenv("THREADS_ACCOUNT_ID", raising=False)
    assert settings.threads_account_id(s) is None
    s["publishing"]["threads_account_id"] = "fromsettings123"
    assert settings.threads_account_id(s) == "fromsettings123"
    monkeypatch.setenv("THREADS_ACCOUNT_ID", "66b2e19d8c3f5a7e9d0b1c2d")
    assert settings.threads_account_id(s) == "66b2e19d8c3f5a7e9d0b1c2d"
    monkeypatch.setenv("THREADS_ACCOUNT_ID", "bad id; rm -rf")
    assert settings.threads_account_id(s) is None
