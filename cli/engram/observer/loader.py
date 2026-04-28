"""Load Session assets from disk into Relevance Gate inputs.

Bridges :mod:`engram.observer.session` (Session asset frontmatter +
body) and :mod:`engram.relevance.gate` (the Stage 0
:class:`SessionContinuation` view). The Relevance Gate stays a pure
function; this module owns the IO.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from engram.core.paths import user_root
from engram.observer.session import (
    SessionParseError,
    parse_session_file,
    sessions_root,
)
from engram.relevance.gate import SessionContinuation

__all__ = [
    "iter_session_files",
    "load_session_continuations",
    "session_to_continuation",
]


def iter_session_files(
    *,
    project_root: Path | None = None,
) -> Iterator[Path]:
    """Yield every ``sess_*.md`` under the chosen sessions root.

    ``project_root`` selects the same root the Tier 1 writer used:
    project-local ``.memory/sessions`` when given, user-global
    ``~/.engram/sessions`` otherwise. Iteration is undefined-order;
    callers that need recency must sort by frontmatter.
    """
    if project_root is not None:
        root = sessions_root(project_root / ".memory")
    else:
        root = sessions_root(user_root())
    if not root.is_dir():
        return iter(())
    return (p for p in root.rglob("sess_*.md") if p.is_file())


def session_to_continuation(path: Path) -> SessionContinuation | None:
    """Parse one session asset into a SessionContinuation.

    Returns ``None`` for unparseable files (no frontmatter, missing
    fields, etc.) so the caller can keep iterating without trying to
    catch :class:`SessionParseError` itself.
    """
    try:
        fm, body = parse_session_file(path)
    except (OSError, SessionParseError):
        return None
    if fm.task_hash is None:
        return None
    ended = fm.ended_at.date() if fm.ended_at is not None else None
    return SessionContinuation(
        session_id=fm.session_id,
        task_hash=fm.task_hash,
        body=body,
        size_bytes=len(body.encode("utf-8")),
        ended_at=ended,
    )


def load_session_continuations(
    *,
    project_root: Path | None = None,
) -> list[SessionContinuation]:
    """Hydrate every parseable Session asset into a flat list.

    Sessions without ``task_hash`` are silently skipped — they cannot
    be matched by Stage 0 anyway, and including them would bloat the
    in-memory list for callers that pass it to ``run_relevance_gate``.
    """
    out: list[SessionContinuation] = []
    for path in iter_session_files(project_root=project_root):
        cont = session_to_continuation(path)
        if cont is not None:
            out.append(cont)
    return out
