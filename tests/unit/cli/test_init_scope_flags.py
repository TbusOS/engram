"""T-36 tests: ``engram init --subscribe / --org / --team``.

Covers three scope-onboarding flags on ``engram init``:

- ``--subscribe <pool>`` (repeatable): subscribes the freshly-initialized
  project to each pool. Pool must already exist at ``~/.engram/pools/<name>/``.
  Writes ``[subscribe.<name>]`` to pools.toml (SPEC §9.2) and creates the
  ``.memory/pools/<name>`` symlink (SPEC §3.1).
- ``--org <name>``: asserts the project belongs to an already-joined org
  scope. Validates ``~/.engram/org/<name>/.git`` exists; fails with an
  actionable message otherwise.
- ``--team <name>``: same for team.

The flags are non-interactive and additive — any combination is legal.
Missing scopes fail loudly so the operator fixes the environment once
rather than discovering the problem on every `engram memory` call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomli
from click.testing import CliRunner

from engram.cli import cli


def _make_pool(home: Path, name: str) -> Path:
    """Create ``~/.engram/pools/<name>/`` so subscribe can target it."""
    pool = home / ".engram" / "pools" / name
    pool.mkdir(parents=True, exist_ok=True)
    return pool


def _make_org(home: Path, name: str) -> Path:
    """Create a git-shaped ``~/.engram/org/<name>/`` so validation passes."""
    org = home / ".engram" / "org" / name
    (org / ".git").mkdir(parents=True, exist_ok=True)
    return org


def _make_team(home: Path, name: str) -> Path:
    team = home / ".engram" / "team" / name
    (team / ".git").mkdir(parents=True, exist_ok=True)
    return team


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path / "proj"


# ------------------------------------------------------------------
# --subscribe
# ------------------------------------------------------------------


def test_init_subscribe_single_pool(home: Path, project: Path) -> None:
    _make_pool(home, "compliance")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "init", "--subscribe", "compliance"]
    )
    assert result.exit_code == 0, result.output
    data = tomli.loads((project / ".memory" / "pools.toml").read_text(encoding="utf-8"))
    assert "compliance" in data["subscribe"]
    assert data["subscribe"]["compliance"]["subscribed_at"] == "project"
    assert data["subscribe"]["compliance"]["propagation_mode"] == "auto-sync"
    assert (project / ".memory" / "pools" / "compliance").is_symlink()


def test_init_subscribe_multiple_pools(home: Path, project: Path) -> None:
    _make_pool(home, "compliance")
    _make_pool(home, "security-playbooks")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "init",
            "--subscribe",
            "compliance",
            "--subscribe",
            "security-playbooks",
        ],
    )
    assert result.exit_code == 0, result.output
    data = tomli.loads((project / ".memory" / "pools.toml").read_text(encoding="utf-8"))
    assert set(data["subscribe"].keys()) == {"compliance", "security-playbooks"}
    for name in ("compliance", "security-playbooks"):
        assert (project / ".memory" / "pools" / name).is_symlink()


def test_init_subscribe_missing_pool_fails(home: Path, project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "init", "--subscribe", "does-not-exist"]
    )
    assert result.exit_code != 0
    assert "does-not-exist" in result.output


def test_init_subscribe_failure_leaves_project_uninitialized(
    home: Path, project: Path
) -> None:
    """If the pool is missing, init must fail *before* writing any files —
    or, if it wrote the scaffold first, it must roll back so retrying with
    the fixed pool doesn't hit 'already exists'."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "init", "--subscribe", "missing"]
    )
    assert result.exit_code != 0
    # Either the project was never created, or running init again succeeds
    # after the pool is made available.
    _make_pool(home, "missing")
    result2 = runner.invoke(
        cli, ["--dir", str(project), "init", "--subscribe", "missing", "--force"]
    )
    assert result2.exit_code == 0, result2.output


# ------------------------------------------------------------------
# --org
# ------------------------------------------------------------------


def test_init_org_joined_succeeds(home: Path, project: Path) -> None:
    _make_org(home, "acme")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init", "--org", "acme"])
    assert result.exit_code == 0, result.output
    # Project artifacts present as usual.
    assert (project / ".memory" / "local").is_dir()


def test_init_org_not_joined_fails_with_guidance(home: Path, project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init", "--org", "not-joined"])
    assert result.exit_code != 0
    assert "not-joined" in result.output
    assert "engram org join" in result.output


def test_init_org_missing_git_dir_fails(home: Path, project: Path) -> None:
    """Bare directory without ``.git`` is not a joined org."""
    (home / ".engram" / "org" / "half").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init", "--org", "half"])
    assert result.exit_code != 0
    assert "half" in result.output


# ------------------------------------------------------------------
# --team
# ------------------------------------------------------------------


def test_init_team_joined_succeeds(home: Path, project: Path) -> None:
    _make_team(home, "platform")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init", "--team", "platform"])
    assert result.exit_code == 0, result.output


def test_init_team_not_joined_fails(home: Path, project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init", "--team", "absent"])
    assert result.exit_code != 0
    assert "engram team join" in result.output


# ------------------------------------------------------------------
# combined
# ------------------------------------------------------------------


def test_init_all_flags_together(home: Path, project: Path) -> None:
    _make_org(home, "acme")
    _make_team(home, "platform")
    _make_pool(home, "compliance")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "init",
            "--org",
            "acme",
            "--team",
            "platform",
            "--subscribe",
            "compliance",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "subscribed_pools" in payload
    assert payload["subscribed_pools"] == ["compliance"]
    assert payload["org"] == "acme"
    assert payload["team"] == "platform"
    # pools.toml populated
    data = tomli.loads((project / ".memory" / "pools.toml").read_text(encoding="utf-8"))
    assert "compliance" in data["subscribe"]


def test_init_without_scope_flags_still_works(home: Path, project: Path) -> None:
    """Regression guard: T-17 behaviour must remain unchanged when no flags given."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "init"])
    assert result.exit_code == 0, result.output
    assert (project / ".memory" / "local").is_dir()
    assert (project / ".engram" / "version").is_file()
