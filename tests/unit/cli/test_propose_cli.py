"""T-210 tests for engram propose review/promote/reject."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.observer.tier2 import SessionForDistill
from engram.observer.tier3 import propose_procedures


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    init_project(proj, name="test", force=False)
    monkeypatch.setenv("ENGRAM_DIR", str(proj))
    return proj


def _seed_proposal(project: Path, name: str = "deploy-rollback") -> Path:
    sessions = [
        SessionForDistill(
            session_id=f"s{i}",
            task_hash="t1",
            files_touched=(),
            outcome="completed",
            body="ok",
        )
        for i in range(3)
    ]
    response = json.dumps(
        [
            {
                "name": name,
                "when_to_use": "After failed deploys.",
                "steps": ["a", "b", "c"],
                "source_sessions": ["s0"],
            }
        ]
    )
    result = propose_procedures(
        sessions,
        memory_dir=project / ".memory",
        provider=lambda _p: response,
    )
    assert len(result.written_paths) == 1
    return result.written_paths[0]


# ----------------------------------------------------------------------
# review
# ----------------------------------------------------------------------


def test_review_empty(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "review"])
    assert result.exit_code == 0
    assert "no Workflow proposals" in result.output


def test_review_lists_proposal(project: Path) -> None:
    _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "review"])
    assert result.exit_code == 0
    assert "deploy-rollback" in result.output


def test_review_json(project: Path) -> None:
    _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "review", "--format", "json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert any(r["name"] == "deploy-rollback" for r in rows)


# ----------------------------------------------------------------------
# promote
# ----------------------------------------------------------------------


def test_promote_unknown_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "promote", "nope"])
    assert result.exit_code != 0


def test_promote_creates_workflow_scaffold(project: Path) -> None:
    src = _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "promote", "deploy-rollback"])
    assert result.exit_code == 0, result.output
    wdir = project / ".memory" / "workflows" / "deploy-rollback"
    assert (wdir / "README.md").exists()
    assert (wdir / "spine.toml").exists()
    assert (wdir / "metrics.yaml").exists()
    assert (wdir / "fixtures").is_dir()
    # original proposal.md is gone
    assert not src.exists()
    # type field upgraded
    text = (wdir / "README.md").read_text()
    assert "type: workflow" in text


def test_promote_dry_run(project: Path) -> None:
    src = _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["propose", "promote", "deploy-rollback", "--dry-run"]
    )
    assert result.exit_code == 0
    assert src.exists()


# ----------------------------------------------------------------------
# reject
# ----------------------------------------------------------------------


def test_reject_unknown_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "reject", "nope"])
    assert result.exit_code != 0


def test_reject_archives_directory(project: Path) -> None:
    _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "reject", "deploy-rollback"])
    assert result.exit_code == 0, result.output
    src = project / ".memory" / "workflows" / "deploy-rollback"
    assert not src.exists()
    home = Path(os.environ["HOME"])
    archives = list(
        (home / ".engram" / "archive" / "workflows").rglob("deploy-rollback.*")
    )
    assert len(archives) == 1


def test_reject_with_reason(project: Path) -> None:
    _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["propose", "reject", "deploy-rollback", "--reason", "Outdated approach"]
    )
    assert result.exit_code == 0
    home = Path(os.environ["HOME"])
    archives = list(
        (home / ".engram" / "archive" / "workflows").rglob("deploy-rollback.*")
    )
    assert len(archives) == 1
    assert "outdated-approach" in archives[0].name


def test_reject_dry_run(project: Path) -> None:
    _seed_proposal(project, "deploy-rollback")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["propose", "reject", "deploy-rollback", "--dry-run"]
    )
    assert result.exit_code == 0
    src = project / ".memory" / "workflows" / "deploy-rollback"
    assert src.exists()
