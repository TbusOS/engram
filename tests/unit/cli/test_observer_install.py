"""T-205 tests for engram.observer.install + install_cli."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.observer.install import (
    INSTALL_TARGETS,
    InstallTargetUnknown,
    apply_install_plan,
    build_install_plan,
    hook_script_path,
    list_install_targets,
)
from engram.observer.install_cli import observer_group


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


def test_registry_has_five_targets() -> None:
    assert set(INSTALL_TARGETS.keys()) == {
        "claude-code",
        "codex",
        "cursor",
        "gemini-cli",
        "opencode",
    }


def test_list_install_targets_sorted() -> None:
    names = [t.name for t in list_install_targets()]
    assert names == sorted(names)


def test_each_target_has_action() -> None:
    for t in INSTALL_TARGETS.values():
        assert t.action in {"write", "paste"}


def test_only_claude_code_writes() -> None:
    """Other clients are paste-mode pending stable hook surfaces."""
    write_targets = [t.name for t in INSTALL_TARGETS.values() if t.action == "write"]
    assert write_targets == ["claude-code"]


# ----------------------------------------------------------------------
# Hook script paths
# ----------------------------------------------------------------------


def test_hook_script_paths_exist_in_repo() -> None:
    """The bundled hook scripts must be present under adapters/."""
    for name in INSTALL_TARGETS:
        path = hook_script_path(name)
        assert path.exists(), f"missing hook script for {name}: {path}"
        assert path.is_file()


def test_hook_script_paths_are_executable() -> None:
    import os

    for name in INSTALL_TARGETS:
        path = hook_script_path(name)
        assert os.access(path, os.X_OK), f"{path} is not executable"


def test_hook_script_paths_resolve_under_adapters_root(tmp_path: Path) -> None:
    fake_root = tmp_path / "adapters"
    (fake_root / "claude-code" / "hooks").mkdir(parents=True)
    (fake_root / "claude-code" / "hooks" / "engram_observe_post_tool_use.sh").write_text(
        "#!/bin/sh\nexit 0\n"
    )
    p = hook_script_path("claude-code", adapters_root=fake_root)
    assert p == fake_root / "claude-code" / "hooks" / "engram_observe_post_tool_use.sh"


# ----------------------------------------------------------------------
# build_install_plan
# ----------------------------------------------------------------------


def test_build_plan_for_claude_code_is_write() -> None:
    plan = build_install_plan("claude-code")
    assert plan.action == "write"
    assert plan.config_path == Path.home() / ".claude" / "settings.json"
    assert "PostToolUse" in plan.snippet


def test_build_plan_for_codex_is_paste() -> None:
    plan = build_install_plan("codex")
    assert plan.action == "paste"
    assert plan.config_path is None
    assert "engram_observe_post_tool_use.sh" in plan.snippet


def test_build_plan_unknown_target_raises() -> None:
    with pytest.raises(InstallTargetUnknown):
        build_install_plan("nonexistent")


# ----------------------------------------------------------------------
# apply_install_plan — claude-code merge
# ----------------------------------------------------------------------


def test_apply_creates_settings_file(tmp_path: Path) -> None:
    plan = build_install_plan("claude-code")
    fake_settings = tmp_path / "settings.json"
    # Override the resolver via plan field directly.
    from engram.observer.install import InstallPlan

    custom = InstallPlan(
        target=plan.target,
        action=plan.action,
        hook_path=plan.hook_path,
        snippet=plan.snippet,
        config_path=fake_settings,
    )
    apply_install_plan(custom)
    assert fake_settings.exists()
    data = json.loads(fake_settings.read_text())
    hooks = data["hooks"]["PostToolUse"]
    assert len(hooks) == 1


def test_apply_idempotent(tmp_path: Path) -> None:
    plan = build_install_plan("claude-code")
    from engram.observer.install import InstallPlan

    fake_settings = tmp_path / "settings.json"
    custom = InstallPlan(
        target=plan.target,
        action=plan.action,
        hook_path=plan.hook_path,
        snippet=plan.snippet,
        config_path=fake_settings,
    )
    apply_install_plan(custom)
    apply_install_plan(custom)
    data = json.loads(fake_settings.read_text())
    hooks = data["hooks"]["PostToolUse"]
    assert len(hooks) == 1  # no duplicate


def test_apply_preserves_existing_hooks(tmp_path: Path) -> None:
    fake_settings = tmp_path / "settings.json"
    fake_settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "/usr/bin/other-hook.sh"}
                            ],
                        }
                    ]
                }
            }
        )
    )
    plan = build_install_plan("claude-code")
    from engram.observer.install import InstallPlan

    custom = InstallPlan(
        target=plan.target,
        action=plan.action,
        hook_path=plan.hook_path,
        snippet=plan.snippet,
        config_path=fake_settings,
    )
    apply_install_plan(custom)
    data = json.loads(fake_settings.read_text())
    hooks = data["hooks"]["PostToolUse"]
    assert len(hooks) == 2


def test_apply_dry_run_writes_nothing(tmp_path: Path) -> None:
    plan = build_install_plan("claude-code")
    from engram.observer.install import InstallPlan

    fake_settings = tmp_path / "settings.json"
    custom = InstallPlan(
        target=plan.target,
        action=plan.action,
        hook_path=plan.hook_path,
        snippet=plan.snippet,
        config_path=fake_settings,
    )
    apply_install_plan(custom, dry_run=True)
    assert not fake_settings.exists()


def test_apply_paste_target_is_noop(tmp_path: Path) -> None:
    """Paste targets do nothing on apply."""
    plan = build_install_plan("codex")
    apply_install_plan(plan)  # no error
    apply_install_plan(plan, dry_run=True)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def test_cli_list() -> None:
    runner = CliRunner()
    result = runner.invoke(observer_group, ["install", "--list"])
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "codex" in result.output


def test_cli_list_json() -> None:
    runner = CliRunner()
    result = runner.invoke(observer_group, ["install", "--list", "--format", "json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    names = {row["name"] for row in rows}
    assert names == set(INSTALL_TARGETS.keys())


def test_cli_install_paste_target() -> None:
    runner = CliRunner()
    result = runner.invoke(observer_group, ["install", "--target", "codex"])
    assert result.exit_code == 0
    assert "codex" in result.output
    assert "engram_observe_post_tool_use.sh" in result.output


def test_cli_install_dry_run() -> None:
    runner = CliRunner()
    result = runner.invoke(
        observer_group, ["install", "--target", "claude-code", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_cli_no_target_no_list_errors() -> None:
    runner = CliRunner()
    result = runner.invoke(observer_group, ["install"])
    assert result.exit_code == 2


def test_cli_format_json() -> None:
    runner = CliRunner()
    result = runner.invoke(
        observer_group,
        ["install", "--target", "codex", "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["target"] == "codex"
    assert payload["action"] == "paste"
