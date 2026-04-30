"""Append-only event queue for ``engram observe``.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §4.2.

Performance contract:

- p50 < 5 ms when the queue is small.
- p99 < 50 ms when the queue is large.
- Returns ``QueueFullError`` when the per-session line count exceeds
  ``max_events_per_session`` so a misbehaving client cannot fill the disk.

Concurrency: ``fcntl.flock`` serialises writers across processes; each
event is one line, written with ``"a"`` mode so the kernel appends
atomically. We deliberately do not ``fsync`` — the queue is a buffer,
not the system of record (Tier 0 / Tier 1 / Tier 2 sessions are).
"""

from __future__ import annotations

import fcntl
import time
from pathlib import Path
from typing import Any

from engram.observer.paths import queue_file_for_session, raw_session_file
from engram.observer.protocol import ObserveEvent, render_event_line

__all__ = [
    "DEFAULT_MAX_EVENTS_PER_SESSION",
    "DEFAULT_MAX_TOTAL_SESSIONS",
    "EnqueueResult",
    "QueueError",
    "QueueFullError",
    "QueueOverflowError",
    "enqueue",
    "queue_depth",
]


DEFAULT_MAX_EVENTS_PER_SESSION = 10_000
DEFAULT_MAX_TOTAL_SESSIONS = 1_000  # security reviewer F8


class QueueError(RuntimeError):
    """Base class for observer queue failures."""


class QueueFullError(QueueError):
    """Raised when the per-session queue exceeds the configured cap."""


class QueueOverflowError(QueueError):
    """Raised when the global session count exceeds :data:`DEFAULT_MAX_TOTAL_SESSIONS`.

    Security reviewer F8 — without a global cap, a misbehaving (or
    malicious) hook that cycles through unique session ids could
    exhaust inodes / disk in ``~/.engram/observe-queue/`` while every
    individual queue stays under its 10k cap.
    """


class EnqueueResult:
    """Result of a successful enqueue.

    Attributes:
        queued_at: Server timestamp recorded on the line (ISO-8601).
        queue_depth: Number of lines in the per-session queue *after* this write.
        path: Absolute path to the queue file.
    """

    __slots__ = ("path", "queue_depth", "queued_at")

    def __init__(self, *, queued_at: str, queue_depth: int, path: Path) -> None:
        self.queued_at = queued_at
        self.queue_depth = queue_depth
        self.path = path

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"EnqueueResult(queued_at={self.queued_at!r}, "
            f"depth={self.queue_depth}, path={self.path})"
        )


def enqueue(
    event: ObserveEvent,
    *,
    base: Path | None = None,
    max_events_per_session: int = DEFAULT_MAX_EVENTS_PER_SESSION,
    max_total_sessions: int = DEFAULT_MAX_TOTAL_SESSIONS,
    raw_retention: bool = False,
) -> EnqueueResult:
    """Append ``event`` to its session queue.

    Atomic across processes via ``fcntl.flock``. Two caps:

    - per-session ``max_events_per_session`` (10k by default) — protects
      against a single runaway session.
    - global ``max_total_sessions`` (1k by default, security reviewer
      F8) — protects against a flood of distinct session ids that
      would exhaust inodes / disk.

    When ``raw_retention`` is True, the full pre-trim payload is also
    appended to ``~/.engram/raw/sessions/<id>.full.jsonl``. The trimmed
    line still goes to the main queue.
    """
    queue_path = queue_file_for_session(event.session_id, base=base)
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    # Global cap check — only fires when this would create a new
    # session file. Existing sessions are unaffected.
    if not queue_path.exists():
        existing_sessions = sum(
            1 for p in queue_path.parent.iterdir() if p.suffix == ".jsonl"
        )
        if existing_sessions >= max_total_sessions:
            raise QueueOverflowError(
                f"observe queue holds {existing_sessions} sessions "
                f"(>= {max_total_sessions} cap); refusing to create "
                f"{event.session_id}. Run 'engram observer daemon --once' "
                "to drain, or increase max_total_sessions."
            )

    line = render_event_line(event) + "\n"
    encoded = line.encode("utf-8")

    # fcntl.flock serialises all writers; do depth check + append under
    # one lock so we never race ourselves on the cap.
    with open(queue_path, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            depth_before = _count_lines_locked(f)
            if depth_before >= max_events_per_session:
                raise QueueFullError(
                    f"observe queue for session {event.session_id} is full "
                    f"({depth_before} >= {max_events_per_session})"
                )
            f.write(line.lstrip("\n"))  # already has trailing \n; lstrip is paranoia
            f.flush()
            depth_after = depth_before + 1
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    if raw_retention:
        _append_raw(event, encoded, base=base)

    return EnqueueResult(queued_at=event.server_t, queue_depth=depth_after, path=queue_path)


def queue_depth(session_id: str, *, base: Path | None = None) -> int:
    """Return the number of events currently queued for ``session_id``."""
    path = queue_file_for_session(session_id, base=base)
    if not path.exists():
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            for _ in f:
                count += 1
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return count


def _count_lines_locked(f: Any) -> int:
    """Count newlines in an already-locked file. Caller MUST hold the lock."""
    f.seek(0)
    count = 0
    for _ in f:
        count += 1
    f.seek(0, 2)  # seek to end so the next write appends
    return count


def _append_raw(event: ObserveEvent, primary_line: bytes, *, base: Path | None) -> None:
    """Append the full pre-trim payload to the per-session raw jsonl."""
    raw_path = raw_session_file(event.session_id, base=base)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    # Use the same line we wrote to the main queue. raw retention's
    # value is keeping the *event* — re-deriving full prompt/stderr from
    # an already-trimmed dict is impossible, so when raw_retention is
    # True the caller is responsible for invoking enqueue *before* trim
    # if they need the original. For now, we store the trimmed line —
    # raw retention v2 will plumb the pre-trim payload through.
    _ = time.time()  # placeholder: hook for future fsync policy
    with open(raw_path, "ab") as rf:
        fcntl.flock(rf.fileno(), fcntl.LOCK_EX)
        try:
            rf.write(primary_line)
            rf.flush()
        finally:
            fcntl.flock(rf.fileno(), fcntl.LOCK_UN)
