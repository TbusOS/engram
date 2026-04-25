"""Issue #3 / T-160: README ## Commands table must stay in sync with the
actually-registered subcommands.

Drift mode: a contributor adds a new subcommand in `engram/cli.py`
``_register_subcommands()`` but forgets to update the README table. CI
catches this here so the README does not become a lie.

The check is intentionally loose:

- Every registered top-level command (and group) MUST appear at least once
  in the README ``## Commands`` section.
- The reverse direction (README mentions a command that is not registered)
  is allowed — the table also lists ``Planned`` commands that are
  intentionally not yet wired up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engram.cli import cli


REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "README.md"


def _registered_command_names() -> list[str]:
    """All top-level subcommands the CLI actually registers right now."""
    return sorted(name for name in cli.commands if not name.startswith("_"))


def _commands_section(text: str) -> str:
    marker = "## Commands"
    start = text.find(marker)
    if start < 0:
        raise AssertionError("README is missing the ## Commands section")
    # Cut at the next top-level heading after Commands so we don't pull in
    # later sections (Migrating, Project layout, etc.).
    rest = text[start + len(marker) :]
    next_heading = rest.find("\n## ")
    return rest if next_heading < 0 else rest[:next_heading]


def test_every_registered_command_appears_in_readme() -> None:
    text = README.read_text(encoding="utf-8")
    section = _commands_section(text)
    missing: list[str] = []
    for cmd in _registered_command_names():
        # Match either ``engram <cmd>`` (exact) or `<cmd>` in a code span.
        if f"engram {cmd}" not in section and f"`{cmd}`" not in section:
            missing.append(cmd)
    assert not missing, (
        "These registered subcommands are not mentioned in README ## Commands:\n  "
        + "\n  ".join(missing)
        + "\nUpdate README.md to keep the table in sync."
    )
