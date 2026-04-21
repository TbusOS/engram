"""T-18 tests for engram.commands.config — user-global ~/.engram/config.toml."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.config import (
    ConfigKeyError,
    config_path,
    get_config_value,
    parse_value,
    set_config_value,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect ~/.engram/ to a per-test tmp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path


# ------------------------------------------------------------------
# config_path + file location
# ------------------------------------------------------------------


def test_config_path_is_under_user_root(fake_home: Path) -> None:
    assert config_path() == fake_home / ".engram" / "config.toml"


def test_set_creates_config_file(fake_home: Path) -> None:
    set_config_value("foo", "bar")
    assert (fake_home / ".engram" / "config.toml").is_file()


def test_set_creates_parent_directory(fake_home: Path) -> None:
    # .engram/ does not exist yet
    assert not (fake_home / ".engram").exists()
    set_config_value("foo", "bar")
    assert (fake_home / ".engram").is_dir()


# ------------------------------------------------------------------
# Roundtrip
# ------------------------------------------------------------------


def test_set_then_get_string(fake_home: Path) -> None:
    set_config_value("ui.theme", "dark")
    assert get_config_value("ui.theme") == "dark"


def test_set_then_get_int(fake_home: Path) -> None:
    set_config_value("budget.context_tokens", 4096)
    assert get_config_value("budget.context_tokens") == 4096


def test_set_then_get_bool(fake_home: Path) -> None:
    set_config_value("features.experimental", True)
    assert get_config_value("features.experimental") is True


def test_set_multiple_keys_preserves_others(fake_home: Path) -> None:
    set_config_value("a.b", 1)
    set_config_value("a.c", 2)
    set_config_value("x", "y")
    assert get_config_value("a.b") == 1
    assert get_config_value("a.c") == 2
    assert get_config_value("x") == "y"


def test_set_overwrites_existing_key(fake_home: Path) -> None:
    set_config_value("x", "first")
    set_config_value("x", "second")
    assert get_config_value("x") == "second"


# ------------------------------------------------------------------
# Error paths
# ------------------------------------------------------------------


def test_get_missing_key_raises(fake_home: Path) -> None:
    with pytest.raises(ConfigKeyError, match="nope"):
        get_config_value("nope")


def test_get_missing_nested_key_raises(fake_home: Path) -> None:
    set_config_value("ui.theme", "dark")
    with pytest.raises(ConfigKeyError, match="ui.font"):
        get_config_value("ui.font")


def test_set_rejects_dotted_path_through_scalar(fake_home: Path) -> None:
    set_config_value("ui", "dark")  # scalar
    with pytest.raises(ValueError, match="not a table"):
        set_config_value("ui.theme", "dark")


def test_get_intermediate_table_returns_dict(fake_home: Path) -> None:
    set_config_value("ui.theme", "dark")
    set_config_value("ui.font", "mono")
    value = get_config_value("ui")
    assert value == {"theme": "dark", "font": "mono"}


def test_get_on_missing_file_raises(fake_home: Path) -> None:
    with pytest.raises(ConfigKeyError, match="foo"):
        get_config_value("foo")


# ------------------------------------------------------------------
# parse_value (CLI value coercion)
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("false", False),
        ("True", True),
        ("False", False),
        ("42", 42),
        ("0", 0),
        ("-17", -17),
        ("3.14", 3.14),
        ("-0.5", -0.5),
        ("dark", "dark"),
        ("", ""),
        ("42.0.1", "42.0.1"),  # looks like a version string, not a number
    ],
)
def test_parse_value_autotypes(raw: str, expected: object) -> None:
    assert parse_value(raw) == expected
    # bool preservation — Python: isinstance(True, int) is True
    if isinstance(expected, bool):
        assert isinstance(parse_value(raw), bool)


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_config_set_then_get(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "set", "ui.theme", "dark"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["config", "get", "ui.theme"])
    assert result.exit_code == 0, result.output
    assert "dark" in result.output


def test_cli_config_set_autotypes_int(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "set", "budget.tokens", "4096"])
    assert result.exit_code == 0
    # Value should be stored as int, not string
    assert get_config_value("budget.tokens") == 4096
    assert not isinstance(get_config_value("budget.tokens"), str)


def test_cli_config_set_autotypes_bool(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "set", "features.experimental", "true"])
    assert result.exit_code == 0
    assert get_config_value("features.experimental") is True


def test_cli_config_get_missing_key_errors(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "get", "nope"])
    assert result.exit_code != 0
    assert "nope" in result.output.lower() or "not found" in result.output.lower()


def test_cli_config_list_empty(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "list"])
    assert result.exit_code == 0


def test_cli_config_list_shows_entries(fake_home: Path) -> None:
    set_config_value("ui.theme", "dark")
    set_config_value("budget.tokens", 4096)
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "list"])
    assert result.exit_code == 0
    assert "ui.theme" in result.output
    assert "dark" in result.output
    assert "budget.tokens" in result.output
    assert "4096" in result.output


def test_cli_config_get_json_output(fake_home: Path) -> None:
    set_config_value("ui.theme", "dark")
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "config", "get", "ui.theme"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload == {"key": "ui.theme", "value": "dark"}


def test_cli_config_list_json_output(fake_home: Path) -> None:
    set_config_value("a.b", 1)
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "config", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload == {"a": {"b": 1}}


def test_cli_config_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "config" in result.output
