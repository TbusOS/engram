"""Observer wire protocol — event schema + validation.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §4.

The protocol is intentionally minimal: clients send a single JSON object
per event. This module defines:

- :data:`ALLOWED_EVENT_KINDS` — the closed set of legal ``event`` values.
- :class:`ObserveEvent` — the typed in-memory representation, server-side.
- :func:`parse_event` — parse + validate a raw dict from stdin or file.

The server (``engram observe`` CLI) adds two fields the client cannot
forge: ``t`` (server-side ISO-8601 timestamp) and ``client`` (the
``--client`` flag value). Both are appended to the queue as part of the
canonical jsonl line so downstream consumers do not have to trust the
client's clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "ALLOWED_EVENT_KINDS",
    "MAX_EVENT_BYTES",
    "ObserveEvent",
    "ProtocolError",
    "parse_event",
    "render_event_line",
]


# Event kinds intentionally form a closed set. Adding a new one requires a
# spec amendment so downstream consumers (Tier 0/1/2/3) never have to
# guess about an unknown kind.
ALLOWED_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "session_start",
        "tool_use",
        "tool_result",
        "user_prompt",
        "error",
        "session_end",
    }
)

# Hard ceiling on a single event's serialized size. Beyond this we mark
# ``truncated: true`` and drop large fields (prompt body, stderr body,
# args). Spec §3.3 caps timeline lines at 4 KB.
MAX_EVENT_BYTES = 4096


class ProtocolError(ValueError):
    """Raised when an event payload violates the wire protocol."""


@dataclass(frozen=True)
class ObserveEvent:
    """Validated, server-stamped event ready for queue write.

    ``raw`` carries every field the client supplied minus a small set of
    fields we strip for size reasons. ``server_t`` and ``client`` are
    server-injected and authoritative.
    """

    kind: str
    server_t: str
    client: str
    session_id: str
    raw: dict[str, Any]

    def to_line_dict(self) -> dict[str, Any]:
        """Return the canonical dict that gets serialized to one queue line."""
        # Order is cosmetic but consistent — operators and grep work better
        # when leading fields are predictable.
        out: dict[str, Any] = {
            "t": self.server_t,
            "client": self.client,
            "session_id": self.session_id,
            "kind": self.kind,
        }
        for key, value in self.raw.items():
            if key in out or key == "event":
                continue
            out[key] = value
        return out


def _server_timestamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{datetime.now(tz=timezone.utc).microsecond // 1000:03d}Z"
    )


def parse_event(
    payload: dict[str, Any],
    *,
    session_id: str,
    client: str,
    now: str | None = None,
) -> ObserveEvent:
    """Validate ``payload`` and return an :class:`ObserveEvent`.

    Raises :class:`ProtocolError` for any of:

    - ``payload`` is not a dict.
    - ``event`` field missing or not a string.
    - ``event`` value not in :data:`ALLOWED_EVENT_KINDS`.
    - serialized size exceeds :data:`MAX_EVENT_BYTES` after best-effort
      truncation of large fields.
    """
    if not isinstance(payload, dict):
        raise ProtocolError(
            f"observer event must be a JSON object, got {type(payload).__name__}"
        )

    kind = payload.get("event")
    if not isinstance(kind, str):
        raise ProtocolError("observer event missing required 'event' field (string)")
    if kind not in ALLOWED_EVENT_KINDS:
        allowed = ", ".join(sorted(ALLOWED_EVENT_KINDS))
        raise ProtocolError(
            f"observer event kind {kind!r} not in allowed set: {allowed}"
        )

    if not isinstance(client, str) or not client:
        raise ProtocolError("client tag must be a non-empty string")

    raw = _trim_to_size(dict(payload))

    return ObserveEvent(
        kind=kind,
        server_t=now if now is not None else _server_timestamp(),
        client=client,
        session_id=session_id,
        raw=raw,
    )


def _trim_to_size(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop large optional fields if the line would exceed the cap.

    The fields we drop are well-known content fields (prompt body, stderr
    body, argument blobs). Operators that need full fidelity opt into
    raw retention (``[observer.raw_retention] enabled = true``), which
    writes the full payload to ``~/.engram/raw/sessions/<id>.full.jsonl``
    in addition to the trimmed timeline line.
    """
    import json as _json  # local to keep parse_event small

    line = _json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if len(line.encode("utf-8")) <= MAX_EVENT_BYTES:
        return raw

    # Best-effort drop of well-known large fields, in order of likelihood.
    for big_field in ("stderr", "stderr_full", "prompt", "prompt_full", "args", "result"):
        if big_field in raw:
            del raw[big_field]
            line = _json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            if len(line.encode("utf-8")) <= MAX_EVENT_BYTES:
                raw["truncated"] = True
                return raw

    # Last resort: keep only the core identifying fields.
    pruned = {k: raw[k] for k in ("event", "tool", "files", "exit_code", "outcome") if k in raw}
    pruned["truncated"] = True
    return pruned


def render_event_line(event: ObserveEvent) -> str:
    """Serialize ``event`` to one queue line (no trailing newline)."""
    import json as _json

    return _json.dumps(event.to_line_dict(), ensure_ascii=False, separators=(",", ":"))
