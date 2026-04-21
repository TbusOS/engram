"""T-33 tests for `engram team` + `engram org` — SPEC §8.5 git-synced scopes.

The behaviour is identical for both scope kinds, so every test is
parametrised on ``kind ∈ {"team", "org"}`` and runs twice.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli

_GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(_GIT is None, reason="git binary not available")


SCOPE_KINDS = ("team", "org")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_upstream(tmp_path: Path, kind: str, name: str) -> Path:
    """Create a minimal upstream repo for the scope to be joined from."""
    upstream = tmp_path / "upstreams" / f"{kind}-{name}"
    upstream.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(upstream)],
        check=True,
        capture_output=True,
    )
    _git(upstream, "config", "user.email", "test@example.com")
    _git(upstream, "config", "user.name", "Test User")
    _git(upstream, "config", "receive.denyCurrentBranch", "ignore")
    (upstream / "MEMORY.md").write_text(f"# {kind} {name}\n", encoding="utf-8")
    _git(upstream, "add", "MEMORY.md")
    _git(upstream, "commit", "-m", "initial")
    return upstream


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    yield h


def _cli_invoke(runner: CliRunner, kind: str, *args: str) -> Any:
    return runner.invoke(cli, [kind, *args])


# ------------------------------------------------------------------
# join
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_join_clones_upstream(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    result = runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    assert result.exit_code == 0, result.output

    dest = home / ".engram" / kind / "platform"
    assert dest.is_dir()
    assert (dest / ".git").is_dir()
    assert (dest / "MEMORY.md").is_file()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_join_rejects_existing(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    result = runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    assert result.exit_code != 0
    assert "already" in result.output.lower() or "exist" in result.output.lower()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_join_json_output(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", kind, "join", "platform", str(upstream)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["name"] == "platform"
    assert payload["path"].endswith(f".engram/{kind}/platform")


# ------------------------------------------------------------------
# sync
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_sync_fetches_upstream_commit(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    # Make a new commit in the upstream.
    (upstream / "feedback_new.md").write_text("fresh rule\n", encoding="utf-8")
    _git(upstream, "add", "feedback_new.md")
    _git(upstream, "commit", "-m", "add feedback")

    result = runner.invoke(cli, [kind, "sync", "platform"])
    assert result.exit_code == 0, result.output
    assert (home / ".engram" / kind / "platform" / "feedback_new.md").is_file()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_sync_all(kind: str, home: Path, tmp_path: Path) -> None:
    up_a = _init_upstream(tmp_path, kind, "alpha")
    up_b = _init_upstream(tmp_path, kind, "beta")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "alpha", str(up_a)])
    runner.invoke(cli, [kind, "join", "beta", str(up_b)])

    (up_a / "f.md").write_text("x\n", encoding="utf-8")
    _git(up_a, "add", "f.md")
    _git(up_a, "commit", "-m", "f")

    result = runner.invoke(cli, [kind, "sync", "--all"])
    assert result.exit_code == 0, result.output
    assert (home / ".engram" / kind / "alpha" / "f.md").is_file()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_sync_unknown_errors(kind: str, home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [kind, "sync", "ghost"])
    assert result.exit_code != 0


# ------------------------------------------------------------------
# publish
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_publish_commits_and_pushes(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])

    # Add a new asset locally and publish.
    (home / ".engram" / kind / "platform" / "project_decision.md").write_text(
        "local decision\n", encoding="utf-8"
    )
    result = runner.invoke(cli, [kind, "publish", "platform", "--message", "add decision"])
    assert result.exit_code == 0, result.output

    # Check upstream HEAD commit tree (working tree won't update automatically
    # because we set receive.denyCurrentBranch=ignore — push updates refs only).
    tree = subprocess.run(
        ["git", "-C", str(upstream), "ls-tree", "-r", "HEAD", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "project_decision.md" in tree


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_publish_nothing_to_commit(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    result = runner.invoke(
        cli, [kind, "publish", "platform", "--message", "noop"]
    )
    assert result.exit_code == 0
    assert "nothing" in result.output.lower() or "clean" in result.output.lower()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_publish_requires_message(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    result = runner.invoke(cli, [kind, "publish", "platform"])
    assert result.exit_code != 0


# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_status_clean(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    result = runner.invoke(cli, [kind, "status", "platform"])
    assert result.exit_code == 0
    assert "clean" in result.output.lower()


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_status_reports_dirty(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    (home / ".engram" / kind / "platform" / "feedback_x.md").write_text(
        "dirty\n", encoding="utf-8"
    )
    result = runner.invoke(cli, [kind, "status", "platform"])
    assert result.exit_code == 0
    assert "feedback_x.md" in result.output or "1" in result.output


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_status_json(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "platform")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "platform", str(upstream)])
    result = runner.invoke(
        cli, ["--format", "json", kind, "status", "platform"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["name"] == "platform"
    assert payload["clean"] is True
    assert isinstance(payload["changes"], list)


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_list_empty(kind: str, home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [kind, "list"])
    assert result.exit_code == 0


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_list_shows_joined(kind: str, home: Path, tmp_path: Path) -> None:
    for name in ("alpha", "beta"):
        upstream = _init_upstream(tmp_path, kind, name)
        runner = CliRunner()
        runner.invoke(cli, [kind, "join", name, str(upstream)])
    runner = CliRunner()
    result = runner.invoke(cli, [kind, "list"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_list_json(kind: str, home: Path, tmp_path: Path) -> None:
    upstream = _init_upstream(tmp_path, kind, "alpha")
    runner = CliRunner()
    runner.invoke(cli, [kind, "join", "alpha", str(upstream)])
    result = runner.invoke(cli, ["--format", "json", kind, "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert isinstance(payload, list)
    assert any(entry["name"] == "alpha" for entry in payload)


@pytest.mark.parametrize("kind", SCOPE_KINDS)
def test_group_registered(kind: str) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert kind in result.output


# Keep mypy happy with the `Any` return types in this test module.
from typing import Any  # noqa: E402
