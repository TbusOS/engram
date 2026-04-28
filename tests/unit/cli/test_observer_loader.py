"""T-206 tests for engram.observer.loader — Session asset → SessionContinuation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engram.observer.loader import (
    iter_session_files,
    load_session_continuations,
    session_to_continuation,
)
from engram.observer.session import (
    SessionFrontmatter,
    render_session_file,
    session_path,
)


def _write_session(
    memory_dir: Path,
    *,
    sid: str,
    th: str | None,
    started: datetime,
    body: str = "narrative",
) -> Path:
    fm = SessionFrontmatter(
        type="session",
        session_id=sid,
        client="claude-code",
        started_at=started,
        ended_at=started,
        task_hash=th,
    )
    p = session_path(sid, started_at=started, memory_dir=memory_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, body))
    return p


# ----------------------------------------------------------------------
# iter_session_files
# ----------------------------------------------------------------------


def test_iter_empty_when_dir_missing(tmp_path: Path) -> None:
    paths = list(iter_session_files(project_root=tmp_path))
    assert paths == []


def test_iter_finds_files(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    memory = project / ".memory"
    _write_session(
        memory, sid="abc", th="x", started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    )
    _write_session(
        memory, sid="def", th="y", started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc)
    )
    paths = list(iter_session_files(project_root=project))
    assert len(paths) == 2


# ----------------------------------------------------------------------
# session_to_continuation
# ----------------------------------------------------------------------


def test_continuation_built_from_file(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    memory = project / ".memory"
    p = _write_session(
        memory,
        sid="abc",
        th="task1",
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        body="## Investigated\n- looked at things\n",
    )
    cont = session_to_continuation(p)
    assert cont is not None
    assert cont.session_id == "abc"
    assert cont.task_hash == "task1"
    assert "looked at things" in cont.body
    assert cont.ended_at is not None


def test_continuation_skips_no_task_hash(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    memory = project / ".memory"
    p = _write_session(
        memory,
        sid="abc",
        th=None,
        started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
    )
    assert session_to_continuation(p) is None


def test_continuation_returns_none_for_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("not a session file")
    assert session_to_continuation(bad) is None


# ----------------------------------------------------------------------
# load_session_continuations
# ----------------------------------------------------------------------


def test_load_skips_no_task_hash(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    memory = project / ".memory"
    _write_session(
        memory, sid="a", th="x", started=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    )
    _write_session(
        memory, sid="b", th=None, started=datetime(2026, 4, 27, 14, 0, tzinfo=timezone.utc)
    )
    out = load_session_continuations(project_root=project)
    ids = sorted(c.session_id for c in out)
    assert ids == ["a"]
