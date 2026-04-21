"""T-53 / T-54 / T-55 tests: ``engram adapter`` CLI + 5 adapter specs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.adapters.renderer import BEGIN_MARKER, END_MARKER
from engram.cli import cli


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "proj"
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(root), "init", "--name", "adapter-test"])
    assert result.exit_code == 0
    return root


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


def test_adapter_list_shows_five_canonical_tools(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "adapter", "list"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {a["name"] for a in payload}
    # Claude Code + AGENTS.md (codex/opencode) + Gemini CLI + Cursor + raw API.
    assert {
        "claude-code",
        "codex",
        "gemini-cli",
        "cursor",
        "raw-api",
    }.issubset(names)


# ------------------------------------------------------------------
# install
# ------------------------------------------------------------------


def test_install_claude_code_creates_claude_md(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "adapter", "install", "claude-code"],
    )
    assert result.exit_code == 0, result.output
    claude_md = project / "CLAUDE.md"
    assert claude_md.is_file()
    text = claude_md.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text
    assert END_MARKER in text
    # Template references the engram essentials the LLM needs to know.
    assert ".memory/" in text
    assert "engram memory search" in text


def test_install_codex_creates_agents_md(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "codex"])
    assert (project / "AGENTS.md").is_file()


def test_install_gemini_cli_creates_gemini_md(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "gemini-cli"])
    assert (project / "GEMINI.md").is_file()


def test_install_cursor_creates_rules_file(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "cursor"])
    assert (project / ".cursor" / "rules" / "engram.mdc").is_file()


def test_install_raw_api_creates_prompt_file(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "raw-api"])
    assert (project / "ENGRAM_PROMPT.md").is_file()


# ------------------------------------------------------------------
# refresh — update without trampling user content
# ------------------------------------------------------------------


def test_refresh_preserves_user_content_outside_markers(project: Path) -> None:
    claude_md = project / "CLAUDE.md"
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "claude-code"])

    # User appends personal notes outside the markers.
    with claude_md.open("a", encoding="utf-8") as f:
        f.write("\n\n# My personal CLAUDE tweaks\n\nDO NOT TOUCH THIS LINE\n")

    # Refresh the adapter.
    result = runner.invoke(
        cli, ["--dir", str(project), "adapter", "refresh", "claude-code"]
    )
    assert result.exit_code == 0, result.output

    text = claude_md.read_text(encoding="utf-8")
    assert "DO NOT TOUCH THIS LINE" in text
    assert BEGIN_MARKER in text
    assert END_MARKER in text


def test_refresh_all_updates_every_installed_adapter(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "claude-code"])
    runner.invoke(cli, ["--dir", str(project), "adapter", "install", "codex"])

    result = runner.invoke(cli, ["--dir", str(project), "adapter", "refresh"])
    assert result.exit_code == 0, result.output
    # Both files still present and still contain the managed block.
    for name in ("CLAUDE.md", "AGENTS.md"):
        t = (project / name).read_text(encoding="utf-8")
        assert BEGIN_MARKER in t


# ------------------------------------------------------------------
# Errors + hooks
# ------------------------------------------------------------------


def test_install_unknown_adapter_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "adapter", "install", "not-real-tool"]
    )
    assert result.exit_code != 0
    assert "not-real-tool" in result.output


def test_claude_code_hooks_available_at_repo_path() -> None:
    """T-53 hooks ship as reference files under adapters/claude-code/hooks/."""
    repo_root = Path(__file__).resolve().parents[3]
    hooks = repo_root / "adapters" / "claude-code" / "hooks"
    assert hooks.is_dir()
    assert (hooks / "engram_stop.sh").is_file()
    assert (hooks / "engram_precompact.sh").is_file()
    # Must be executable-ish shell scripts.
    for f in hooks.glob("*.sh"):
        head = f.read_text(encoding="utf-8").splitlines()[0]
        assert head.startswith("#!") and "sh" in head
