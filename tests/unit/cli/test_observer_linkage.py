"""T-207 tests for engram.observer.linkage — prev/next session pointers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engram.core.fs import write_atomic
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


def test_find_predecessor_cross_midnight_end_wins(tmp_path: Path) -> None:
    """A session in an older *start-date* bucket that ENDED later still wins.

    Date buckets are keyed by ``started_at``'s UTC date, but predecessors
    rank by ``ended_at`` — so a newest-first scan must not stop at the first
    bucket that holds a match. ``spanner`` started Apr 25 (older bucket) but
    ended after ``earlybird`` which started and ended Apr 26.
    """
    _write(
        tmp_path,
        sid="spanner",
        th="x",
        started=datetime(2026, 4, 25, 23, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 13, 0, tzinfo=timezone.utc),
    )
    _write(
        tmp_path,
        sid="earlybird",
        th="x",
        started=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 9, 0, tzinfo=timezone.utc),
    )
    found = find_predecessor(
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is not None
    assert found[0] == "spanner"


def test_find_predecessor_early_stops_past_old_buckets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newest-first scan stops before parsing buckets too old to win.

    A4: ``find_predecessor`` must not parse every session on the store each
    time Tier 1 finalises one. A recent predecessor plus ten much-older
    same-task sessions: the scan finds the recent one without touching the
    ancient buckets.
    """
    _write(
        tmp_path,
        sid="pred",
        th="x",
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        ended=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
    )
    for i in range(1, 11):
        d = datetime(2026, 4, i, 12, 0, tzinfo=timezone.utc)
        _write(tmp_path, sid=f"old{i}", th="x", started=d, ended=d)

    import engram.observer.linkage as linkage_mod

    real_parse = linkage_mod.parse_session_file
    parsed: list[str] = []

    def _counting(path: Path) -> tuple[SessionFrontmatter, str]:
        parsed.append(path.name)
        return real_parse(path)

    monkeypatch.setattr(linkage_mod, "parse_session_file", _counting)

    found = find_predecessor(
        new_session_id="new",
        new_started_at=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc),
        new_task_hash="x",
        memory_dir=tmp_path,
    )
    assert found is not None and found[0] == "pred"
    # Only the recent bucket is parsed; the April 1-10 buckets are skipped.
    assert parsed == ["sess_pred.md"], parsed


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


# ----------------------------------------------------------------------
# A9/F9 (2026-06-13) — shared lock prevents lost updates
# ----------------------------------------------------------------------


def test_concurrent_frontmatter_writes_no_lost_update(tmp_path: Path) -> None:
    """N threads each append a distinct distilled_into entry under the
    shared per-store lock; all entries must survive.

    This is the lost-update the A9/F9 fix targets: every thread does a
    parse -> modify -> write_atomic, and write_atomic swaps the inode.
    Locking the data file (the old behavior) serialized on the soon-to-be
    orphaned inode and lost writes; the per-store sentinel does not.
    """
    import threading

    from engram.observer.session import session_frontmatter_lock

    started = datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    path = _write(tmp_path, sid="target", th="t1", started=started, ended=started)

    def stamp(tag: str) -> None:
        with session_frontmatter_lock(path):
            fm, body = parse_session_file(path)
            updated = SessionFrontmatter(
                type=fm.type,
                session_id=fm.session_id,
                client=fm.client,
                started_at=fm.started_at,
                ended_at=fm.ended_at,
                task_hash=fm.task_hash,
                tool_calls=fm.tool_calls,
                files_touched=fm.files_touched,
                files_modified=fm.files_modified,
                outcome=fm.outcome,
                error_summary=fm.error_summary,
                prev_session=fm.prev_session,
                next_session=fm.next_session,
                distilled_into=(*fm.distilled_into, tag),
                scope=fm.scope,
                enforcement=fm.enforcement,
                confidence=fm.confidence,
                extra=fm.extra,
            )
            write_atomic(path, render_session_file(updated, body))

    tags = [f"d{i}" for i in range(12)]
    threads = [threading.Thread(target=stamp, args=(t,)) for t in tags]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    fm, _ = parse_session_file(path)
    assert sorted(fm.distilled_into) == sorted(tags)


def test_linkage_and_distilled_into_coexist(tmp_path: Path) -> None:
    """A predecessor stamped with distilled_into keeps it after linkage
    writes next_session (and vice versa)."""
    from engram.observer.session import session_frontmatter_lock

    early = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    late = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    pred = _write(tmp_path, sid="pred", th="t1", started=early, ended=early)
    new = _write(tmp_path, sid="newer", th="t1", started=late, ended=None)

    # Distill stamps the predecessor first.
    with session_frontmatter_lock(pred):
        fm, body = parse_session_file(pred)
        write_atomic(
            pred,
            render_session_file(
                SessionFrontmatter(
                    type=fm.type,
                    session_id=fm.session_id,
                    client=fm.client,
                    started_at=fm.started_at,
                    ended_at=fm.ended_at,
                    task_hash=fm.task_hash,
                    distilled_into=("recurring-files",),
                ),
                body,
            ),
        )

    # Then linkage wires next_session onto the same predecessor.
    link_session_to_predecessor(
        new,
        new_session_id="newer",
        new_started_at=late,
        new_task_hash="t1",
        memory_dir=tmp_path,
    )

    fm, _ = parse_session_file(pred)
    assert fm.next_session == "newer"
    assert fm.distilled_into == ("recurring-files",)
