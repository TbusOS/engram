"""Append-only JSONL journals — SPEC §3.4 / §5.1.

Every mutating layer of engram writes an append-only event log:

- ``~/.engram/journal/propagation.jsonl`` — pool propagation events
- ``~/.engram/journal/inter_repo.jsonl`` — inbox send / ack / resolve
- ``~/.engram/journal/consistency.jsonl`` — proposal lifecycle
- ``~/.engram/journal/usage.jsonl`` — usage events that feed confidence updates
- ``workflows/<name>/journal/runs.jsonl`` — one line per spine invocation

The SPEC makes these files load-bearing: tools MUST NOT truncate or rewrite
them, and ``graph.db`` can be rebuilt from them. This module is the only
sanctioned writer — it enforces JSON-object-per-line format, UTF-8 encoding,
and cross-process safety via ``fcntl.flock`` so concurrent workers can append
without interleaving.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

__all__ = ["JournalError", "append_event", "read_events"]


class JournalError(ValueError):
    """Raised when a journal event cannot be serialized or a line cannot be parsed."""


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Append a single JSON object as one line to the JSONL file at ``path``.

    - Creates parent directories if missing.
    - Serializes as compact JSON with UTF-8 (no ``\\uXXXX`` escapes).
    - Uses ``fcntl.flock`` to serialize concurrent writers so lines never
      interleave, even for events larger than ``PIPE_BUF``.
    - ``event`` must be a ``dict``; non-dict top-level values are rejected to
      keep the format uniform.
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be a dict, got {type(event).__name__}")
    try:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise JournalError(f"cannot serialize event to JSON: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.write("\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each JSON object from the JSONL file at ``path`` in file order.

    - Returns an empty iterator if the file does not exist (no journal yet).
    - Skips blank lines (tolerant of editors that add trailing newlines).
    - Raises :class:`JournalError` on a malformed line, tagged with path and
      line number so the operator can locate the corruption quickly.
    - Raises :class:`JournalError` if a line parses to a non-object (JSON
      arrays / strings / numbers at the top level are not valid events).
    """
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalError(f"malformed JSONL at {path}:line {lineno}: {exc.msg}") from exc
            if not isinstance(parsed, dict):
                raise JournalError(
                    f"event at {path}:line {lineno} is not a JSON object "
                    f"(got {type(parsed).__name__})"
                )
            yield parsed
