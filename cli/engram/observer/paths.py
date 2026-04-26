"""File-system locations for the observer pipeline.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §3.1.

All paths are derived from :func:`engram.core.paths.user_root` so the
observer is portable across the user's projects — a single daemon
instance under ``~/.engram/observer.pid`` services every project.
"""

from __future__ import annotations

import re
from pathlib import Path

from engram.core.paths import user_root

__all__ = [
    "OBSERVER_PID_FILE",
    "archive_raw_dir",
    "observe_queue_dir",
    "queue_file_for_session",
    "raw_queue_file_for_session",
    "raw_session_file",
    "raw_sessions_dir",
    "validate_session_id",
]

# Session-id format: lowercase alphanumeric + ``_`` + ``-``, length 1..96.
# Conservative on purpose — session ids land in filenames so we forbid
# anything that would require shell escaping or that crosses path
# components (no dots, no slashes, no whitespace).
_SESSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")

OBSERVER_PID_FILE = "observer.pid"


class InvalidSessionIdError(ValueError):
    """Raised when a session id violates :data:`_SESSION_ID_RE`."""


def validate_session_id(session_id: str) -> str:
    """Return ``session_id`` after format validation.

    The value is round-tripped untouched so callers can ``session = validate_session_id(raw)``.
    """
    if not isinstance(session_id, str):
        raise InvalidSessionIdError(
            f"session_id must be a string, got {type(session_id).__name__}"
        )
    if not _SESSION_ID_RE.match(session_id):
        raise InvalidSessionIdError(
            f"session_id {session_id!r} must match {_SESSION_ID_RE.pattern} "
            "(lowercase alphanumeric, underscore, hyphen; first char alphanumeric; <= 96 chars)"
        )
    return session_id


def observe_queue_dir(*, base: Path | None = None) -> Path:
    """Return ``~/.engram/observe-queue/`` — the per-session enqueue area.

    ``base`` overrides ``~/.engram/`` for tests; production code never
    passes it.
    """
    root = base if base is not None else user_root()
    return root / "observe-queue"


def queue_file_for_session(session_id: str, *, base: Path | None = None) -> Path:
    """Path to the per-session enqueue jsonl file."""
    sid = validate_session_id(session_id)
    return observe_queue_dir(base=base) / f"{sid}.jsonl"


def raw_sessions_dir(*, base: Path | None = None) -> Path:
    """Path to ``~/.engram/raw/sessions/``."""
    root = base if base is not None else user_root()
    return root / "raw" / "sessions"


def raw_queue_file_for_session(session_id: str, *, base: Path | None = None) -> Path:
    """Per-session full-fidelity jsonl (raw retention, opt-in 30-day TTL)."""
    sid = validate_session_id(session_id)
    return raw_sessions_dir(base=base) / f"{sid}.full.jsonl"


def raw_session_file(session_id: str, *, base: Path | None = None) -> Path:
    """Alias kept for the public observer surface."""
    return raw_queue_file_for_session(session_id, base=base)


def archive_raw_dir(*, base: Path | None = None) -> Path:
    """Path to ``~/.engram/archive/raw/`` for TTL-aged raw events."""
    root = base if base is not None else user_root()
    return root / "archive" / "raw"
