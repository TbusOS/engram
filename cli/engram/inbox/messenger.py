"""Send core — dedup + rate limit + journal (SPEC §10.2, §10.5)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from engram.core.fs import write_atomic
from engram.core.journal import append_event, read_events
from engram.core.paths import user_root
from engram.inbox.identity import resolve_repo_id, slugify_repo_id

__all__ = [
    "DEDUP_DETECTED",
    "MAX_PENDING_PER_SENDER",
    "MAX_PER_SENDER_PER_DAY",
    "RATE_LIMIT_HIT",
    "SENT",
    "send_message",
]


# Outcome sentinels returned by send_message so callers can switch
# without string-matching the `detail` field.
SENT = "sent"
DEDUP_DETECTED = "duplicate-merged"
RATE_LIMIT_HIT = "rate-limit-exceeded"

# SPEC §10.5 defaults. Keep in lockstep with the test lock.
MAX_PENDING_PER_SENDER = 20
MAX_PER_SENDER_PER_DAY = 50

VALID_INTENTS: frozenset[str] = frozenset(
    {"bug-report", "api-change", "question", "update-notify", "task"}
)
VALID_SEVERITIES: frozenset[str] = frozenset({"info", "warning", "critical"})


# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------


def _inbox_root(recipient_id: str) -> Path:
    return user_root() / "inbox" / slugify_repo_id(recipient_id)


def _pending_dir(recipient_id: str) -> Path:
    return _inbox_root(recipient_id) / "pending"


def _journal_path() -> Path:
    return user_root() / "journal" / "inter_repo.jsonl"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


# ------------------------------------------------------------------
# Dedup helpers
# ------------------------------------------------------------------


def _dedup_hash(
    sender: str,
    intent: str,
    dedup_key: str | None,
    related_code_refs: list[str] | None,
    first_line: str,
) -> str:
    if dedup_key:
        payload = f"KEY|{dedup_key}|{intent}"
    elif related_code_refs:
        payload = "REFS|" + "|".join(sorted(related_code_refs)) + "|" + intent
    else:
        payload = f"FALLBACK|{sender}|{first_line}|{intent}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_message(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    fm_text, body = text[4:].split("\n---\n", 1)
    fm = yaml.safe_load(fm_text)
    return fm, body.lstrip("\n")


def _render_message(fm: dict[str, Any], body: str) -> str:
    yaml_block = yaml.dump(fm, sort_keys=False, allow_unicode=True)
    tail = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{tail}"


def _find_existing_duplicate(
    recipient_id: str,
    sender: str,
    intent: str,
    dedup_key: str | None,
    related_code_refs: list[str] | None,
    summary: str,
) -> Path | None:
    pending = _pending_dir(recipient_id)
    if not pending.is_dir():
        return None
    first_line = summary.strip().splitlines()[0] if summary else ""
    wanted = _dedup_hash(sender, intent, dedup_key, related_code_refs, first_line)
    for f in pending.glob("*.md"):
        try:
            fm, body = _read_message(f)
        except (yaml.YAMLError, ValueError):
            continue
        if fm.get("from") != sender or fm.get("intent") != intent:
            continue
        existing_first = body.strip().splitlines()[0] if body.strip() else ""
        existing_hash = _dedup_hash(
            fm.get("from", ""),
            fm.get("intent", ""),
            fm.get("dedup_key"),
            fm.get("related_code_refs"),
            existing_first,
        )
        if existing_hash == wanted:
            return f
    return None


# ------------------------------------------------------------------
# Rate limit
# ------------------------------------------------------------------


def _count_pending_from(recipient_id: str, sender: str) -> int:
    pending = _pending_dir(recipient_id)
    if not pending.is_dir():
        return 0
    count = 0
    for f in pending.glob("*.md"):
        try:
            fm, _ = _read_message(f)
        except (yaml.YAMLError, ValueError):
            continue
        if fm.get("from") == sender:
            count += 1
    return count


def _count_24h_from(recipient_id: str, sender: str) -> int:
    cutoff = _now_utc() - timedelta(hours=24)
    journal = _journal_path()
    if not journal.is_file():
        return 0
    count = 0
    for ev in read_events(journal):
        if ev.get("event") != "message_sent":
            continue
        if ev.get("from") != sender or ev.get("to") != recipient_id:
            continue
        try:
            ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            count += 1
    return count


# ------------------------------------------------------------------
# Send core
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _MessageSpec:
    sender: str
    recipient: str
    intent: str
    summary: str
    what: str
    why: str
    how: str
    severity: str
    deadline: str | None
    related_code_refs: list[str] | None
    dedup_key: str | None
    reply_to: str | None


def _build_message_frontmatter(
    spec: _MessageSpec, created: datetime
) -> tuple[dict[str, Any], str]:
    stamp = created.strftime("%Y%m%d-%H%M%S")
    nonce = secrets.token_hex(2)
    message_id = f"{spec.sender}:{stamp}:{nonce}"
    fm: dict[str, Any] = {
        "from": spec.sender,
        "to": spec.recipient,
        "intent": spec.intent,
        "status": "pending",
        "created": _iso(created),
        "message_id": message_id,
        "severity": spec.severity,
    }
    if spec.deadline:
        fm["deadline"] = spec.deadline
    if spec.related_code_refs:
        fm["related_code_refs"] = list(spec.related_code_refs)
    if spec.dedup_key:
        fm["dedup_key"] = spec.dedup_key
    if spec.reply_to:
        fm["reply_to"] = spec.reply_to
    return fm, message_id


def _filename_for(spec: _MessageSpec, created: datetime) -> str:
    stamp = created.strftime("%Y%m%d-%H%M%S")
    sender_slug = slugify_repo_id(spec.sender)
    # Short topic: up to 4 slug-safe words from summary
    words = [
        "".join(ch for ch in w.lower() if ch.isalnum() or ch == "-")
        for w in spec.summary.split()
        if w
    ][:4]
    topic = "-".join(w for w in words if w) or "msg"
    return f"{stamp}-from-{sender_slug}-{topic}.md"


def _render_body(spec: _MessageSpec) -> str:
    parts: list[str] = [spec.summary, ""]
    parts.append(f"**What:** {spec.what}")
    parts.append("")
    parts.append(f"**Why:** {spec.why}")
    if spec.how:
        parts.append("")
        parts.append(f"**How to resolve (if actionable):** {spec.how}")
    return "\n".join(parts) + "\n"


def send_message(
    *,
    project_root: Path,
    to: str,
    intent: str,
    summary: str,
    what: str,
    why: str,
    how: str = "",
    severity: str = "info",
    deadline: str | None = None,
    related_code_refs: list[str] | None = None,
    dedup_key: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    if intent not in VALID_INTENTS:
        raise ValueError(
            f"intent {intent!r} must be one of {sorted(VALID_INTENTS)}"
        )
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"severity {severity!r} must be one of {sorted(VALID_SEVERITIES)}"
        )
    sender = resolve_repo_id(project_root)
    spec = _MessageSpec(
        sender=sender,
        recipient=to,
        intent=intent,
        summary=summary,
        what=what,
        why=why,
        how=how,
        severity=severity,
        deadline=deadline,
        related_code_refs=related_code_refs,
        dedup_key=dedup_key,
        reply_to=reply_to,
    )

    # Dedup check first — duplicates don't count against rate limits.
    existing = _find_existing_duplicate(
        to, sender, intent, dedup_key, related_code_refs, summary
    )
    if existing is not None:
        fm, body = _read_message(existing)
        fm["duplicate_count"] = int(fm.get("duplicate_count", 0)) + 1
        body = (
            body.rstrip("\n")
            + f"\n\n<!-- duplicate received {_iso(_now_utc())} -->\n"
            + f"\n{_render_body(spec).strip()}\n"
        )
        write_atomic(existing, _render_message(fm, body))
        append_event(
            _journal_path(),
            {
                "timestamp": _iso(_now_utc()),
                "event": "message_duplicated",
                "from": sender,
                "to": to,
                "message_id": fm["message_id"],
                "duplicate_count": fm["duplicate_count"],
            },
        )
        return {
            "status": DEDUP_DETECTED,
            "message_id": fm["message_id"],
            "detail": f"merged into existing message (duplicate_count={fm['duplicate_count']})",
        }

    # Rate limits (SPEC §10.5)
    pending_count = _count_pending_from(to, sender)
    if pending_count >= MAX_PENDING_PER_SENDER:
        append_event(
            _journal_path(),
            {
                "timestamp": _iso(_now_utc()),
                "event": "rate_limit_hit",
                "from": sender,
                "to": to,
                "limit_type": "pending_cap",
                "current": pending_count,
                "limit": MAX_PENDING_PER_SENDER,
            },
        )
        return {
            "status": RATE_LIMIT_HIT,
            "detail": (
                f"pending cap {pending_count}/{MAX_PENDING_PER_SENDER} hit; "
                "recipient must process backlog before more messages accepted"
            ),
        }
    day_count = _count_24h_from(to, sender)
    if day_count >= MAX_PER_SENDER_PER_DAY:
        append_event(
            _journal_path(),
            {
                "timestamp": _iso(_now_utc()),
                "event": "rate_limit_hit",
                "from": sender,
                "to": to,
                "limit_type": "daily_window",
                "current": day_count,
                "limit": MAX_PER_SENDER_PER_DAY,
            },
        )
        return {
            "status": RATE_LIMIT_HIT,
            "detail": (
                f"24h window {day_count}/{MAX_PER_SENDER_PER_DAY} hit; "
                "cooldown before more messages accepted"
            ),
        }

    # Normal send
    created = _now_utc()
    fm, message_id = _build_message_frontmatter(spec, created)
    body = _render_body(spec)
    pending = _pending_dir(to)
    pending.mkdir(parents=True, exist_ok=True)
    dest = pending / _filename_for(spec, created)
    write_atomic(dest, _render_message(fm, body))
    append_event(
        _journal_path(),
        {
            "timestamp": _iso(created),
            "event": "message_sent",
            "from": sender,
            "to": to,
            "intent": intent,
            "severity": severity,
            "message_id": message_id,
        },
    )
    return {
        "status": SENT,
        "message_id": message_id,
        "path": str(dest),
    }
