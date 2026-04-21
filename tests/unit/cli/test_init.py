"""T-17 tests for engram.commands.init — `engram init` + init_project()."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import STORE_VERSION, init_project


# ------------------------------------------------------------------
# init_project() pure function
# ------------------------------------------------------------------


def test_init_project_creates_memory_tree(tmp_path: Path) -> None:
    init_project(tmp_path)
    assert (tmp_path / ".memory").is_dir()
    for sub in ("local", "pools", "workflows", "kb"):
        assert (tmp_path / ".memory" / sub).is_dir()


def test_init_project_creates_engram_version_file(tmp_path: Path) -> None:
    init_project(tmp_path)
    version_file = tmp_path / ".engram" / "version"
    assert version_file.read_text(encoding="utf-8").strip() == STORE_VERSION


def test_init_project_writes_memory_md_with_required_sections(tmp_path: Path) -> None:
    init_project(tmp_path, name="acme-platform")
    content = (tmp_path / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    # SPEC §7.2 required top-level sections
    for section in (
        "# MEMORY.md",
        "## Identity",
        "## Always-on rules",
        "## Topics",
        "## Subscribed pools",
        "## Recently added",
    ):
        assert section in content, f"missing {section}"


def test_init_project_memory_md_includes_project_name(tmp_path: Path) -> None:
    init_project(tmp_path, name="acme-platform")
    content = (tmp_path / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "acme-platform" in content


def test_init_project_default_name_is_directory_basename(tmp_path: Path) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    init_project(project_dir)
    content = (project_dir / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "my-project" in content


def test_init_project_writes_pools_toml_stub(tmp_path: Path) -> None:
    init_project(tmp_path)
    pools = (tmp_path / ".memory" / "pools.toml").read_text(encoding="utf-8")
    assert "pool" in pools.lower()


def test_init_project_errors_when_memory_already_exists(tmp_path: Path) -> None:
    (tmp_path / ".memory").mkdir()
    with pytest.raises(click.ClickException, match="already exists"):
        init_project(tmp_path)


def test_init_project_force_overwrites_skeleton(tmp_path: Path) -> None:
    (tmp_path / ".memory").mkdir()
    (tmp_path / ".memory" / "MEMORY.md").write_text("pre-existing content")
    init_project(tmp_path, force=True)
    content = (tmp_path / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "pre-existing content" not in content
    assert "# MEMORY.md" in content


def test_init_project_force_preserves_local_assets(tmp_path: Path) -> None:
    (tmp_path / ".memory" / "local").mkdir(parents=True)
    (tmp_path / ".memory" / "local" / "feedback_keep.md").write_text("do not delete me")
    init_project(tmp_path, force=True)
    assert (tmp_path / ".memory" / "local" / "feedback_keep.md").read_text() == "do not delete me"


def test_init_project_returns_key_paths(tmp_path: Path) -> None:
    result = init_project(tmp_path)
    assert set(result.keys()) == {
        "memory",
        "engram",
        "version_file",
        "landing_index",
        "pools_toml",
    }
    assert result["memory"] == tmp_path / ".memory"
    assert result["version_file"] == tmp_path / ".engram" / "version"


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_init_in_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".memory").is_dir()
    assert (tmp_path / ".engram" / "version").exists()


def test_cli_init_with_dir_flag(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "engram-project"
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(target), "init"])
    assert result.exit_code == 0, result.output
    assert (target / ".memory").is_dir()


def test_cli_init_with_name(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(tmp_path), "init", "--name", "myproj"])
    assert result.exit_code == 0, result.output
    content = (tmp_path / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "myproj" in content


def test_cli_init_errors_on_reinit_without_force(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(tmp_path), "init"])
    assert result.exit_code == 0
    result2 = runner.invoke(cli, ["--dir", str(tmp_path), "init"])
    assert result2.exit_code != 0
    assert "already exists" in result2.output


def test_cli_init_force_succeeds_on_reinit(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(tmp_path), "init"])
    assert result.exit_code == 0
    result2 = runner.invoke(cli, ["--dir", str(tmp_path), "init", "--force"])
    assert result2.exit_code == 0, result2.output


def test_cli_init_no_adapter_flag_accepted(tmp_path: Path) -> None:
    """--no-adapter is accepted today as a no-op (adapter support lands in T-55)."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(tmp_path), "init", "--no-adapter"]
    )
    assert result.exit_code == 0, result.output


def test_cli_init_json_output(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "--dir", str(tmp_path), "init"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["memory"] == str(tmp_path / ".memory")
    assert payload["version_file"] == str(tmp_path / ".engram" / "version")


def test_cli_init_text_output_mentions_memory(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(tmp_path), "init"])
    assert result.exit_code == 0
    assert ".memory" in result.output


def test_init_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "init" in result.output
