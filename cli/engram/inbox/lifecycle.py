"""Acknowledge / resolve / reject lifecycle transitions (SPEC §10.4)."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engram.core.fs import write_atomic
from engram.core.journal import append_event
from engram.core.paths import user_root
from engram.inbox.identity import slugify_repo_id

__all__ = ["acknowledge", "reject", "resolve"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _inbox_root(recipient_id: str) -> Path:
    return user_root() / "inbox" / slugify_repo_id(recipient_id)


def _find_message(
    recipient_id: str, message_id: str
) -> tuple[Path, dict[str, Any], str]:
    """Return (current_path, fm, body) or raise ValueError if not found.

    Searches all four state dirs; raises if the message is already in a
    terminal state when caller wants to transition.
    """
    root = _inbox_root(recipient_id)
    for state in ("pending", "acknowledged", "resolved", "rejected"):
        d = root / state
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
                fm_text, body = text[4:].split("\n---\n", 1)
                fm = yaml.safe_load(fm_text)
            except (yaml.YAMLError, ValueError):
                continue
            if fm.get("message_id") == message_id:
                return f, fm, body.lstrip("\n")
    raise ValueError(
        f"message {message_id} not found under {_inbox_root(recipient_id)}"
    )


def _move_and_rewrite(
    src: Path, recipient_id: str, new_state: str, fm: dict[str, Any], body: str
) -> Path:
    new_dir = _inbox_root(recipient_id) / new_state
    new_dir.mkdir(parents=True, exist_ok=True)
    dst = new_dir / src.name
    fm["status"] = new_state
    yaml_block = yaml.dump(fm, sort_keys=False, allow_unicode=True)
    tail = body if body.endswith("\n") else body + "\n"
    write_atomic(dst, f"---\n{yaml_block}---\n\n{tail}")
    if src != dst:
        src.unlink()
    return dst


def _journal_event(event_type: str, fm: dict[str, Any], extra: dict) -> None:
    payload: dict[str, Any] = {
        "timestamp": _now_iso(),
        "event": event_type,
        "from": fm.get("from"),
        "to": fm.get("to"),
        "message_id": fm.get("message_id"),
    }
    payload.update(extra)
    append_event(user_root() / "journal" / "inter_repo.jsonl", payload)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def acknowledge(*, recipient_id: str, message_id: str) -> Path:
    src, fm, body = _find_message(recipient_id, message_id)
    state = fm.get("status")
    if state != "pending":
        raise ValueError(
            f"cannot acknowledge; message is in terminal state {state!r} "
            f"(SPEC §10.4: transitions are one-way)"
        )
    fm["acknowledged_at"] = _now_iso()
    dst = _move_and_rewrite(src, recipient_id, "acknowledged", fm, body)
    _journal_event("message_acknowledged", fm, {})
    return dst


def resolve(
    *, recipient_id: str, message_id: str, note: str
) -> Path:
    if not note.strip():
        raise ValueError("resolve requires a non-empty note (SPEC §10.4)")
    src, fm, body = _find_message(recipient_id, message_id)
    state = fm.get("status")
    if state not in ("pending", "acknowledged"):
        raise ValueError(
            f"cannot resolve; message is in terminal state {state!r}"
        )
    fm["resolved_at"] = _now_iso()
    fm["resolution_note"] = note
    dst = _move_and_rewrite(src, recipient_id, "resolved", fm, body)
    _journal_event("message_resolved", fm, {"resolution_note": note})
    return dst


def reject(
    *, recipient_id: str, message_id: str, reason: str
) -> Path:
    if not reason.strip():
        raise ValueError("reject requires a non-empty reason (SPEC §10.4)")
    src, fm, body = _find_message(recipient_id, message_id)
    state = fm.get("status")
    if state not in ("pending", "acknowledged"):
        raise ValueError(
            f"cannot reject; message is in terminal state {state!r}"
        )
    fm["rejected_at"] = _now_iso()
    fm["rejection_reason"] = reason
    dst = _move_and_rewrite(src, recipient_id, "rejected", fm, body)
    _journal_event("message_rejected", fm, {"rejection_reason": reason})
    return dst


# Silence unused-import noise in some type-checkers:
_ = shutil
