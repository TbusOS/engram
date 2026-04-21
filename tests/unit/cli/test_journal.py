"""T-15 tests for engram.core.journal — append-only JSONL helpers."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from engram.core.journal import JournalError, append_event, read_events


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------


def test_append_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_event(path, {"kind": "hello"})
    assert path.exists()


def test_append_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "events.jsonl"
    append_event(path, {"kind": "hello"})
    assert path.exists()


def test_append_multiple_events_preserves_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    for i in range(5):
        append_event(path, {"i": i})
    events = list(read_events(path))
    assert events == [{"i": 0}, {"i": 1}, {"i": 2}, {"i": 3}, {"i": 4}]


def test_append_writes_one_line_per_event(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_event(path, {"a": 1})
    append_event(path, {"b": 2})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_append_file_ends_with_newline(tmp_path: Path) -> None:
    """Every appended event terminates with \\n so the next append starts on a fresh line."""
    path = tmp_path / "events.jsonl"
    append_event(path, {"a": 1})
    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")


def test_unicode_and_nested_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = {
        "message": "engram — 你好 🧠",
        "nested": {"list": [1, 2, 3], "bool": True, "null": None},
        "floats": 3.14,
    }
    append_event(path, event)
    events = list(read_events(path))
    assert events == [event]


def test_ascii_not_escaped(tmp_path: Path) -> None:
    """ensure_ascii=False — Chinese stays as UTF-8, not \\uXXXX escapes."""
    path = tmp_path / "events.jsonl"
    append_event(path, {"text": "你好"})
    raw = path.read_text(encoding="utf-8")
    assert "你好" in raw


# ------------------------------------------------------------------
# read_events
# ------------------------------------------------------------------


def test_read_events_missing_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.jsonl"
    assert list(read_events(path)) == []


def test_read_events_empty_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")
    assert list(read_events(path)) == []


def test_read_events_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text('{"a": 1}\n\n{"b": 2}\n\n', encoding="utf-8")
    assert list(read_events(path)) == [{"a": 1}, {"b": 2}]


def test_read_events_raises_on_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text('{"a": 1}\nnot json\n', encoding="utf-8")
    events = read_events(path)
    next(events)  # first line ok
    with pytest.raises(JournalError, match="line 2"):
        next(events)


def test_read_events_error_includes_path(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(JournalError, match="bad.jsonl"):
        list(read_events(path))


def test_read_events_rejects_non_object_line(tmp_path: Path) -> None:
    """A JSON array or scalar at line level is not a valid event."""
    path = tmp_path / "events.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(JournalError, match="object"):
        list(read_events(path))


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------


def test_append_event_rejects_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with pytest.raises(TypeError, match="dict"):
        append_event(path, [1, 2, 3])  # type: ignore[arg-type]


def test_append_event_rejects_non_json_serializable(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    class NotJSON:
        pass

    with pytest.raises(JournalError, match="serialize"):
        append_event(path, {"blob": NotJSON()})  # type: ignore[dict-item]


# ------------------------------------------------------------------
# Concurrency
# ------------------------------------------------------------------


def test_concurrent_appends_preserve_every_event(tmp_path: Path) -> None:
    """50 threads × 20 events each must yield 1000 well-formed events, no loss or corruption."""
    path = tmp_path / "events.jsonl"
    n_threads = 50
    per_thread = 20

    def worker(tid: int) -> None:
        for i in range(per_thread):
            append_event(path, {"t": tid, "i": i})

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = list(read_events(path))
    assert len(events) == n_threads * per_thread
    # Every (t, i) pair appears exactly once.
    seen = {(ev["t"], ev["i"]) for ev in events}
    assert len(seen) == n_threads * per_thread
