"""T-200 tests for engram.observer.paths — session-id validation + paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from engram.observer.paths import (
    InvalidSessionIdError,
    archive_raw_dir,
    observe_queue_dir,
    queue_file_for_session,
    raw_session_file,
    raw_sessions_dir,
    validate_session_id,
)


# ------------------------------------------------------------------
# validate_session_id
# ------------------------------------------------------------------


def test_validate_accepts_alnum() -> None:
    assert validate_session_id("abc123") == "abc123"


def test_validate_accepts_underscore_and_hyphen() -> None:
    assert validate_session_id("sess_abc-123") == "sess_abc-123"


def test_validate_accepts_max_length() -> None:
    sid = "a" + "b" * 95
    assert validate_session_id(sid) == sid


def test_validate_rejects_empty() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id("")


def test_validate_rejects_uppercase() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id("ABC")


def test_validate_rejects_path_separators() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id("abc/def")


def test_validate_rejects_leading_punct() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id("-abc")


def test_validate_rejects_too_long() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id("a" * 97)


def test_validate_rejects_non_string() -> None:
    with pytest.raises(InvalidSessionIdError):
        validate_session_id(123)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Path derivations
# ------------------------------------------------------------------


def test_observe_queue_dir_under_base(tmp_path: Path) -> None:
    assert observe_queue_dir(base=tmp_path) == tmp_path / "observe-queue"


def test_queue_file_for_session(tmp_path: Path) -> None:
    p = queue_file_for_session("sess_abc", base=tmp_path)
    assert p == tmp_path / "observe-queue" / "sess_abc.jsonl"


def test_queue_file_validates_id(tmp_path: Path) -> None:
    with pytest.raises(InvalidSessionIdError):
        queue_file_for_session("BAD/ID", base=tmp_path)


def test_raw_session_file(tmp_path: Path) -> None:
    p = raw_session_file("sess_abc", base=tmp_path)
    assert p == tmp_path / "raw" / "sessions" / "sess_abc.full.jsonl"


def test_raw_sessions_dir(tmp_path: Path) -> None:
    assert raw_sessions_dir(base=tmp_path) == tmp_path / "raw" / "sessions"


def test_archive_raw_dir(tmp_path: Path) -> None:
    assert archive_raw_dir(base=tmp_path) == tmp_path / "archive" / "raw"
