"""Filesystem locations. Override the repository root with TEKTIZEN_ROOT (used by tests)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("TEKTIZEN_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return repo_root() / "data"


def schemas_dir() -> Path:
    # Schemas ship with the code, never with test data, so they always resolve from the package.
    return Path(__file__).resolve().parent.parent / "schemas"


def config_dir() -> Path:
    return repo_root() / "config"


def prompts_dir() -> Path:
    return repo_root() / "agents" / "prompts"
