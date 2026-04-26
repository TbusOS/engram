"""T-200 tests for engram.observer.protocol — event schema validation."""

from __future__ import annotations

import json

import pytest

from engram.observer.protocol import (
    ALLOWED_EVENT_KINDS,
    MAX_EVENT_BYTES,
    ProtocolError,
    parse_event,
    render_event_line,
)


# ------------------------------------------------------------------
# parse_event happy path
# ------------------------------------------------------------------


def test_parse_minimal_tool_use() -> None:
    event = parse_event(
        {"event": "tool_use", "tool": "Read"},
        session_id="sess_abc",
        client="claude-code",
        now="2026-04-26T14:00:00.000Z",
    )
    assert event.kind == "tool_use"
    assert event.session_id == "sess_abc"
    assert event.client == "claude-code"
    assert event.server_t == "2026-04-26T14:00:00.000Z"


def test_parse_passes_through_extra_fields() -> None:
    event = parse_event(
        {"event": "tool_use", "tool": "Edit", "files": ["a.py"], "diff_lines": 5},
        session_id="sess_abc",
        client="codex",
    )
    line = json.loads(render_event_line(event))
    assert line["tool"] == "Edit"
    assert line["files"] == ["a.py"]
    assert line["diff_lines"] == 5


def test_to_line_dict_has_canonical_order() -> None:
    event = parse_event(
        {"event": "tool_use", "tool": "Bash"},
        session_id="sess_abc",
        client="cursor",
        now="2026-04-26T00:00:00.000Z",
    )
    d = event.to_line_dict()
    keys = list(d.keys())
    assert keys[:4] == ["t", "client", "session_id", "kind"]


def test_render_line_produces_valid_json() -> None:
    event = parse_event(
        {"event": "session_end", "outcome": "completed"},
        session_id="sess_abc",
        client="manual",
    )
    line = render_event_line(event)
    parsed = json.loads(line)
    assert parsed["kind"] == "session_end"
    assert parsed["outcome"] == "completed"


# ------------------------------------------------------------------
# parse_event error paths
# ------------------------------------------------------------------


def test_parse_rejects_non_dict() -> None:
    with pytest.raises(ProtocolError):
        parse_event("not a dict", session_id="sess_abc", client="claude-code")  # type: ignore[arg-type]


def test_parse_rejects_missing_event_field() -> None:
    with pytest.raises(ProtocolError):
        parse_event({"tool": "Read"}, session_id="sess_abc", client="claude-code")


def test_parse_rejects_unknown_event_kind() -> None:
    with pytest.raises(ProtocolError):
        parse_event(
            {"event": "telepathy"},
            session_id="sess_abc",
            client="claude-code",
        )


def test_parse_rejects_empty_client() -> None:
    with pytest.raises(ProtocolError):
        parse_event(
            {"event": "tool_use"},
            session_id="sess_abc",
            client="",
        )


def test_allowed_kinds_complete() -> None:
    expected = {
        "session_start",
        "tool_use",
        "tool_result",
        "user_prompt",
        "error",
        "session_end",
    }
    assert ALLOWED_EVENT_KINDS == expected


# ------------------------------------------------------------------
# Trim-to-size behavior
# ------------------------------------------------------------------


def test_oversize_event_drops_large_fields() -> None:
    big_blob = "x" * (MAX_EVENT_BYTES * 2)
    event = parse_event(
        {"event": "user_prompt", "prompt": big_blob, "prompt_chars": len(big_blob)},
        session_id="sess_abc",
        client="claude-code",
    )
    line = render_event_line(event)
    assert len(line.encode("utf-8")) <= MAX_EVENT_BYTES
    payload = json.loads(line)
    assert payload.get("truncated") is True
    assert "prompt" not in payload
    # core identifying fields preserved
    assert payload["kind"] == "user_prompt"
    assert payload["prompt_chars"] == len(big_blob)


def test_normal_event_not_marked_truncated() -> None:
    event = parse_event(
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        session_id="sess_abc",
        client="claude-code",
    )
    line = json.loads(render_event_line(event))
    assert "truncated" not in line
