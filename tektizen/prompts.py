"""Load agent prompts and brand configuration from Markdown at runtime."""

from __future__ import annotations

import re
from pathlib import Path

from . import paths

AGENTS = (
    "trend_researcher",
    "content_strategist",
    "content_creator",
    "quality_evaluator",
    "fact_checker",
    "content_editor",
    "learning_analyst",
)

CONFIG_DOCS = ("brand_profile", "content_rules", "approval_policy")

REQUIRED_SECTIONS = (
    "Role", "Objective", "Personality", "Responsibilities", "Rules",
    "Input Format", "Output Format", "Failure Conditions", "Examples",
)

MAX_MARKDOWN_BYTES = 64_000


class PromptError(Exception):
    pass


def prompt_path(agent: str) -> Path:
    if agent not in AGENTS:
        raise PromptError(f"unknown agent: {agent!r}")
    return paths.prompts_dir() / f"{agent}.md"


def config_path(name: str) -> Path:
    if name not in CONFIG_DOCS:
        raise PromptError(f"unknown config document: {name!r}")
    return paths.config_dir() / f"{name}.md"


def _read(path: Path) -> str:
    if not path.exists():
        raise PromptError(f"missing {path.relative_to(paths.repo_root())}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise PromptError(f"{path.name} is empty")
    return text


def section_names(markdown: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.M)]


def missing_sections(markdown: str) -> list[str]:
    present = {s.lower() for s in section_names(markdown)}
    return [s for s in REQUIRED_SECTIONS if s.lower() not in present]


def validate_prompt_markdown(markdown: str) -> list[str]:
    problems = []
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        problems.append(f"prompt exceeds {MAX_MARKDOWN_BYTES} bytes")
    if not markdown.lstrip().startswith("# "):
        problems.append("prompt must start with a '# Title' heading")
    missing = missing_sections(markdown)
    if missing:
        problems.append("missing sections: " + ", ".join(missing))
    return problems


def load_prompt(agent: str) -> str:
    text = _read(prompt_path(agent))
    problems = validate_prompt_markdown(text)
    if problems:
        raise PromptError(f"{agent}.md is invalid: " + "; ".join(problems))
    return text


def load_config(name: str) -> str:
    return _read(config_path(name))


def build_system_prompt(agent: str) -> str:
    """Agent prompt + shared brand profile and content rules, in that order."""
    return "\n\n---\n\n".join([
        load_prompt(agent),
        "# Shared context: Brand Profile\n\n" + load_config("brand_profile"),
        "# Shared context: Content Rules\n\n" + load_config("content_rules"),
    ])
