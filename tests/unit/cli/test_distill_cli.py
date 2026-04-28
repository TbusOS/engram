"""T-209 tests for engram distill review/promote/reject."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.observer.session import (
    SessionFrontmatter,
    parse_session_file,
    render_session_file,
    session_path,
)
from engram.observer.tier2 import distill_sessions, SessionForDistill


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Initialise a clean engram project + isolate ~/.engram via HOME."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    proj = tmp_path / "proj"
    init_project(proj, name="test", force=False)
    monkeypatch.setenv("ENGRAM_DIR", str(proj))
    return proj


def _seed_candidate(project: Path, name: str = "auth") -> Path:
    """Drop a Tier-2-style proposed file under .memory/distilled/."""
    sessions = [
        SessionForDistill(
            session_id=f"s{i}",
            task_hash="t1",
            files_touched=(),
            outcome="completed",
            body="ok",
        )
        for i in range(5)
    ]
    response = json.dumps(
        [
            {
                "name": name,
                "description": "Test candidate.",
                "body": "- bullet a\n- bullet b\n",
                "source_sessions": ["s0", "s1"],
            }
        ]
    )
    result = distill_sessions(
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
    result = runner.invoke(cli, ["distill", "review"])
    assert result.exit_code == 0
    assert "no distilled candidates" in result.output


def test_review_lists_candidate(project: Path) -> None:
    _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "review"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "Test candidate." in result.output


def test_review_json(project: Path) -> None:
    _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "review", "--format", "json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert any(r["name"] == "auth" for r in rows)


# ----------------------------------------------------------------------
# promote
# ----------------------------------------------------------------------


def test_promote_unknown_name_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "promote", "nope"])
    assert result.exit_code != 0
    assert "no candidate named nope" in result.output


def test_promote_moves_file_to_local(project: Path) -> None:
    src = _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "promote", "auth"])
    assert result.exit_code == 0, result.output
    assert not src.exists()
    dest = project / ".memory" / "local" / "auth.md"
    assert dest.exists()
    text = dest.read_text()
    assert "type: agent" in text
    assert "bullet a" in text


def test_promote_dry_run_changes_nothing(project: Path) -> None:
    src = _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "promote", "auth", "--dry-run"])
    assert result.exit_code == 0
    assert src.exists()
    dest = project / ".memory" / "local" / "auth.md"
    assert not dest.exists()


def test_promote_overrides_scope_and_enforcement(project: Path) -> None:
    _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "distill",
            "promote",
            "auth",
            "--scope",
            "user",
            "--enforcement",
            "default",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (project / ".memory" / "local" / "auth.md").read_text()
    assert "scope: user" in text
    assert "enforcement: default" in text


def test_promote_stamps_source_sessions(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When source sessions exist on disk, promote should set distilled_into."""
    started = datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    fm = SessionFrontmatter(
        type="session",
        session_id="s0",
        client="claude-code",
        started_at=started,
        ended_at=started,
        task_hash="t1",
    )
    sp = session_path("s0", started_at=started, memory_dir=project / ".memory")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(render_session_file(fm, "body\n"))

    _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "promote", "auth"])
    assert result.exit_code == 0, result.output

    fm_after, _ = parse_session_file(sp)
    assert "auth" in fm_after.distilled_into


# ----------------------------------------------------------------------
# reject
# ----------------------------------------------------------------------


def test_reject_unknown_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "reject", "nope"])
    assert result.exit_code != 0


def test_reject_moves_file_to_archive(project: Path) -> None:
    src = _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "reject", "auth"])
    assert result.exit_code == 0, result.output
    assert not src.exists()
    home = Path(os.environ["HOME"])
    archives = list((home / ".engram" / "archive" / "distilled").rglob("auth.*.md"))
    assert len(archives) == 1


def test_reject_with_reason_includes_slug(project: Path) -> None:
    _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "distill",
            "reject",
            "auth",
            "--reason",
            "Already covered elsewhere",
        ],
    )
    assert result.exit_code == 0
    home = Path(os.environ["HOME"])
    archives = list((home / ".engram" / "archive" / "distilled").rglob("auth.*.md"))
    assert len(archives) == 1
    assert "already-covered-elsewhere" in archives[0].name


def test_reject_dry_run_changes_nothing(project: Path) -> None:
    src = _seed_candidate(project, "auth")
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "reject", "auth", "--dry-run"])
    assert result.exit_code == 0
    assert src.exists()
