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
import os
from pathlib import Path
from typing import Any

from engram.observer.paths import (
    count_file_for_session,
    queue_file_for_session,
    raw_session_file,
)
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
    raw_payload: str | None = None,
) -> EnqueueResult:
    """Append ``event`` to its session queue.

    Atomic across processes via ``fcntl.flock``. Two caps:

    - per-session ``max_events_per_session`` (10k by default) — protects
      against a single runaway session.
    - global ``max_total_sessions`` (1k by default, security reviewer
      F8) — protects against a flood of distinct session ids that
      would exhaust inodes / disk.

    When ``raw_retention`` is True, ``raw_payload`` — compact JSON of the
    full pre-trim event, captured before ``parse_event`` filtered and
    size-truncated it — is appended to
    ``~/.engram/raw/sessions/<id>.full.jsonl`` so prompt / stderr bodies
    survive for later re-analysis. Falls back to the trimmed queue line
    when ``raw_payload`` is None. The trimmed line goes to the main queue
    regardless.
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
    count_path = count_file_for_session(event.session_id, base=base)

    # fcntl.flock serialises all writers; do depth check + append under
    # one lock so we never race ourselves on the cap. Sidecar count file
    # (A3/F10, 2026-05-02) keeps the depth check O(1) instead of
    # re-scanning the queue on every write.
    with open(queue_path, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            depth_before = _read_count_locked(count_path, queue_file=f)
            if depth_before >= max_events_per_session:
                raise QueueFullError(
                    f"observe queue for session {event.session_id} is full "
                    f"({depth_before} >= {max_events_per_session})"
                )
            f.write(line.lstrip("\n"))  # already has trailing \n; lstrip is paranoia
            f.flush()
            depth_after = depth_before + 1
            _write_count_locked(count_path, depth_after)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    if raw_retention:
        _append_raw(event, encoded, base=base, raw_payload=raw_payload)

    return EnqueueResult(queued_at=event.server_t, queue_depth=depth_after, path=queue_path)


def queue_depth(session_id: str, *, base: Path | None = None) -> int:
    """Return the number of events currently queued for ``session_id``.

    Reads the sidecar ``.count`` file (A3/F10) under a shared lock; falls
    back to a one-shot line scan if the sidecar is missing (legacy queues
    written before the sidecar landed). The shared-lock path never seeds
    the sidecar — concurrent readers would race on the same tmp file —
    so seeding waits for the next enqueue, which holds the exclusive lock.
    """
    path = queue_file_for_session(session_id, base=base)
    if not path.exists():
        return 0
    count_path = count_file_for_session(session_id, base=base)
    with open(path, encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            return _read_count_locked(count_path, queue_file=f, persist=False)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _read_count_locked(count_path: Path, *, queue_file: Any, persist: bool = True) -> int:
    """Return the queue depth from the sidecar, falling back to a one-shot scan.

    Caller MUST hold the queue's flock. With ``persist=True`` the caller
    MUST hold it *exclusively*: a recovered count is seeded back to the
    sidecar, and two shared-lock holders would race each other on the
    sidecar's tmp file. Shared-lock readers pass ``persist=False`` and
    only pay the one-shot scan. Missing/corrupt sidecar means the queue
    predates A3/F10 or a crash interrupted the reset — recover by
    counting once.
    """
    try:
        raw = count_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        depth = _count_lines_unlocked(queue_file)
        if persist:
            _write_count_locked(count_path, depth)
        return depth
    try:
        depth = int(raw)
    except ValueError:
        depth = _count_lines_unlocked(queue_file)
        if persist:
            _write_count_locked(count_path, depth)
        return depth
    return max(0, depth)


def _count_lines_unlocked(f: Any) -> int:
    """Count lines in an open file. Caller MUST hold a flock on the file."""
    f.seek(0)
    count = 0
    for _ in f:
        count += 1
    f.seek(0, 2)  # seek to end so the next write appends
    return count


def _write_count_locked(count_path: Path, depth: int) -> None:
    """Atomically replace the sidecar count file. Caller MUST hold the queue flock."""
    tmp = count_path.with_suffix(count_path.suffix + ".tmp")
    tmp.write_text(f"{depth}\n", encoding="utf-8")
    tmp.replace(count_path)


def _append_raw(
    event: ObserveEvent,
    primary_line: bytes,
    *,
    base: Path | None,
    raw_payload: str | None = None,
) -> None:
    """Append the full-fidelity event to the per-session raw jsonl.

    ``raw_payload`` is compact JSON of the pre-trim event (captured before
    ``parse_event`` filtered and size-truncated it), so prompt / stderr
    bodies survive for later re-analysis. Falls back to the trimmed
    ``primary_line`` when None — the raw file stays valid jsonl either way.
    Not fsync'd (opt-in buffer, 30-day TTL); a crash can drop the last lines.
    """
    raw_path = raw_session_file(event.session_id, base=base)
    raw_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = (raw_payload + "\n").encode("utf-8") if raw_payload is not None else primary_line
    with open(raw_path, "ab") as rf:
        # Owner-only (security review M1): the raw file uniquely holds the
        # full pre-trim prompt / stderr bodies the normal pipeline drops —
        # exactly where secret values live. Enforce 0600 on every open so a
        # pre-existing looser file is tightened too.
        os.fchmod(rf.fileno(), 0o600)
        fcntl.flock(rf.fileno(), fcntl.LOCK_EX)
        try:
            rf.write(line)
            rf.flush()
        finally:
            fcntl.flock(rf.fileno(), fcntl.LOCK_UN)
