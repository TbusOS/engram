"""T-200 tests for engram.observer.queue — concurrency + atomicity + cap."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from engram.observer.paths import queue_file_for_session, raw_session_file
from engram.observer.protocol import parse_event
from engram.observer.queue import (
    DEFAULT_MAX_EVENTS_PER_SESSION,
    QueueFullError,
    enqueue,
    queue_depth,
)


def _event(session_id: str = "sess_abc", *, kind: str = "tool_use", **extra):
    payload = {"event": kind, **extra}
    return parse_event(
        payload, session_id=session_id, client="claude-code", now="2026-04-26T14:00:00.000Z"
    )


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------


def test_enqueue_creates_file(tmp_path: Path) -> None:
    result = enqueue(_event(), base=tmp_path)
    assert result.path == queue_file_for_session("sess_abc", base=tmp_path)
    assert result.path.exists()
    assert result.queue_depth == 1


def test_enqueue_multiple_appends_in_order(tmp_path: Path) -> None:
    for i in range(5):
        enqueue(_event(tool=f"T{i}"), base=tmp_path)
    path = queue_file_for_session("sess_abc", base=tmp_path)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["tool"] for r in lines] == ["T0", "T1", "T2", "T3", "T4"]


def test_queue_depth_returns_zero_when_missing(tmp_path: Path) -> None:
    assert queue_depth("sess_abc", base=tmp_path) == 0


def test_queue_depth_after_appends(tmp_path: Path) -> None:
    for _ in range(3):
        enqueue(_event(), base=tmp_path)
    assert queue_depth("sess_abc", base=tmp_path) == 3


def test_default_max_is_10000() -> None:
    assert DEFAULT_MAX_EVENTS_PER_SESSION == 10_000


def test_each_line_is_valid_json(tmp_path: Path) -> None:
    enqueue(_event(tool="Read", files=["a.py"]), base=tmp_path)
    enqueue(_event(tool="Edit", files=["b.py"]), base=tmp_path)
    path = queue_file_for_session("sess_abc", base=tmp_path)
    for line in path.read_text().splitlines():
        parsed = json.loads(line)  # would raise on invalid
        assert parsed["client"] == "claude-code"


def test_session_id_carried_in_line(tmp_path: Path) -> None:
    enqueue(_event(session_id="sess_xyz"), base=tmp_path)
    path = queue_file_for_session("sess_xyz", base=tmp_path)
    line = json.loads(path.read_text().strip())
    assert line["session_id"] == "sess_xyz"


# ------------------------------------------------------------------
# Cap enforcement
# ------------------------------------------------------------------


def test_queue_full_raises_when_cap_hit(tmp_path: Path) -> None:
    for _ in range(3):
        enqueue(_event(), base=tmp_path, max_events_per_session=3)
    with pytest.raises(QueueFullError):
        enqueue(_event(), base=tmp_path, max_events_per_session=3)


def test_cap_check_per_session(tmp_path: Path) -> None:
    enqueue(_event(session_id="sess_a"), base=tmp_path, max_events_per_session=1)
    # different session — cap is per-session, so this must succeed.
    enqueue(_event(session_id="sess_b"), base=tmp_path, max_events_per_session=1)


# ------------------------------------------------------------------
# Concurrency
# ------------------------------------------------------------------


def test_concurrent_enqueue_no_interleaving(tmp_path: Path) -> None:
    threads = []
    n_writers = 10
    n_per_writer = 20

    def worker(wid: int) -> None:
        for i in range(n_per_writer):
            enqueue(_event(tool=f"w{wid}-{i}"), base=tmp_path)

    for w in range(n_writers):
        t = threading.Thread(target=worker, args=(w,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    path = queue_file_for_session("sess_abc", base=tmp_path)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == n_writers * n_per_writer
    # Every line parses cleanly; every line has the expected client tag —
    # if writes had interleaved, the JSON would be malformed.
    for line in lines:
        assert line["client"] == "claude-code"


# ------------------------------------------------------------------
# Raw retention
# ------------------------------------------------------------------


def test_raw_retention_off_by_default(tmp_path: Path) -> None:
    enqueue(_event(), base=tmp_path)
    raw_path = raw_session_file("sess_abc", base=tmp_path)
    assert not raw_path.exists()


def test_raw_retention_on_writes_full_file(tmp_path: Path) -> None:
    enqueue(_event(), base=tmp_path, raw_retention=True)
    raw_path = raw_session_file("sess_abc", base=tmp_path)
    assert raw_path.exists()
    content = raw_path.read_text().strip()
    assert json.loads(content)["client"] == "claude-code"
