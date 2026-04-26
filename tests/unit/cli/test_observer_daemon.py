"""T-201 tests for engram.observer.daemon — singleton lock + processing loop."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engram.observer.daemon import (
    DaemonConfig,
    ObserverDaemon,
    PendingSession,
    SingletonLock,
    SingletonLockError,
    scan_pending_sessions,
)
from engram.observer.protocol import parse_event
from engram.observer.queue import enqueue


# ----------------------------------------------------------------------
# SingletonLock
# ----------------------------------------------------------------------


def test_acquire_and_release(tmp_path: Path) -> None:
    lock = SingletonLock(base=tmp_path)
    lock.acquire()
    try:
        assert lock.path.exists()
        pid_text = lock.path.read_text().strip()
        assert int(pid_text) == os.getpid()
    finally:
        lock.release()
    # release unlinks
    assert not lock.path.exists()


def test_context_manager(tmp_path: Path) -> None:
    with SingletonLock(base=tmp_path) as lock:
        assert lock.path.exists()
    assert not lock.path.exists()


def test_second_lock_blocked_when_holder_alive(tmp_path: Path) -> None:
    lock_a = SingletonLock(base=tmp_path)
    lock_a.acquire()
    try:
        with pytest.raises(SingletonLockError):
            SingletonLock(base=tmp_path).acquire()
    finally:
        lock_a.release()


def test_steal_dead_pid(tmp_path: Path) -> None:
    """Skeleton: write a guaranteed-dead PID, then acquire — must steal."""
    pid_file = tmp_path / "observer.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    # PID 1 is always alive; we want a dead one. Use 999999 — extremely
    # unlikely to be a live process and not protected.
    pid_file.write_text("999999\n")
    lock = SingletonLock(base=tmp_path)
    lock.acquire()
    try:
        assert lock.stolen is True
        # Our PID is now in the file
        assert int(pid_file.read_text().strip()) == os.getpid()
    finally:
        lock.release()


# ----------------------------------------------------------------------
# scan_pending_sessions
# ----------------------------------------------------------------------


def _enqueue_event(tmp_path: Path, session_id: str, **extra) -> None:
    payload = {"event": "tool_use", "tool": "Read", **extra}
    event = parse_event(
        payload, session_id=session_id, client="claude-code", now="2026-04-26T14:00:00.000Z"
    )
    enqueue(event, base=tmp_path)


def test_scan_empty_when_no_queue_dir(tmp_path: Path) -> None:
    assert list(scan_pending_sessions(base=tmp_path)) == []


def test_scan_finds_sessions_with_events(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")
    _enqueue_event(tmp_path, "sess_b")
    pending = list(scan_pending_sessions(base=tmp_path))
    sids = sorted(p.session_id for p in pending)
    assert sids == ["sess_a", "sess_b"]


def test_scan_skips_empty_files(tmp_path: Path) -> None:
    qdir = tmp_path / "observe-queue"
    qdir.mkdir(parents=True)
    (qdir / "empty.jsonl").write_text("")
    _enqueue_event(tmp_path, "sess_a")
    pending = [p.session_id for p in scan_pending_sessions(base=tmp_path)]
    assert pending == ["sess_a"]


def test_scan_orders_by_modified_time(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")
    _enqueue_event(tmp_path, "sess_b")
    qdir = tmp_path / "observe-queue"
    older = qdir / "sess_a.jsonl"
    newer = qdir / "sess_b.jsonl"
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    pending = list(scan_pending_sessions(base=tmp_path))
    assert [p.session_id for p in pending] == ["sess_a", "sess_b"]


# ----------------------------------------------------------------------
# ObserverDaemon main loop
# ----------------------------------------------------------------------


def test_tick_invokes_tier0_per_session(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")
    _enqueue_event(tmp_path, "sess_b")

    seen: list[str] = []

    def tier0(p: PendingSession) -> None:
        seen.append(p.session_id)

    daemon = ObserverDaemon(base=tmp_path, tier0_runner=tier0)
    daemon.tick()
    assert sorted(seen) == ["sess_a", "sess_b"]
    assert daemon.stats.tier0_invocations == 2


def test_idle_session_triggers_tier1(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")

    tier1_seen: list[str] = []

    def tier1(p: PendingSession) -> None:
        tier1_seen.append(p.session_id)

    # Pretend the queue file was last modified well in the past.
    qfile = tmp_path / "observe-queue" / "sess_a.jsonl"
    os.utime(qfile, (1_000_000, 1_000_000))

    daemon = ObserverDaemon(
        base=tmp_path,
        config=DaemonConfig(session_idle_threshold_seconds=60.0),
        tier1_runner=tier1,
        clock=lambda: 1_000_500.0,  # 500 s after the file's mtime
    )
    daemon.tick()
    assert tier1_seen == ["sess_a"]


def test_active_session_does_not_trigger_tier1(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")

    tier1_seen: list[str] = []

    def tier1(p: PendingSession) -> None:
        tier1_seen.append(p.session_id)

    daemon = ObserverDaemon(
        base=tmp_path,
        config=DaemonConfig(session_idle_threshold_seconds=3600.0),
        tier1_runner=tier1,
        clock=lambda: 0.0,  # 0 — file mtime is "now or later"
    )
    daemon.tick()
    assert tier1_seen == []


def test_run_forever_respects_max_iterations(tmp_path: Path) -> None:
    sleeps: list[float] = []
    daemon = ObserverDaemon(
        base=tmp_path,
        config=DaemonConfig(max_iterations=3, poll_interval_seconds=0.01),
        sleeper=lambda s: sleeps.append(s),
    )
    stats = daemon.run_forever(install_signals=False)
    assert stats.iterations == 3
    assert len(sleeps) == 3


def test_run_forever_stops_when_requested(tmp_path: Path) -> None:
    daemon = ObserverDaemon(
        base=tmp_path,
        config=DaemonConfig(poll_interval_seconds=0.0),
        sleeper=lambda s: None,
    )
    daemon.request_stop()
    stats = daemon.run_forever(install_signals=False)
    assert stats.iterations == 0


def test_tier0_exception_does_not_kill_daemon(tmp_path: Path) -> None:
    _enqueue_event(tmp_path, "sess_a")
    _enqueue_event(tmp_path, "sess_b")

    seen: list[str] = []

    def flaky(p: PendingSession) -> None:
        seen.append(p.session_id)
        if p.session_id == "sess_a":
            raise RuntimeError("boom")

    daemon = ObserverDaemon(base=tmp_path, tier0_runner=flaky)
    daemon.tick()
    # both sessions visited; one raised, one succeeded
    assert sorted(seen) == ["sess_a", "sess_b"]
    assert daemon.stats.tier0_invocations == 1  # only the success counted
