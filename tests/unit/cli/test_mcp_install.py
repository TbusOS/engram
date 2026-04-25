"""T-163 tests for ``engram mcp install --target=<client>``.

The contract:

- registry of supported clients with stable target names
- each target has either a known config-file path (writes JSON/TOML merge)
  OR prints a paste-ready snippet (when the client's config location varies
  too much across platforms / versions to write blindly)
- ``--dry-run`` prints planned changes without touching disk
- ``--list`` lists supported targets
- idempotent: running the same install twice does not duplicate the
  ``engram`` entry
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.mcp.install import (
    INSTALL_TARGETS,
    InstallPlan,
    install_target,
    plan_install,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Sandbox HOME so install writes never touch the real filesystem."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    yield home


# ------------------------------------------------------------------
# registry shape
# ------------------------------------------------------------------


class TestRegistry:
    def test_known_targets_present(self) -> None:
        names = set(INSTALL_TARGETS)
        # P0 targets — must exist in v0.2.1
        for required in (
            "claude-desktop",
            "claude-code",
            "cursor",
            "zed",
            "codex",
            "opencode",
            "vscode-continue",
            "vscode-cline",
            "vscode-copilot",
        ):
            assert required in names, f"missing target {required!r}"

    def test_every_target_has_describe(self) -> None:
        for name, target in INSTALL_TARGETS.items():
            assert target.describe, f"{name} missing describe"
            assert target.snippet, f"{name} missing snippet"


# ------------------------------------------------------------------
# plan_install — dry-run path
# ------------------------------------------------------------------


class TestPlanInstall:
    def test_plan_includes_target_name_and_action(
        self, fake_home: Path
    ) -> None:
        plan = plan_install("claude-desktop")
        assert isinstance(plan, InstallPlan)
        assert plan.target == "claude-desktop"
        # Either a write or a paste action
        assert plan.action in {"write", "paste"}
        if plan.action == "write":
            assert plan.config_path is not None
            assert "mcpServers" in plan.snippet or "engram" in plan.snippet

    def test_unknown_target_raises(self) -> None:
        with pytest.raises(KeyError):
            plan_install("not-a-real-client")


# ------------------------------------------------------------------
# install_target — actual file write (sandboxed via fake_home)
# ------------------------------------------------------------------


class TestInstallClaudeDesktop:
    def test_creates_config_when_missing(self, fake_home: Path) -> None:
        result = install_target("claude-desktop")
        assert result.action == "write"
        assert result.config_path is not None
        config = json.loads(result.config_path.read_text(encoding="utf-8"))
        assert "engram" in config["mcpServers"]
        assert config["mcpServers"]["engram"]["command"] == "engram"
        assert config["mcpServers"]["engram"]["args"] == ["mcp", "serve"]

    def test_merges_into_existing_config(self, fake_home: Path) -> None:
        # Pre-existing config with another server
        first = install_target("claude-desktop")
        config = json.loads(first.config_path.read_text(encoding="utf-8"))
        config["mcpServers"]["other"] = {"command": "x"}
        first.config_path.write_text(json.dumps(config), encoding="utf-8")

        # Re-install engram; "other" must survive
        install_target("claude-desktop")
        merged = json.loads(first.config_path.read_text(encoding="utf-8"))
        assert "other" in merged["mcpServers"]
        assert "engram" in merged["mcpServers"]

    def test_idempotent(self, fake_home: Path) -> None:
        install_target("claude-desktop")
        install_target("claude-desktop")
        config = json.loads(
            (fake_home / "Library" / "Application Support" / "Claude" /
             "claude_desktop_config.json").read_text(encoding="utf-8")
        ) if (fake_home / "Library" / "Application Support" / "Claude" /
              "claude_desktop_config.json").exists() else json.loads(
            (fake_home / ".config" / "Claude" /
             "claude_desktop_config.json").read_text(encoding="utf-8")
        )
        # Single engram entry, not duplicated
        servers = config["mcpServers"]
        assert sum(1 for k in servers if k == "engram") == 1


class TestInstallCursor:
    def test_writes_cursor_mcp_json(self, fake_home: Path) -> None:
        result = install_target("cursor")
        assert result.action == "write"
        assert result.config_path.name == "mcp.json"
        config = json.loads(result.config_path.read_text(encoding="utf-8"))
        assert "engram" in config["mcpServers"]


class TestInstallPasteOnlyTargets:
    """codex / opencode / vscode-* print snippet rather than auto-writing
    (config locations vary too much)."""

    @pytest.mark.parametrize(
        "target",
        ["codex", "opencode", "vscode-continue", "vscode-cline", "vscode-copilot"],
    )
    def test_paste_action_returns_snippet(
        self, fake_home: Path, target: str
    ) -> None:
        result = install_target(target)
        assert result.action == "paste"
        assert result.config_path is None
        assert result.snippet
        assert "engram" in result.snippet


class TestInstallClaudeCode:
    """claude-code recommends `claude mcp add` shell command rather than
    direct file edit. plan/install returns a paste action with the command."""

    def test_returns_shell_command_for_paste(self, fake_home: Path) -> None:
        result = install_target("claude-code")
        assert result.action == "paste"
        assert "claude mcp add" in result.snippet
        assert "engram mcp serve" in result.snippet


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _run(*args: str) -> "object":
    runner = CliRunner()
    return runner.invoke(cli, ["mcp", "install", *args], catch_exceptions=False)


class TestInstallCli:
    def test_list_targets(self, fake_home: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "install", "--list"])
        assert result.exit_code == 0
        for name in ("claude-desktop", "cursor", "zed", "codex"):
            assert name in result.output

    def test_dry_run_does_not_write(self, fake_home: Path) -> None:
        result = _run("--target=claude-desktop", "--dry-run")
        assert result.exit_code == 0
        # no config file should have been created
        possible_paths = [
            fake_home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            fake_home / ".config" / "Claude" / "claude_desktop_config.json",
        ]
        assert not any(p.exists() for p in possible_paths)

    def test_install_writes_for_known_target(self, fake_home: Path) -> None:
        result = _run("--target=cursor")
        assert result.exit_code == 0
        cursor_config = fake_home / ".cursor" / "mcp.json"
        assert cursor_config.exists()

    def test_unknown_target_errors(self, fake_home: Path) -> None:
        result = _run("--target=nonsense")
        assert result.exit_code != 0
        assert "unknown target" in result.output.lower() or "nonsense" in result.output

    def test_missing_target_flag_errors(self, fake_home: Path) -> None:
        result = _run()
        assert result.exit_code != 0
