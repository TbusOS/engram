"""T-32 tests for `engram pool pull` — git-based pool sync."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project

_GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(_GIT is None, reason="git binary not available")


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _bootstrap_pool_from_remote(home: Path, name: str) -> Path:
    """Set up a pool with a git remote that can receive publishes.

    The maintainer working copy doubles as the upstream: we clone ``pool``
    from it. When the maintainer later commits, ``git pull`` in the pool
    fetches those commits directly. Avoids bare-repo + initial-branch
    bootstrapping edge cases while still exercising the real git pull path.
    """
    maintainer = home / "maintainers" / name
    maintainer.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(maintainer)],
        check=True,
        capture_output=True,
    )
    _git(maintainer, "config", "user.email", "test@example.com")
    _git(maintainer, "config", "user.name", "Test User")
    # Allow pushes into a checked-out branch (only matters if we pushed back,
    # which this test setup does not). Keeps `git clone` / `git pull` from
    # working-tree repo well-behaved across git versions.
    _git(maintainer, "config", "receive.denyCurrentBranch", "ignore")
    (maintainer / "MEMORY.md").write_text("# initial\n", encoding="utf-8")
    _git(maintainer, "add", "MEMORY.md")
    _git(maintainer, "commit", "-m", "initial")

    pool = home / ".engram" / "pools" / name
    pool.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", str(maintainer), str(pool)],
        check=True,
        capture_output=True,
    )
    return pool


def _publish_change(
    home: Path,
    name: str,
    *,
    add: dict[str, str] | None = None,
    modify: dict[str, str] | None = None,
) -> None:
    """Make a new commit in the maintainer repo (= upstream for the pool)."""
    maintainer = home / "maintainers" / name
    for fname, body in (add or {}).items():
        (maintainer / fname).write_text(body, encoding="utf-8")
        _git(maintainer, "add", fname)
    for fname, body in (modify or {}).items():
        (maintainer / fname).write_text(body, encoding="utf-8")
        _git(maintainer, "add", fname)
    _git(maintainer, "commit", "-m", "update")


@pytest.fixture
def project_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path]]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "proj"
    project.mkdir()
    init_project(project)
    yield project, home


# ------------------------------------------------------------------
# pull a single pool
# ------------------------------------------------------------------


def test_pull_fetches_remote_commit(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    _bootstrap_pool_from_remote(home, "design-system")

    _publish_change(home, "design-system", add={"feedback_one.md": "hi\n"})

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "pull", "design-system"]
    )
    assert result.exit_code == 0, result.output
    assert (home / ".engram" / "pools" / "design-system" / "feedback_one.md").is_file()


def test_pull_reports_counts_json(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    _bootstrap_pool_from_remote(home, "design-system")

    _publish_change(
        home,
        "design-system",
        add={"feedback_one.md": "hi\n", "feedback_two.md": "hi\n"},
        modify={"MEMORY.md": "# modified\n"},
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--format", "json", "--dir", str(project), "pool", "pull", "design-system"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["pool"] == "design-system"
    assert payload["added"] == 2
    assert payload["modified"] == 1
    assert payload["removed"] == 0
    assert payload["changed"] is True


def test_pull_on_up_to_date_pool(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    _bootstrap_pool_from_remote(home, "design-system")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "pull", "design-system"]
    )
    assert result.exit_code == 0, result.output
    assert "up to date" in result.output.lower()


def test_pull_rejects_non_git_pool(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    pool = home / ".engram" / "pools" / "plain"
    pool.mkdir(parents=True)
    (pool / "MEMORY.md").write_text("# no git here\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "pull", "plain"])
    assert result.exit_code != 0
    assert "git" in result.output.lower()


def test_pull_rejects_missing_pool(project_home: tuple[Path, Path]) -> None:
    project, _ = project_home
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "pull", "phantom"])
    assert result.exit_code != 0


# ------------------------------------------------------------------
# pull --all
# ------------------------------------------------------------------


def test_pull_all_iterates_git_pools(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    for name in ("alpha", "beta"):
        _bootstrap_pool_from_remote(home, name)
        _publish_change(home, name, add={f"feedback_{name}.md": "hi\n"})

    # A non-git pool that should be skipped silently by --all.
    (home / ".engram" / "pools" / "plain").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "pull", "--all"])
    assert result.exit_code == 0, result.output
    assert (home / ".engram" / "pools" / "alpha" / "feedback_alpha.md").is_file()
    assert (home / ".engram" / "pools" / "beta" / "feedback_beta.md").is_file()


def test_pull_all_json_returns_list(project_home: tuple[Path, Path]) -> None:
    project, home = project_home
    for name in ("alpha", "beta"):
        _bootstrap_pool_from_remote(home, name)
    _publish_change(home, "alpha", add={"feedback_new.md": "hi\n"})

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "pool", "pull", "--all"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert isinstance(payload, list)
    names = {r["pool"] for r in payload}
    assert names == {"alpha", "beta"}
    alpha = next(r for r in payload if r["pool"] == "alpha")
    beta = next(r for r in payload if r["pool"] == "beta")
    assert alpha["changed"] is True
    assert beta["changed"] is False


def test_pull_without_name_or_all_errors(project_home: tuple[Path, Path]) -> None:
    project, _ = project_home
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "pull"])
    assert result.exit_code != 0


def test_pull_name_and_all_are_mutually_exclusive(
    project_home: tuple[Path, Path],
) -> None:
    project, home = project_home
    _bootstrap_pool_from_remote(home, "design-system")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "pull", "design-system", "--all"]
    )
    assert result.exit_code != 0
