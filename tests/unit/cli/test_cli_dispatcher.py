"""T-16 tests for engram.cli — root group + global flags + GlobalConfig propagation."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from engram.cli import GlobalConfig, cli


@pytest.fixture
def probe_cli() -> Iterator[click.Group]:
    """Register a hidden `_probe` subcommand that dumps GlobalConfig as JSON."""

    @cli.command(name="_probe", hidden=True)
    @click.pass_obj
    def _probe(cfg: GlobalConfig) -> None:
        click.echo(
            json.dumps(
                {
                    "dir_override": str(cfg.dir_override)
                    if cfg.dir_override is not None
                    else None,
                    "output_format": cfg.output_format,
                    "quiet": cfg.quiet,
                    "debug": cfg.debug,
                }
            )
        )

    try:
        yield cli
    finally:
        cli.commands.pop("_probe", None)


def _invoke_probe(args: list[str]) -> dict[str, object]:
    runner = CliRunner()
    result = runner.invoke(cli, [*args, "_probe"])
    assert result.exit_code == 0, result.output
    data: dict[str, object] = json.loads(result.output.strip())
    return data


# ------------------------------------------------------------------
# Defaults
# ------------------------------------------------------------------


def test_defaults_when_no_flags_given(probe_cli: click.Group) -> None:
    data = _invoke_probe([])
    assert data == {
        "dir_override": None,
        "output_format": "text",
        "quiet": False,
        "debug": False,
    }


# ------------------------------------------------------------------
# --dir
# ------------------------------------------------------------------


def test_dir_flag_stored_in_context(
    probe_cli: click.Group, tmp_path: Path
) -> None:
    data = _invoke_probe(["--dir", str(tmp_path)])
    assert data["dir_override"] == str(tmp_path)


def test_dir_flag_accepts_non_existent_path(
    probe_cli: click.Group, tmp_path: Path
) -> None:
    """--dir parses paths that don't exist yet — engram init creates them."""
    target = tmp_path / "not-yet-created"
    data = _invoke_probe(["--dir", str(target)])
    assert data["dir_override"] == str(target)


def test_dir_flag_rejects_file_as_directory(
    probe_cli: click.Group, tmp_path: Path
) -> None:
    regular_file = tmp_path / "f.txt"
    regular_file.write_text("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(regular_file), "_probe"])
    assert result.exit_code != 0
    assert "directory" in result.output.lower() or "file" in result.output.lower()


# ------------------------------------------------------------------
# --format
# ------------------------------------------------------------------


def test_format_json_accepted(probe_cli: click.Group) -> None:
    data = _invoke_probe(["--format", "json"])
    assert data["output_format"] == "json"


def test_format_text_accepted(probe_cli: click.Group) -> None:
    data = _invoke_probe(["--format", "text"])
    assert data["output_format"] == "text"


def test_format_invalid_rejected(probe_cli: click.Group) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "yaml", "_probe"])
    assert result.exit_code != 0
    assert "yaml" in result.output.lower() or "choice" in result.output.lower()


# ------------------------------------------------------------------
# --quiet / --debug / -q
# ------------------------------------------------------------------


def test_quiet_flag_sets_quiet_true(probe_cli: click.Group) -> None:
    data = _invoke_probe(["--quiet"])
    assert data["quiet"] is True
    assert data["debug"] is False


def test_short_q_is_same_as_quiet(probe_cli: click.Group) -> None:
    data = _invoke_probe(["-q"])
    assert data["quiet"] is True


def test_debug_flag_sets_debug_true(probe_cli: click.Group) -> None:
    data = _invoke_probe(["--debug"])
    assert data["debug"] is True
    assert data["quiet"] is False


def test_quiet_and_debug_can_coexist(probe_cli: click.Group) -> None:
    """Both flags can be set; --debug wins for logging level (tested separately)."""
    data = _invoke_probe(["--quiet", "--debug"])
    assert data["quiet"] is True
    assert data["debug"] is True


# ------------------------------------------------------------------
# GlobalConfig.resolve_project_root
# ------------------------------------------------------------------


def test_resolve_project_root_uses_dir_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    cfg = GlobalConfig(dir_override=tmp_path)
    assert cfg.resolve_project_root() == tmp_path.resolve()


def test_resolve_project_root_dir_override_beats_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dir wins over ENGRAM_DIR (DESIGN §9.3 resolution order)."""
    env_dir = tmp_path / "env"
    cli_dir = tmp_path / "cli"
    env_dir.mkdir()
    cli_dir.mkdir()
    monkeypatch.setenv("ENGRAM_DIR", str(env_dir))
    cfg = GlobalConfig(dir_override=cli_dir)
    assert cfg.resolve_project_root() == cli_dir.resolve()


def test_resolve_project_root_expands_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "foo").mkdir()
    cfg = GlobalConfig(dir_override=Path("~/foo"))
    resolved = cfg.resolve_project_root()
    assert "~" not in str(resolved)
    assert resolved == (tmp_path / "foo").resolve()


def test_resolve_project_root_falls_back_to_walk_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".memory").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    monkeypatch.chdir(nested)
    cfg = GlobalConfig()
    assert cfg.resolve_project_root() == tmp_path.resolve()


def test_resolve_project_root_honors_env_when_no_dir_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "env-target"
    monkeypatch.setenv("ENGRAM_DIR", str(override))
    cfg = GlobalConfig(dir_override=None)
    assert cfg.resolve_project_root() == override.resolve()


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------


def test_debug_flag_raises_root_logger_to_debug(
    probe_cli: click.Group, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _invoke_probe(["--debug"])
    # Root logger should be at DEBUG (10) after --debug configures it.
    assert logging.getLogger().level == logging.DEBUG


def test_quiet_flag_raises_root_logger_to_warning(
    probe_cli: click.Group,
) -> None:
    _invoke_probe(["--quiet"])
    assert logging.getLogger().level == logging.WARNING


def test_default_logger_is_info(probe_cli: click.Group) -> None:
    _invoke_probe([])
    assert logging.getLogger().level == logging.INFO


# ------------------------------------------------------------------
# Version + help still work
# ------------------------------------------------------------------


def test_version_flag_still_works() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "engram" in result.output


def test_help_mentions_global_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--dir" in result.output
    assert "--format" in result.output
    assert "--quiet" in result.output
    assert "--debug" in result.output
