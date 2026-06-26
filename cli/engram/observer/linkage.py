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
guarded by :func:`engram.observer.session.session_frontmatter_lock` —
a per-store advisory lock on a stable sentinel — so two writers
(daemon linkage vs. ``engram distill promote`` in another process,
rare but possible) cannot interleave a read-modify-write. Locking the
data file itself does not work: ``write_atomic`` swaps the inode, so
the lock must live on a path it never replaces (see A9/F9).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from engram.core.fs import write_atomic
from engram.observer.session import (
    SessionFrontmatter,
    SessionParseError,
    parse_session_file,
    render_session_file,
    session_frontmatter_lock,
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


# A session in an older start-date bucket can still be the most recent
# predecessor if it ended later (e.g. it crossed midnight). This is the
# largest such span the newest-first scan accounts for before it stops
# walking older buckets. Generous on purpose — real sessions span minutes
# to hours, so the early stop never skips a genuine most-recent predecessor.
_MAX_SESSION_SPAN_DAYS = 7


def _parse_bucket_date(name: str) -> date | None:
    """Return the UTC date a ``<YYYY-MM-DD>`` bucket name encodes, or None."""
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def _iter_bucket_sessions(scan_dir: Path) -> Iterator[Path]:
    """Yield real (non-symlink) ``sess_*.md`` files directly in ``scan_dir``.

    Security reviewer F5 — refuse to follow symlinks. A malicious project
    bootstrap could plant ``sess_x.md -> /etc/passwd`` and have its content
    slurped into the next Tier 1 / Tier 2 prompt.
    """
    return (
        p
        for p in scan_dir.glob("sess_*.md")
        if p.is_file() and not p.is_symlink()
    )


def _iter_scan_dirs_newest_first(root: Path) -> Iterator[tuple[Path, date | None]]:
    """Yield ``(dir, bucket_date)`` to scan for sessions, date buckets newest first.

    Session assets live at ``sessions/<YYYY-MM-DD>/sess_<id>.md`` where the
    bucket is the UTC date of ``started_at`` — so a reverse-lexical sort of
    the bucket names is reverse-chronological. The yield order is:

    1. ``root`` itself, then any non-date subdir (``bucket_date=None``).
       These are always scanned and never act as an early-stop boundary, so
       a stray top-level or oddly-named file is still found.
    2. date buckets, newest first.

    The walk descends one level — the on-disk contract above. The old flat
    ``rglob`` recursed deeper, but engram only ever writes depth-1 date
    buckets, so this is equivalent in practice.

    Emitting every ``None`` dir before the dated ones means the caller's
    early stop (which only fires on a dated bucket) can never skip a
    non-date dir that happened to sort low. Symlinked dirs are skipped (F5).
    """
    yield root, None
    dated: list[tuple[Path, date]] = []
    for d in root.iterdir():
        if not d.is_dir() or d.is_symlink():
            continue
        bucket_date = _parse_bucket_date(d.name)
        if bucket_date is None:
            yield d, None
        else:
            dated.append((d, bucket_date))
    dated.sort(key=lambda t: t[1], reverse=True)
    for d, bucket_date in dated:
        yield d, bucket_date


def find_predecessor(
    *,
    new_session_id: str,
    new_started_at: datetime,
    new_task_hash: str,
    memory_dir: Path,
) -> tuple[str, Path] | None:
    """Find the most recent same-task-hash session whose ``ended_at`` precedes us.

    Returns ``(session_id, path)`` or ``None``. The new session itself is
    excluded by id so re-running Tier 1 cannot create a self-link.

    A4: scans date buckets newest-first and stops once an older bucket
    cannot hold a candidate that ended after the best so far (given a
    session spans at most :data:`_MAX_SESSION_SPAN_DAYS`). When a recent
    predecessor exists — the common case — this parses a handful of files
    instead of every session in the store.
    """
    if not new_task_hash:
        return None
    root = sessions_root(memory_dir)
    if not root.is_dir():
        return None

    best_id: str | None = None
    best_path: Path | None = None
    best_ts: datetime | None = None

    for scan_dir, bucket_date in _iter_scan_dirs_newest_first(root):
        if (
            best_ts is not None
            and bucket_date is not None
            and bucket_date + timedelta(days=_MAX_SESSION_SPAN_DAYS) < best_ts.date()
        ):
            # Dated buckets arrive newest-first and every non-date dir has
            # already been yielded, so nothing left can end after best_ts.
            break
        for path in _iter_bucket_sessions(scan_dir):
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


def set_next_session(
    predecessor_path: Path,
    *,
    new_session_id: str,
) -> bool:
    """Rewrite ``predecessor_path`` with ``next_session = new_session_id``.

    The whole read-modify-write runs under
    :func:`session_frontmatter_lock` so a concurrent writer (distill
    back-link, re-compaction) cannot clobber the change. Returns True on
    success, False if the file disappeared / could not be parsed. Never
    raises for concurrent disappearance.
    """
    try:
        with session_frontmatter_lock(predecessor_path):
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

    # Forward link on the new session — read-modify-write under the
    # per-store lock so a concurrent distill back-link / re-compaction
    # cannot lose the ``prev_session`` update.
    try:
        with session_frontmatter_lock(new_session_path):
            try:
                fm, body = parse_session_file(new_session_path)
            except (OSError, SessionParseError):
                return LinkageResult(
                    prev_session_id=prev_id,
                    prev_path=prev_path,
                    next_back_reference_written=False,
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
    except OSError:
        return LinkageResult(
            prev_session_id=prev_id, prev_path=prev_path, next_back_reference_written=False
        )

    # NOTE: the lock above is released before set_next_session acquires
    # the same per-store lock for the predecessor. Sequential, never
    # nested — see session_frontmatter_lock's self-deadlock warning.
    back_ok = set_next_session(prev_path, new_session_id=new_session_id)
    return LinkageResult(
        prev_session_id=prev_id,
        prev_path=prev_path,
        next_back_reference_written=back_ok,
    )
