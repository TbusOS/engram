"""Reverse notification — the sender side of the inbox loop (SPEC §10.4, T-96).

The sender does not poll. On their next ``engram review`` or ``engram
status``, the CLI scans ``~/.engram/journal/inter_repo.jsonl`` for
lifecycle transitions (acknowledged / resolved / rejected) on messages
*this repo composed*, surfaces the ones newer than a per-repo watermark,
and advances the watermark so each transition is shown once.

The watermark is a tiny cursor file under
``~/.engram/inbox/.cursors/<sender-slug>.cursor`` holding the *count* of
this repo's transitions already shown. A count (not a timestamp) is used
because two transitions on the same message — acknowledge then resolve —
can share a one-second timestamp, and a ``<=`` timestamp watermark would
silently drop the second one. The journal is append-only (SPEC §10.7),
so the sender's filtered transition stream is stable and a count cursor
is monotonic. It is per-repo so two projects on the same machine don't
consume each other's notifications.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from engram.core.fs import write_atomic
from engram.core.journal import JournalError, read_events
from engram.core.paths import user_root
from engram.inbox.identity import resolve_repo_id, slugify_repo_id

__all__ = [
    "ReverseNotification",
    "collect_reverse_notifications",
    "render_reverse_notifications",
]

_TRANSITION_EVENTS = {
    "message_acknowledged": "ACK",
    "message_resolved": "RESOLVED",
    "message_rejected": "REJECTED",
}


@dataclass(frozen=True, slots=True)
class ReverseNotification:
    """One lifecycle transition on a message this repo sent."""

    event: str  # message_acknowledged / _resolved / _rejected
    label: str  # ACK / RESOLVED / REJECTED
    message_id: str
    to: str
    timestamp: str
    detail: str  # resolution_note / rejection_reason / acknowledged_by


def _journal_path() -> Path:
    return user_root() / "journal" / "inter_repo.jsonl"


def _cursor_path(sender_repo_id: str) -> Path:
    return user_root() / "inbox" / ".cursors" / f"{slugify_repo_id(sender_repo_id)}.cursor"


def _read_cursor(sender_repo_id: str) -> int:
    path = _cursor_path(sender_repo_id)
    if not path.is_file() or path.is_symlink():
        return 0
    try:
        return max(0, int(path.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0


def _write_cursor(sender_repo_id: str, count: int) -> None:
    with suppress(OSError):
        write_atomic(_cursor_path(sender_repo_id), f"{count}\n")


def _detail(event: dict[str, object]) -> str:
    for key in ("resolution_note", "rejection_reason", "acknowledged_by"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def collect_reverse_notifications(
    project_root: Path, *, advance: bool = True
) -> list[ReverseNotification]:
    """Return transitions on this repo's sent messages since the watermark.

    With ``advance=True`` (the default) the watermark moves to the newest
    transition seen, so each is surfaced once across ``review``/``status``.
    Best-effort: a missing/corrupt journal yields an empty list, never an
    error (reverse notification is advisory, not a gate).
    """
    sender = resolve_repo_id(project_root)
    already_shown = _read_cursor(sender)
    try:
        events = list(read_events(_journal_path()))
    except (JournalError, OSError):
        return []

    # All of this sender's transition events, in append (file) order.
    matching: list[ReverseNotification] = []
    for ev in events:
        if ev.get("event") not in _TRANSITION_EVENTS or ev.get("from") != sender:
            continue
        ts = ev.get("timestamp")
        matching.append(
            ReverseNotification(
                event=str(ev["event"]),
                label=_TRANSITION_EVENTS[str(ev["event"])],
                message_id=str(ev.get("message_id", "")),
                to=str(ev.get("to", "")),
                timestamp=str(ts) if isinstance(ts, str) else "",
                detail=_detail(ev),
            )
        )

    # Everything past the count already shown is new.
    fresh = matching[already_shown:]
    if advance and len(matching) != already_shown:
        _write_cursor(sender, len(matching))
    return fresh


def render_reverse_notifications(notes: list[ReverseNotification]) -> str:
    """Render the SPEC §10.4 'updates since last session' block, or ''."""
    if not notes:
        return ""
    lines = ["Cross-repo inbox — updates since last session:"]
    for n in notes:
        mark = {"RESOLVED": "✓", "REJECTED": "✗", "ACK": "•"}.get(n.label, "•")
        lines.append(f"  {mark} {n.label}  {n.to}  (msg {n.message_id})")
        if n.detail:
            lines.append(f"      Note: {n.detail}")
    return "\n".join(lines)
