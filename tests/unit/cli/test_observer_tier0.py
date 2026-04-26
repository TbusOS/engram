"""T-202 tests for engram.observer.tier0 — mechanical compactor."""

from __future__ import annotations

import json
from pathlib import Path

from engram.observer.daemon import PendingSession
from engram.observer.protocol import parse_event
from engram.observer.queue import enqueue
from engram.observer.tier0 import (
    Tier0Result,
    compact_session,
    extract_facts,
    iter_queue_lines,
    render_narrative_from_timeline,
    run_tier0,
    session_timeline_path,
)


def _enqueue(tmp_path: Path, *events) -> Path:
    """Enqueue several events for sess_abc and return the queue path."""
    for evt in events:
        e = parse_event(
            evt,
            session_id="sess_abc",
            client="claude-code",
            now=evt.get("_t", "2026-04-26T14:00:00.000Z"),
        )
        enqueue(e, base=tmp_path)
    return tmp_path / "observe-queue" / "sess_abc.jsonl"


# ----------------------------------------------------------------------
# extract_facts
# ----------------------------------------------------------------------


def test_extract_keeps_known_fields() -> None:
    rec = extract_facts(
        {
            "t": "2026-04-26T14:00:00Z",
            "kind": "tool_use",
            "tool": "Read",
            "files": ["a.py"],
            "tokens_in": 100,
            "junk_field": "ignored",
        }
    )
    assert rec is not None
    assert rec.kind == "tool_use"
    assert rec.payload["tool"] == "Read"
    assert rec.payload["files"] == ["a.py"]
    assert "junk_field" not in rec.payload


def test_extract_returns_none_on_missing_kind() -> None:
    assert extract_facts({"t": "x"}) is None


def test_extract_returns_none_on_missing_t() -> None:
    assert extract_facts({"kind": "tool_use"}) is None


def test_fact_to_line_is_valid_json() -> None:
    rec = extract_facts(
        {"t": "2026-04-26T14:00:00Z", "kind": "tool_use", "tool": "Edit"}
    )
    assert rec is not None
    parsed = json.loads(rec.to_line())
    assert parsed["t"] == "2026-04-26T14:00:00Z"
    assert parsed["kind"] == "tool_use"
    assert parsed["tool"] == "Edit"


# ----------------------------------------------------------------------
# iter_queue_lines
# ----------------------------------------------------------------------


def test_iter_yields_none_for_missing_file(tmp_path: Path) -> None:
    assert list(iter_queue_lines(tmp_path / "nope.jsonl")) == []


def test_iter_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "q.jsonl"
    p.write_text('{"a": 1}\n\n\n{"b": 2}\n')
    parsed = list(iter_queue_lines(p))
    assert parsed == [{"a": 1}, {"b": 2}]


def test_iter_yields_none_on_bad_lines(tmp_path: Path) -> None:
    p = tmp_path / "q.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"b": 2}\n')
    parsed = list(iter_queue_lines(p))
    assert parsed == [{"a": 1}, None, {"b": 2}]


# ----------------------------------------------------------------------
# compact_session
# ----------------------------------------------------------------------


def test_compact_writes_facts_per_event(tmp_path: Path) -> None:
    queue_path = _enqueue(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        {"event": "tool_use", "tool": "Edit", "files": ["a.py"], "diff_lines_added": 5},
        {"event": "session_end", "outcome": "completed"},
    )
    sessions_dir = tmp_path / ".memory" / "sessions" / "2026-04-26"
    result = compact_session(
        "sess_abc", queue_path=queue_path, sessions_dir=sessions_dir
    )
    assert isinstance(result, Tier0Result)
    assert result.facts_written == 3
    assert result.parse_errors == 0
    timeline = result.timeline_path.read_text().splitlines()
    assert len(timeline) == 3
    rec = json.loads(timeline[0])
    assert rec["tool"] == "Read"
    assert rec["files"] == ["a.py"]


def test_compact_session_idempotent_path(tmp_path: Path) -> None:
    queue_path = _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})
    sessions_dir = tmp_path / "out"
    p1 = session_timeline_path("sess_abc", sessions_dir=sessions_dir)
    r = compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    assert r.timeline_path == p1


def test_compact_creates_sessions_dir(tmp_path: Path) -> None:
    queue_path = _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})
    sessions_dir = tmp_path / "deep" / "nested" / "sessions"
    compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    assert sessions_dir.is_dir()


def test_compact_records_parse_errors(tmp_path: Path) -> None:
    qpath = tmp_path / "q.jsonl"
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text('{"valid": "but missing kind"}\nnot json\n')
    sessions_dir = tmp_path / "out"
    result = compact_session("sess_abc", queue_path=qpath, sessions_dir=sessions_dir)
    assert result.parse_errors == 2
    assert result.facts_written == 0


def test_compact_appends_only(tmp_path: Path) -> None:
    queue_path = _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})
    sessions_dir = tmp_path / "out"
    compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    # second pass on same queue → duplicates expected per docstring
    compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    timeline = (sessions_dir / "sess_abc.timeline.jsonl").read_text().splitlines()
    assert len(timeline) == 2


# ----------------------------------------------------------------------
# Daemon-facing entry
# ----------------------------------------------------------------------


def test_run_tier0_with_pending(tmp_path: Path) -> None:
    queue_path = _enqueue(tmp_path, {"event": "tool_use", "tool": "Read"})
    sessions_dir = tmp_path / "out"
    pending = PendingSession(
        session_id="sess_abc",
        queue_path=queue_path,
        queue_size_bytes=queue_path.stat().st_size,
        last_modified=queue_path.stat().st_mtime,
    )
    result = run_tier0(pending, sessions_dir=sessions_dir)
    assert result.facts_written == 1


# ----------------------------------------------------------------------
# Mechanical narrative
# ----------------------------------------------------------------------


def test_narrative_handles_empty(tmp_path: Path) -> None:
    out = render_narrative_from_timeline(tmp_path / "missing.jsonl")
    assert "# Narrative (mechanical)" in out
    assert "no events" in out


def test_narrative_summarises_events(tmp_path: Path) -> None:
    queue_path = _enqueue(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        {"event": "tool_use", "tool": "Edit", "files": ["a.py"]},
        {"event": "user_prompt", "prompt_chars": 50},
        {"event": "error", "stderr_first_line": "ModuleNotFoundError: foo"},
        {"event": "session_end", "outcome": "completed"},
    )
    sessions_dir = tmp_path / "out"
    compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    timeline_path = sessions_dir / "sess_abc.timeline.jsonl"
    out = render_narrative_from_timeline(timeline_path)
    assert "# Narrative (mechanical)" in out
    assert "## Investigated" in out
    assert "5 tool calls" not in out  # tool_calls=2, not 5
    assert "2 tool calls" in out
    assert "`Read`: 1" in out
    assert "`Edit`: 1" in out
    assert "touched `a.py`" in out
    assert "outcome: completed" in out
    assert "ModuleNotFoundError: foo" in out
