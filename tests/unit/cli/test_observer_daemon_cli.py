"""Q2 tests — engram observer daemon / status CLI commands.

Production-readiness audit (2026-04-29) flagged that ``ObserverDaemon``
had no CLI, so the daemon was never actually runnable. These tests pin
the new ``engram observer daemon`` and ``engram observer status``
commands to the bundled runner factories.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import CliRunner

from engram.cli import cli
from engram.observer.protocol import parse_event
from engram.observer.queue import enqueue


def _enqueue(base: Path, sid: str = "sess_abc") -> Path:
    e = parse_event(
        {"event": "tool_use", "tool": "Read"},
        session_id=sid,
        client="claude-code",
        now="2026-04-30T14:00:00.000Z",
    )
    enqueue(e, base=base)
    return base / "observe-queue" / f"{sid}.jsonl"


def test_daemon_once_runs_one_tick(tmp_path: Path) -> None:
    """--once exits after exactly one iteration."""
    base = tmp_path / "engram"
    base.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observer",
            "daemon",
            "--once",
            "--no-pid-lock",
            "--base",
            str(base),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "stopped after 1 iteration" in result.output


def test_daemon_processes_queued_session(tmp_path: Path) -> None:
    """Tier 0 runs in the daemon tick — timeline file appears."""
    base = tmp_path / "engram"
    base.mkdir()
    _enqueue(base)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observer",
            "daemon",
            "--once",
            "--no-pid-lock",
            "--base",
            str(base),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "tier0=1" in result.output
    timeline = base / "timelines" / "sess_abc.timeline.jsonl"
    assert timeline.exists()


def test_daemon_max_iterations(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observer",
            "daemon",
            "--max-iterations",
            "3",
            "--poll-interval",
            "0",
            "--no-pid-lock",
            "--base",
            str(base),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "stopped after 3 iteration" in result.output


def test_daemon_once_and_max_iterations_conflict(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observer",
            "daemon",
            "--once",
            "--max-iterations",
            "5",
            "--no-pid-lock",
            "--base",
            str(base),
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_daemon_singleton_lock_blocks_second_instance(tmp_path: Path) -> None:
    """If something already holds ~/.engram/observer.pid, the daemon refuses."""
    from engram.observer.daemon import SingletonLock

    base = tmp_path / "engram"
    base.mkdir()
    holder = SingletonLock(base=base)
    holder.acquire()
    try:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["observer", "daemon", "--once", "--base", str(base)],
        )
        assert result.exit_code == 75  # EX_TEMPFAIL
        assert "already running" in result.output
    finally:
        holder.release()


def test_status_no_daemon(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["observer", "status", "--base", str(base)]
    )
    assert result.exit_code == 0
    assert "observer alive:     False" in result.output


def test_status_reports_pending_queue(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    _enqueue(base, sid="sess_xyz")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["observer", "status", "--base", str(base)]
    )
    assert result.exit_code == 0
    assert "sess_xyz" in result.output
    assert "pending sessions:   1" in result.output


def test_status_json(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    _enqueue(base, sid="sess_xyz")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["observer", "status", "--format", "json", "--base", str(base)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["pending_count"] == 1
    assert payload["pending_sessions"][0]["session_id"] == "sess_xyz"


def test_daemon_writes_session_asset_with_project_root(tmp_path: Path) -> None:
    base = tmp_path / "engram"
    base.mkdir()
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    _enqueue(base)
    # Fast-forward queue mtime so Tier 1 idle threshold fires.
    qpath = base / "observe-queue" / "sess_abc.jsonl"
    os.utime(qpath, (1, 1))
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observer",
            "daemon",
            "--once",
            "--idle-threshold",
            "0",
            "--no-pid-lock",
            "--base",
            str(base),
            "--project-root",
            str(project),
        ],
    )
    assert result.exit_code == 0, result.output
    sessions = list((project / ".memory" / "sessions").rglob("sess_*.md"))
    # Tier 1 wrote at least one Session asset.
    assert len(sessions) == 1
