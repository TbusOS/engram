"""T-207 tests for engram.observer.linkage — prev/next session pointers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engram.observer.linkage import (
    LinkageResult,
    find_predecessor,
    link_session_to_predecessor,
    set_next_session,
)
from engram.observer.session import (
    SessionFrontmatter,
    parse_session_file,
    render_session_file,
    session_path,
)


def _write(
    memory: Path,
    *,
    sid: str,
    th: str | None,
    started: datetime,
    ended: datetime | None,
    prev: str | None = None,
    next_: str | None = None,
) -> Path:
    fm = SessionFrontmatter(
        type="session",
        session_id=sid,
        client="claude-code",
        started_at=started,
        ended_at=ended,
        task_hash=th,
        prev_session=prev,
        next_session=next_,
    )
    p = session_path(sid, started_at=started, memory_dir=memory)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, "body\n"))
    return p


# ----------------------------------------------------------------------
# find_predecessor
# ----------------------------------------------------------------------


def test_find_predecessor_returns_none_with_no_task_hash(tmp_path: Path) -> None:
    found = find_predecessor(
        new_session_id="b",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="",
        memory_dir=tmp_path,
    )
    assert found is None


def test_find_predecessor_returns_none_when_no_match(tmp_path: Path) -> None:
    _write(
        tmp_path,
        sid="a",
        th="other",
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
    )
    found = find_predecessor(
        new_session_id="b",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is None


def test_find_predecessor_picks_most_recent(tmp_path: Path) -> None:
    _write(
        tmp_path,
        sid="old",
        th="x",
        started=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc),
    )
    _write(
        tmp_path,
        sid="recent",
        th="x",
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
    )
    found = find_predecessor(
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is not None
    sid, _ = found
    assert sid == "recent"


def test_find_predecessor_excludes_self(tmp_path: Path) -> None:
    _write(
        tmp_path,
        sid="b",
        th="x",
        started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 27, 15, 0, tzinfo=timezone.utc),
    )
    found = find_predecessor(
        new_session_id="b",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is None


def test_find_predecessor_excludes_future_sessions(tmp_path: Path) -> None:
    """Predecessors must end before the new session starts."""
    _write(
        tmp_path,
        sid="future",
        th="x",
        started=datetime(2026, 4, 28, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 28, 15, 0, tzinfo=timezone.utc),
    )
    found = find_predecessor(
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is None


# ----------------------------------------------------------------------
# set_next_session
# ----------------------------------------------------------------------


def test_set_next_writes_field(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        sid="prev",
        th="x",
        started=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc),
    )
    ok = set_next_session(p, new_session_id="next-id")
    assert ok is True
    fm, _ = parse_session_file(p)
    assert fm.next_session == "next-id"


def test_set_next_idempotent(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        sid="prev",
        th="x",
        started=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc),
        next_="next-id",
    )
    ok = set_next_session(p, new_session_id="next-id")
    assert ok is True
    fm, _ = parse_session_file(p)
    assert fm.next_session == "next-id"


def test_set_next_returns_false_on_missing_file(tmp_path: Path) -> None:
    assert set_next_session(tmp_path / "missing.md", new_session_id="x") is False


def test_set_next_preserves_body(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        sid="prev",
        th="x",
        started=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc),
    )
    set_next_session(p, new_session_id="next-id")
    _, body = parse_session_file(p)
    assert body == "body\n"


# ----------------------------------------------------------------------
# link_session_to_predecessor
# ----------------------------------------------------------------------


def test_link_writes_both_ends(tmp_path: Path) -> None:
    prev_path = _write(
        tmp_path,
        sid="prev",
        th="x",
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
    )
    new_path = _write(
        tmp_path,
        sid="new",
        th="x",
        started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 27, 15, 0, tzinfo=timezone.utc),
    )
    result = link_session_to_predecessor(
        new_path,
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert isinstance(result, LinkageResult)
    assert result.prev_session_id == "prev"
    assert result.next_back_reference_written is True

    fm_prev, _ = parse_session_file(prev_path)
    fm_new, _ = parse_session_file(new_path)
    assert fm_prev.next_session == "new"
    assert fm_new.prev_session == "prev"


def test_link_returns_empty_when_no_predecessor(tmp_path: Path) -> None:
    new_path = _write(
        tmp_path,
        sid="new",
        th="x",
        started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 27, 15, 0, tzinfo=timezone.utc),
    )
    result = link_session_to_predecessor(
        new_path,
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert result.prev_session_id is None
    assert result.next_back_reference_written is False


def test_link_skips_when_no_task_hash(tmp_path: Path) -> None:
    new_path = _write(
        tmp_path,
        sid="new",
        th=None,
        started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        ended=None,
    )
    result = link_session_to_predecessor(
        new_path,
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash=None,
        memory_dir=tmp_path,
    )
    assert result.prev_session_id is None


def test_tier1_auto_links_when_task_hash_set(tmp_path: Path) -> None:
    """End-to-end: Tier 1 + linkage."""
    from engram.observer.protocol import parse_event
    from engram.observer.queue import enqueue
    from engram.observer.tier0 import compact_session
    from engram.observer.tier1 import compact_to_session_asset

    # First session: enqueue + tier 0 + tier 1 with task_hash=x
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    base = tmp_path

    def _enq(sid: str, *events) -> Path:
        for evt in events:
            e = parse_event(
                evt,
                session_id=sid,
                client="claude-code",
                now="2026-04-26T14:00:00.000Z",
            )
            enqueue(e, base=base)
        return base / "observe-queue" / f"{sid}.jsonl"

    q1 = _enq(
        "first",
        {"event": "tool_use", "tool": "Read", "_t": "2026-04-26T14:00:00.000Z"},
        {"event": "session_end", "outcome": "completed", "_t": "2026-04-26T15:00:00.000Z"},
    )
    sessions_dir = base / "timelines"
    compact_session("first", queue_path=q1, sessions_dir=sessions_dir)
    r1 = compact_to_session_asset(
        "first",
        timeline_path=sessions_dir / "first.timeline.jsonl",
        client="claude-code",
        project_root=project,
        provider=lambda _p: "## Investigated\n- one\n",
        task_hash="taskA",
        started_at=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
    )

    # Second session, same task hash, later in time.
    q2 = _enq(
        "second",
        {"event": "tool_use", "tool": "Edit", "_t": "2026-04-27T14:00:00.000Z"},
        {"event": "session_end", "outcome": "completed", "_t": "2026-04-27T15:00:00.000Z"},
    )
    compact_session("second", queue_path=q2, sessions_dir=sessions_dir)
    r2 = compact_to_session_asset(
        "second",
        timeline_path=sessions_dir / "second.timeline.jsonl",
        client="claude-code",
        project_root=project,
        provider=lambda _p: "## Investigated\n- two\n",
        task_hash="taskA",
        started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
    )

    fm1, _ = parse_session_file(r1.asset_path)
    fm2, _ = parse_session_file(r2.asset_path)
    assert fm2.prev_session == "first"
    assert fm1.next_session == "second"
