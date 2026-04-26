"""T-203 tests for engram.observer.session — Session asset frontmatter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engram.observer.cli import observe_cmd
from engram.observer.session import (
    CLIENT_VALUES,
    DEFAULT_ENFORCEMENT,
    DEFAULT_SCOPE,
    OUTCOME_VALUES,
    SessionConfidence,
    SessionParseError,
    parse_session_file,
    parse_session_frontmatter,
    render_session_file,
    session_path,
    sessions_root,
)


# ----------------------------------------------------------------------
# Defaults / enums
# ----------------------------------------------------------------------


def test_default_scope_and_enforcement() -> None:
    # Sessions never run as mandatory.
    assert DEFAULT_SCOPE == "project"
    assert DEFAULT_ENFORCEMENT == "hint"


def test_outcome_values() -> None:
    assert OUTCOME_VALUES == {"completed", "abandoned", "error", "unknown"}


def test_client_values_match_cli() -> None:
    """Drift guard: session.CLIENT_VALUES must mirror observe_cmd's --client choices."""
    cli_choices: set[str] = set()
    for param in observe_cmd.params:
        if param.name == "client":
            cli_choices = set(param.type.choices)  # type: ignore[attr-defined]
            break
    assert cli_choices == CLIENT_VALUES


# ----------------------------------------------------------------------
# parse_session_frontmatter
# ----------------------------------------------------------------------


def test_parse_minimal() -> None:
    fm = parse_session_frontmatter(
        {
            "type": "session",
            "session_id": "sess_abc",
            "client": "claude-code",
            "started_at": "2026-04-26T14:00:00Z",
        }
    )
    assert fm.session_id == "sess_abc"
    assert fm.client == "claude-code"
    assert fm.scope == "project"
    assert fm.enforcement == "hint"
    assert fm.outcome == "unknown"
    assert fm.confidence == SessionConfidence()


def test_parse_full() -> None:
    fm = parse_session_frontmatter(
        {
            "type": "session",
            "session_id": "sess_abc",
            "client": "codex",
            "started_at": "2026-04-26T14:00:00Z",
            "ended_at": "2026-04-26T15:00:00Z",
            "task_hash": "abc123",
            "tool_calls": 47,
            "files_touched": ["src/foo.ts"],
            "files_modified": ["src/foo.ts"],
            "outcome": "completed",
            "prev_session": "sess_xyz",
            "scope": "user",
            "enforcement": "hint",
            "confidence": {
                "validated_score": 1.5,
                "contradicted_score": 0.0,
                "exposure_count": 3,
                "last_validated": "2026-04-26",
            },
        }
    )
    assert fm.tool_calls == 47
    assert fm.files_touched == ("src/foo.ts",)
    assert fm.outcome == "completed"
    assert fm.prev_session == "sess_xyz"
    assert fm.confidence.validated_score == 1.5
    assert fm.confidence.exposure_count == 3
    assert fm.duration_seconds == 3600


def test_parse_preserves_unknown_fields() -> None:
    fm = parse_session_frontmatter(
        {
            "type": "session",
            "session_id": "sess_abc",
            "client": "claude-code",
            "started_at": "2026-04-26T14:00:00Z",
            "future_field": "preserved",
        }
    )
    assert fm.extra == {"future_field": "preserved"}


def test_parse_rejects_wrong_type() -> None:
    with pytest.raises(SessionParseError):
        parse_session_frontmatter(
            {
                "type": "memory",  # wrong
                "session_id": "sess_abc",
                "client": "claude-code",
                "started_at": "2026-04-26T14:00:00Z",
            }
        )


def test_parse_rejects_unknown_client() -> None:
    with pytest.raises(SessionParseError):
        parse_session_frontmatter(
            {
                "type": "session",
                "session_id": "sess_abc",
                "client": "telepathy",
                "started_at": "2026-04-26T14:00:00Z",
            }
        )


def test_parse_rejects_invalid_session_id() -> None:
    with pytest.raises(Exception):  # InvalidSessionIdError or SessionParseError
        parse_session_frontmatter(
            {
                "type": "session",
                "session_id": "BAD/ID",
                "client": "claude-code",
                "started_at": "2026-04-26T14:00:00Z",
            }
        )


def test_parse_rejects_missing_started_at() -> None:
    with pytest.raises(SessionParseError):
        parse_session_frontmatter(
            {"type": "session", "session_id": "sess_abc", "client": "claude-code"}
        )


def test_parse_rejects_invalid_outcome() -> None:
    with pytest.raises(SessionParseError):
        parse_session_frontmatter(
            {
                "type": "session",
                "session_id": "sess_abc",
                "client": "claude-code",
                "started_at": "2026-04-26T14:00:00Z",
                "outcome": "wat",
            }
        )


# ----------------------------------------------------------------------
# Round-trip
# ----------------------------------------------------------------------


def test_round_trip_via_file(tmp_path: Path) -> None:
    fm = parse_session_frontmatter(
        {
            "type": "session",
            "session_id": "sess_abc",
            "client": "claude-code",
            "started_at": "2026-04-26T14:00:00Z",
            "ended_at": "2026-04-26T15:00:00Z",
            "tool_calls": 5,
            "files_touched": ["a.py", "b.py"],
            "outcome": "completed",
        }
    )
    body = "# Narrative\n\nThis was a quick refactor.\n"
    text = render_session_file(fm, body)

    f = tmp_path / "sess.md"
    f.write_text(text)

    fm2, body2 = parse_session_file(f)
    assert fm2.session_id == fm.session_id
    assert fm2.tool_calls == 5
    assert fm2.files_touched == ("a.py", "b.py")
    assert body2 == body


def test_render_preserves_body_exactly(tmp_path: Path) -> None:
    fm = parse_session_frontmatter(
        {
            "type": "session",
            "session_id": "sess_abc",
            "client": "claude-code",
            "started_at": "2026-04-26T14:00:00Z",
        }
    )
    body = "## Custom\n  indented bullet\n\n\nlots of newlines\n"
    text = render_session_file(fm, body)
    f = tmp_path / "sess.md"
    f.write_text(text)
    _, body2 = parse_session_file(f)
    assert body2 == body


def test_parse_rejects_missing_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "sess.md"
    f.write_text("just a body, no frontmatter\n")
    with pytest.raises(SessionParseError):
        parse_session_file(f)


def test_parse_rejects_unclosed_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "sess.md"
    f.write_text("---\ntype: session\nbody but no closing fence\n")
    with pytest.raises(SessionParseError):
        parse_session_file(f)


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def test_sessions_root(tmp_path: Path) -> None:
    assert sessions_root(tmp_path) == tmp_path / "sessions"


def test_session_path_uses_utc_date_bucket(tmp_path: Path) -> None:
    started = datetime(2026, 4, 26, 23, 30, 0, tzinfo=timezone.utc)
    p = session_path("sess_abc", started_at=started, memory_dir=tmp_path)
    assert p == tmp_path / "sessions" / "2026-04-26" / "sess_sess_abc.md"


def test_session_path_handles_naive_dt_as_utc(tmp_path: Path) -> None:
    started = datetime(2026, 4, 26, 14, 0, 0)
    p = session_path("sess_abc", started_at=started, memory_dir=tmp_path)
    assert p == tmp_path / "sessions" / "2026-04-26" / "sess_sess_abc.md"


def test_session_path_validates_id(tmp_path: Path) -> None:
    started = datetime(2026, 4, 26, 14, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception):  # InvalidSessionIdError
        session_path("BAD/ID", started_at=started, memory_dir=tmp_path)
