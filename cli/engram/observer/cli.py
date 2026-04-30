"""``engram observe`` — CLI entry for streaming events into the observer queue.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §4.

Reads a single JSON object from stdin (or ``--event``), parses it
through :func:`engram.observer.protocol.parse_event`, and appends to the
per-session queue at ``~/.engram/observe-queue/<session>.jsonl``. The
command is intentionally tiny so client hooks can shell out to it
without paying for a Python interpreter spin-up beyond what engram
itself already costs.

Output:

- ``--format=json`` (default): one JSON ack to stdout.
- ``--format=text``: a one-line human ack (``ok queued at <ts> depth=<n>``).

Failure modes are silent at hook level: any error returns a non-zero
exit code with a JSON error object on stdout, and the hook script's
shell wrapper is expected to ``|| true`` so it never blocks the host
client. The observer's job is best-effort — if something is wrong, the
session resumes by user intent on the next start, just slower.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from engram.observer import paths as observer_paths
from engram.observer.protocol import ProtocolError, parse_event
from engram.observer.queue import (
    DEFAULT_MAX_EVENTS_PER_SESSION,
    DEFAULT_MAX_TOTAL_SESSIONS,
    QueueFullError,
    QueueOverflowError,
    enqueue,
)
from engram.observer.translators import KNOWN_TRANSLATORS, translate

__all__ = ["observe_cmd"]


def _emit(payload: dict[str, Any], *, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        if payload.get("ok"):
            click.echo(
                f"ok queued at {payload['queued_at']} depth={payload['queue_depth']} "
                f"session={payload['session_id']}"
            )
        else:
            click.echo(f"error: {payload.get('reason', 'unknown')}", err=True)


@click.command("observe", help="Append a tool-use event to the observer queue.")
@click.option(
    "--session",
    "session_id",
    required=True,
    metavar="ID",
    help="Session id (lowercase alphanumeric + _-, <=96 chars). Source of truth: client env.",
)
@click.option(
    "--client",
    "client",
    required=True,
    type=click.Choice(
        [
            "claude-code",
            "codex",
            "cursor",
            "gemini-cli",
            "opencode",
            "manual",
            "raw-api",
        ]
    ),
    help="Originating client. Locked enum so downstream tools never guess.",
)
@click.option(
    "--event",
    "event_payload",
    metavar="JSON",
    default=None,
    help="Event payload as JSON. If omitted, reads one JSON object from stdin.",
)
@click.option(
    "--from",
    "from_source",
    type=click.Choice(sorted(KNOWN_TRANSLATORS.keys())),
    default=None,
    help=(
        "Translate the input from a host hook payload shape into the engram "
        "observer event format (e.g. claude-code's tool_name/tool_input/...)."
    ),
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "text"]),
    default="json",
    show_default=True,
)
@click.option(
    "--max-events-per-session",
    type=int,
    default=DEFAULT_MAX_EVENTS_PER_SESSION,
    show_default=True,
    help="Hard cap on per-session queue depth before we refuse new events.",
)
@click.option(
    "--max-total-sessions",
    type=int,
    default=DEFAULT_MAX_TOTAL_SESSIONS,
    show_default=True,
    help="Hard cap on number of distinct sessions in the queue dir (F8).",
)
@click.option(
    "--raw-retention/--no-raw-retention",
    default=False,
    help="Also append to ~/.engram/raw/sessions/<id>.full.jsonl (opt-in, 30-day TTL).",
)
@click.option(
    "--base",
    "base_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    hidden=True,
    help="Override ~/.engram for tests.",
)
def observe_cmd(
    session_id: str,
    client: str,
    event_payload: str | None,
    from_source: str | None,
    fmt: str,
    max_events_per_session: int,
    max_total_sessions: int,
    raw_retention: bool,
    base_dir: Path | None,
) -> None:
    raw_text: str
    raw_text = event_payload if event_payload is not None else sys.stdin.read()

    raw_text = raw_text.strip()
    if not raw_text:
        _emit({"ok": False, "reason": "empty_payload"}, fmt=fmt)
        sys.exit(2)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        _emit({"ok": False, "reason": f"invalid_json: {exc.msg}"}, fmt=fmt)
        sys.exit(2)

    # Validate session id at protocol boundary too — the queue layer
    # validates again, but here we get a friendlier error.
    try:
        observer_paths.validate_session_id(session_id)
    except observer_paths.InvalidSessionIdError as exc:
        _emit({"ok": False, "reason": f"invalid_session_id: {exc}"}, fmt=fmt)
        sys.exit(2)

    if from_source is not None:
        if not isinstance(payload, dict):
            _emit({"ok": False, "reason": "translator_input_not_object"}, fmt=fmt)
            sys.exit(2)
        translated = translate(from_source, payload)
        if translated is None:
            _emit(
                {
                    "ok": False,
                    "reason": f"translator_could_not_map: from={from_source}",
                },
                fmt=fmt,
            )
            sys.exit(2)
        payload = translated

    try:
        event = parse_event(payload, session_id=session_id, client=client)
    except ProtocolError as exc:
        _emit({"ok": False, "reason": f"protocol_error: {exc}"}, fmt=fmt)
        sys.exit(2)

    try:
        result = enqueue(
            event,
            base=base_dir,
            max_events_per_session=max_events_per_session,
            max_total_sessions=max_total_sessions,
            raw_retention=raw_retention,
        )
    except QueueFullError as exc:
        # Queue full is a non-fatal advisory; we exit 0 with ok=false so
        # client hooks can `|| true` without surfacing an error to users.
        _emit({"ok": False, "reason": "queue_full", "detail": str(exc)}, fmt=fmt)
        sys.exit(0)
    except QueueOverflowError as exc:
        _emit({"ok": False, "reason": "queue_overflow", "detail": str(exc)}, fmt=fmt)
        sys.exit(0)

    _emit(
        {
            "ok": True,
            "queued_at": result.queued_at,
            "queue_depth": result.queue_depth,
            "session_id": session_id,
            "client": client,
            "kind": event.kind,
        },
        fmt=fmt,
    )
