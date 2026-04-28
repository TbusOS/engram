"""Per-client hook payload translators.

Different host clients fire their hooks with different JSON shapes.
This module owns the small, deterministic mappers from each shape into
the engram observer event protocol (:mod:`engram.observer.protocol`).

Translation contracts:

- Input: a dict parsed from the host's stdin payload.
- Output: a dict shaped for ``parse_event`` (i.e. with an ``event``
  field set to one of :data:`~engram.observer.protocol.ALLOWED_EVENT_KINDS`).
- Translators MUST NOT raise on missing fields; if the payload is
  unrecognised, they return ``None`` so the caller can fall through
  to the verbatim path.

The set of supported ``--from`` values is exposed as
:data:`KNOWN_TRANSLATORS` for the CLI's ``--from`` choice list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = [
    "KNOWN_TRANSLATORS",
    "Translator",
    "translate",
    "translate_claude_code",
    "translate_codex",
]


Translator = Callable[[dict[str, Any]], dict[str, Any] | None]


def translate_claude_code(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Map Claude Code's PostToolUse hook payload to an engram event.

    Claude Code's documented shape (Apr 2026):

        {
          "tool_name": "Read",
          "tool_input": {"file_path": "src/foo.ts"},
          "tool_response": "...",
          "session_id": "...",
          ...
        }

    We extract the tool name + a small, low-risk subset of fields. The
    full ``tool_response`` body never enters the observer event because
    of the 4 KB cap.
    """
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return None

    out: dict[str, Any] = {"event": "tool_use", "tool": tool}

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        files = _extract_files_from_input(tool_input)
        if files:
            out["files"] = files

    tool_response = payload.get("tool_response")
    if isinstance(tool_response, str):
        out["result_chars"] = len(tool_response)
    elif isinstance(tool_response, dict):
        # Some Claude Code tool responses arrive as structured objects;
        # we count their JSON serialisation length as a proxy.
        try:
            import json as _json

            out["result_chars"] = len(_json.dumps(tool_response))
        except (TypeError, ValueError):
            pass

    return out


def translate_codex(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Map an OpenAI Codex CLI hook payload to an engram event.

    Codex's hook shape is similar to Claude Code's — same tool_name /
    tool_input / tool_response trio, just renamed in places. We try
    Claude Code's shape first, then a couple of Codex-specific
    fallbacks so we cover both styles without forking logic.
    """
    cc = translate_claude_code(payload)
    if cc is not None:
        return cc
    name = payload.get("name") or payload.get("function_name")
    if isinstance(name, str):
        return {"event": "tool_use", "tool": name}
    return None


def _extract_files_from_input(tool_input: dict[str, Any]) -> list[str]:
    """Pull plausible file paths out of a tool_input mapping.

    Looks at the standard keys Claude Code uses: file_path, paths,
    file_paths, target. Skips non-string values and dedupes while
    preserving first-seen order.
    """
    candidates: list[str] = []
    for key in ("file_path", "path", "target", "filename"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            candidates.append(val)
    for key in ("file_paths", "paths", "files"):
        val = tool_input.get(key)
        if isinstance(val, list):
            for f in val:
                if isinstance(f, str) and f:
                    candidates.append(f)
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


KNOWN_TRANSLATORS: dict[str, Translator] = {
    "claude-code": translate_claude_code,
    "codex": translate_codex,
}


def translate(source: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run the named translator. Returns None for unknown sources."""
    fn = KNOWN_TRANSLATORS.get(source)
    if fn is None:
        return None
    return fn(payload)
