"""T-10 scaffold smoke tests.

Verify:
- `engram` package imports and exposes `__version__`.
- `engram --version` exits 0 and prints the version.
- `engram --help` exits 0 and names the tool.
- `python -m engram --version` works (__main__ entry).
"""

from __future__ import annotations

import subprocess
import sys

from click.testing import CliRunner

import engram
from engram.cli import cli


def test_package_has_version_string() -> None:
    assert isinstance(engram.__version__, str)
    assert engram.__version__ != ""


def test_cli_version_flag_prints_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "engram" in result.output
    assert engram.__version__ in result.output


def test_cli_help_mentions_engram() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "engram" in result.output.lower()


def test_python_m_engram_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "engram", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "engram" in result.stdout
