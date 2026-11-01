from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An isolated repo root with real config/prompts and an EMPTY data directory."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    shutil.copytree(REPO / "agents", tmp_path / "agents")
    (tmp_path / "data").mkdir()
    monkeypatch.setenv("TEKTIZEN_ROOT", str(tmp_path))
    return tmp_path
