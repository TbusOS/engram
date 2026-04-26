"""T-204 tests for engram.observer.runners — daemon factory wiring."""

from __future__ import annotations

import json
from pathlib import Path

from engram.observer.daemon import ObserverDaemon, PendingSession
from engram.observer.protocol import parse_event
from engram.observer.queue import enqueue
from engram.observer.runners import (
    make_tier0_runner,
    make_tier1_runner,
    read_client_from_timeline,
    timelines_dir,
)
from engram.observer.session import parse_session_file


def _enqueue(tmp_path: Path, *events) -> None:
    for evt in events:
        e = parse_event(
            evt,
            session_id="sess_abc",
            client="claude-code",
            now="2026-04-26T14:00:00.000Z",
        )
        enqueue(e, base=tmp_path)


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def test_timelines_dir_under_base(tmp_path: Path) -> None:
    assert timelines_dir(base=tmp_path) == tmp_path / "timelines"


def test_read_client_from_missing_returns_none(tmp_path: Path) -> None:
    assert read_client_from_timeline(tmp_path / "missing.jsonl") is None


def test_read_client_from_first_line(tmp_path: Path) -> None:
    f = tmp_path / "t.jsonl"
    f.write_text(
        json.dumps({"t": "x", "client": "cursor", "kind": "tool_use"}) + "\n"
    )
    assert read_client_from_timeline(f) == "cursor"


def test_read_client_skips_bad_lines(tmp_path: Path) -> None:
    f = tmp_path / "t.jsonl"
    f.write_text(
        "not json\n" + json.dumps({"t": "x", "client": "codex", "kind": "tool_use"}) + "\n"
    )
    assert read_client_from_timeline(f) == "codex"


# ----------------------------------------------------------------------
# Tier 0 runner integration
# ----------------------------------------------------------------------


def test_tier0_runner_writes_timeline(tmp_path: Path) -> None:
    _enqueue(tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]})
    runner = make_tier0_runner(base=tmp_path)
    queue_path = tmp_path / "observe-queue" / "sess_abc.jsonl"
    pending = PendingSession(
        session_id="sess_abc",
        queue_path=queue_path,
        queue_size_bytes=queue_path.stat().st_size,
        last_modified=queue_path.stat().st_mtime,
    )
    runner(pending)
    timeline = tmp_path / "timelines" / "sess_abc.timeline.jsonl"
    assert timeline.exists()


# ----------------------------------------------------------------------
# Tier 1 runner integration
# ----------------------------------------------------------------------


def test_tier1_runner_writes_session_asset(tmp_path: Path) -> None:
    _enqueue(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        {"event": "session_end", "outcome": "completed"},
    )
    queue_path = tmp_path / "observe-queue" / "sess_abc.jsonl"
    pending = PendingSession(
        session_id="sess_abc",
        queue_path=queue_path,
        queue_size_bytes=queue_path.stat().st_size,
        last_modified=queue_path.stat().st_mtime,
    )
    # Tier 0 first, so the timeline exists for Tier 1 to read.
    make_tier0_runner(base=tmp_path)(pending)
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    runner = make_tier1_runner(
        base=tmp_path,
        project_root=project,
        provider=lambda _p: "## Investigated\n- runner narrative\n",
    )
    runner(pending)
    sessions = list((project / ".memory" / "sessions").rglob("sess_*.md"))
    assert len(sessions) == 1
    fm, body = parse_session_file(sessions[0])
    assert fm.session_id == "sess_abc"
    assert fm.client == "claude-code"
    assert "runner narrative" in body


def test_tier1_runner_uses_provider_loader(tmp_path: Path) -> None:
    _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})
    queue_path = tmp_path / "observe-queue" / "sess_abc.jsonl"
    pending = PendingSession(
        session_id="sess_abc",
        queue_path=queue_path,
        queue_size_bytes=queue_path.stat().st_size,
        last_modified=queue_path.stat().st_mtime,
    )
    make_tier0_runner(base=tmp_path)(pending)

    calls: list[int] = []

    def loader():
        calls.append(1)
        return lambda _p: "## Investigated\n- via loader\n"

    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    runner = make_tier1_runner(
        base=tmp_path, project_root=project, provider_loader=loader
    )
    runner(pending)
    assert len(calls) == 1


def test_tier1_runner_falls_back_to_mechanical_when_loader_fails(tmp_path: Path) -> None:
    _enqueue(tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]})
    queue_path = tmp_path / "observe-queue" / "sess_abc.jsonl"
    pending = PendingSession(
        session_id="sess_abc",
        queue_path=queue_path,
        queue_size_bytes=queue_path.stat().st_size,
        last_modified=queue_path.stat().st_mtime,
    )
    make_tier0_runner(base=tmp_path)(pending)

    def loader():
        raise RuntimeError("config blew up")

    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    runner = make_tier1_runner(
        base=tmp_path, project_root=project, provider_loader=loader
    )
    runner(pending)
    sessions = list((project / ".memory" / "sessions").rglob("sess_*.md"))
    assert len(sessions) == 1
    body = sessions[0].read_text()
    assert "# Narrative (mechanical)" in body


# ----------------------------------------------------------------------
# End-to-end through ObserverDaemon
# ----------------------------------------------------------------------


def test_daemon_tick_with_real_runners(tmp_path: Path) -> None:
    """One full tick: enqueue → daemon.tick → timeline + session asset on disk."""
    _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})

    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    queue_path = tmp_path / "observe-queue" / "sess_abc.jsonl"
    # Make the file appear "old" so the idle threshold is crossed.
    import os

    os.utime(queue_path, (1_000_000, 1_000_000))

    from engram.observer.daemon import DaemonConfig

    daemon = ObserverDaemon(
        base=tmp_path,
        config=DaemonConfig(session_idle_threshold_seconds=60.0),
        clock=lambda: 1_000_500.0,
        tier0_runner=make_tier0_runner(base=tmp_path),
        tier1_runner=make_tier1_runner(
            base=tmp_path,
            project_root=project,
            provider=lambda _p: "## Investigated\n- daemon-end-to-end\n",
        ),
    )
    daemon.tick()

    timeline = tmp_path / "timelines" / "sess_abc.timeline.jsonl"
    sessions = list((project / ".memory" / "sessions").rglob("sess_*.md"))
    assert timeline.exists()
    assert len(sessions) == 1
    body = sessions[0].read_text()
    assert "daemon-end-to-end" in body
