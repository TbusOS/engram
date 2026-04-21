"""T-18 tests for engram.commands.version — `engram version` subcommand."""

from __future__ import annotations

import json

from click.testing import CliRunner

from engram import __version__
from engram.cli import cli


def test_version_text_output() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output
    assert "Python" in result.output
    assert "store" in result.output.lower()


def test_version_json_output_has_expected_keys() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "version"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["engram"] == __version__
    assert "python" in payload
    assert "store_schema" in payload
    assert "platform" in payload


def test_version_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "version" in result.output
