"""Cross-session task linkage — prev_session / next_session pointers.

T-207. Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §5.4.

When Tier 1 finalises a Session asset for a session with a known
``task_hash``, this module:

1. Scans existing Session assets under the same destination root.
2. Finds the most recent one (by ``ended_at``, or ``started_at`` for
   in-flight sessions) with a matching ``task_hash`` whose
   ``ended_at < self.started_at``.
3. Writes ``prev_session`` into the new asset and atomically rewrites
   the predecessor's frontmatter to set ``next_session`` to the new
   id.

The linkage is best-effort: if the predecessor file vanishes between
the scan and the rewrite (concurrent archive, etc.), we log nothing
and skip the back-reference. Tier 1 never raises from a linkage
failure — Stage 0 still works without prev/next chains, just with
slightly worse recency ordering.

The actual file rewrite uses :func:`engram.core.fs.write_atomic`
under :class:`fcntl.flock` so two daemon processes (rare, but
possible during the singleton handoff) cannot interleave writes.
"""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

from engram.core.fs import write_atomic
from engram.observer.session import (
    SessionFrontmatter,
    SessionParseError,
    parse_session_file,
    render_session_file,
    sessions_root,
)

__all__ = [
    "LinkageError",
    "LinkageResult",
    "find_predecessor",
    "link_session_to_predecessor",
    "set_next_session",
]


class LinkageError(RuntimeError):
    """Raised by :func:`set_next_session` for unrecoverable IO errors."""


@dataclass(frozen=True)
class LinkageResult:
    """What linkage did, for logging / tests."""

    prev_session_id: str | None
    prev_path: Path | None
    next_back_reference_written: bool


def _iter_session_paths(memory_dir: Path) -> Iterator[Path]:
    root = sessions_root(memory_dir)
    if not root.is_dir():
        return iter(())
    return (p for p in root.rglob("sess_*.md") if p.is_file())


def find_predecessor(
    *,
    new_session_id: str,
    new_started_at: datetime,
    new_task_hash: str,
    memory_dir: Path,
) -> tuple[str, Path] | None:
    """Find the most recent same-task-hash session whose ``ended_at`` precedes us.

    Returns ``(session_id, path)`` or ``None``. The new session itself
    is excluded by id so re-running Tier 1 cannot create a self-link.
    """
    if not new_task_hash:
        return None

    best_id: str | None = None
    best_path: Path | None = None
    best_ts: datetime | None = None

    for path in _iter_session_paths(memory_dir):
        try:
            fm, _ = parse_session_file(path)
        except (OSError, SessionParseError):
            continue
        if fm.session_id == new_session_id:
            continue
        if fm.task_hash != new_task_hash:
            continue
        candidate_ts = fm.ended_at if fm.ended_at is not None else fm.started_at
        if candidate_ts is None:
            continue
        if candidate_ts >= new_started_at:
            continue
        if best_ts is None or candidate_ts > best_ts:
            best_id = fm.session_id
            best_path = path
            best_ts = candidate_ts

    if best_id is None or best_path is None:
        return None
    return best_id, best_path


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[IO[bytes]]:
    """fcntl.flock LOCK_EX around an existing file.

    Used so the predecessor's frontmatter rewrite cannot interleave
    with another writer. Yields the open file handle for the caller's
    convenience; the caller does NOT need to write through it (we use
    ``write_atomic`` for the actual rewrite).
    """
    with open(path, "rb") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def set_next_session(
    predecessor_path: Path,
    *,
    new_session_id: str,
) -> bool:
    """Rewrite ``predecessor_path`` with ``next_session = new_session_id``.

    Returns True on success, False if the file disappeared / could not
    be parsed. Never raises for concurrent disappearance.
    """
    if not predecessor_path.exists():
        return False
    try:
        with _exclusive_lock(predecessor_path):
            try:
                fm, body = parse_session_file(predecessor_path)
            except (OSError, SessionParseError):
                return False
            if fm.next_session == new_session_id:
                return True
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
                next_session=new_session_id,
                distilled_into=fm.distilled_into,
                scope=fm.scope,
                enforcement=fm.enforcement,
                confidence=fm.confidence,
                extra=fm.extra,
            )
            write_atomic(predecessor_path, render_session_file(updated, body))
        return True
    except OSError:
        return False


def link_session_to_predecessor(
    new_session_path: Path,
    *,
    new_session_id: str,
    new_started_at: datetime,
    new_task_hash: str | None,
    memory_dir: Path,
) -> LinkageResult:
    """Wire ``new_session_path`` into the same-task-hash chain.

    Updates both ends:

    - The new session asset gets ``prev_session = <predecessor id>``.
    - The predecessor gets ``next_session = <new id>``.

    Both writes are atomic. A failure on the back-reference still
    leaves a valid forward link; the missing back-reference will be
    detected by ``engram doctor`` once that check lands.
    """
    if new_task_hash is None or not new_session_path.exists():
        return LinkageResult(
            prev_session_id=None, prev_path=None, next_back_reference_written=False
        )

    predecessor = find_predecessor(
        new_session_id=new_session_id,
        new_started_at=new_started_at,
        new_task_hash=new_task_hash,
        memory_dir=memory_dir,
    )
    if predecessor is None:
        return LinkageResult(
            prev_session_id=None, prev_path=None, next_back_reference_written=False
        )

    prev_id, prev_path = predecessor

    # Forward link on the new session.
    try:
        fm, body = parse_session_file(new_session_path)
    except (OSError, SessionParseError):
        return LinkageResult(
            prev_session_id=prev_id, prev_path=prev_path, next_back_reference_written=False
        )

    if fm.prev_session != prev_id:
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
            prev_session=prev_id,
            next_session=fm.next_session,
            distilled_into=fm.distilled_into,
            scope=fm.scope,
            enforcement=fm.enforcement,
            confidence=fm.confidence,
            extra=fm.extra,
        )
        write_atomic(new_session_path, render_session_file(updated, body))

    back_ok = set_next_session(prev_path, new_session_id=new_session_id)
    return LinkageResult(
        prev_session_id=prev_id,
        prev_path=prev_path,
        next_back_reference_written=back_ok,
    )
