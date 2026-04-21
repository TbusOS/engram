"""Adapter registry — the five canonical adapter specs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from engram.adapters.templates import render_body, render_body_for_cursor

__all__ = ["ADAPTERS", "AdapterSpec", "find_adapter"]


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    name: str
    description: str
    target: tuple[str, ...]        # relative path fragments under project root
    render: Callable[[], str]


ADAPTERS: tuple[AdapterSpec, ...] = (
    AdapterSpec(
        name="claude-code",
        description="Writes CLAUDE.md for Claude Code CLI + Claude Desktop projects.",
        target=("CLAUDE.md",),
        render=render_body,
    ),
    AdapterSpec(
        name="codex",
        description=(
            "Writes AGENTS.md — read by OpenAI Codex CLI and Opencode. "
            "Conflicting adapter `opencode` alias: same file."
        ),
        target=("AGENTS.md",),
        render=render_body,
    ),
    AdapterSpec(
        name="gemini-cli",
        description="Writes GEMINI.md for Google's Gemini CLI.",
        target=("GEMINI.md",),
        render=render_body,
    ),
    AdapterSpec(
        name="cursor",
        description="Writes .cursor/rules/engram.mdc for Cursor IDE.",
        target=(".cursor", "rules", "engram.mdc"),
        render=render_body_for_cursor,
    ),
    AdapterSpec(
        name="raw-api",
        description=(
            "Writes ENGRAM_PROMPT.md — a stand-alone system prompt for "
            "raw-API callers (llama.cpp / ollama / Anthropic API /"
            " OpenAI API / custom)."
        ),
        target=("ENGRAM_PROMPT.md",),
        render=render_body,
    ),
)


def find_adapter(name: str) -> AdapterSpec | None:
    for a in ADAPTERS:
        if a.name == name:
            return a
    return None


def target_path(project_root: Path, spec: AdapterSpec) -> Path:
    return project_root.joinpath(*spec.target)
