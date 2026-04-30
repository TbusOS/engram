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

import re
from collections.abc import Callable
from typing import Any

__all__ = [
    "KNOWN_TRANSLATORS",
    "REDACTED_PATH_MARKER",
    "SECRET_PATH_PATTERNS",
    "Translator",
    "is_secret_path",
    "redact_path",
    "translate",
    "translate_claude_code",
    "translate_codex",
]


# Security reviewer F4 — file paths flow from hook payloads into the
# Session asset frontmatter, the Tier 0 timeline, and (worst case) the
# Tier 2 / Tier 3 prompt sent to a hosted LLM. Even just the *name*
# of ``/etc/shadow`` or ``~/.aws/credentials`` is sensitive metadata,
# and the LLM might learn enough from a session body to attempt path-
# guessing in a later interaction. We never let secret-bearing paths
# enter the pipeline; they get replaced by a marker string instead.
SECRET_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.aws(/|$)"),
    re.compile(r"(^|/)\.ssh(/|$)"),
    re.compile(r"(^|/)\.gnupg(/|$)"),
    re.compile(r"(^|/)\.kube(/|$)"),
    re.compile(r"(^|/)\.netrc$"),
    re.compile(r"(^|/)\.pgpass$"),
    re.compile(r"(^|/)\.env(\.[^/]+)?$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"\.p12$"),
    re.compile(r"\.pfx$"),
    re.compile(r"id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$"),
    re.compile(r"^/etc/(shadow|passwd|sudoers|gshadow)(/|$)"),
    re.compile(r"(^|/)credentials(\.[a-z0-9]+)?$", re.IGNORECASE),
    re.compile(r"(^|/)secret[s]?(/|\.|$)", re.IGNORECASE),
)

REDACTED_PATH_MARKER = "<redacted-secret-path>"


def is_secret_path(path: str) -> bool:
    """Return True when ``path`` matches any :data:`SECRET_PATH_PATTERNS`."""
    if not isinstance(path, str) or not path:
        return False
    return any(rx.search(path) for rx in SECRET_PATH_PATTERNS)


def redact_path(path: str) -> str:
    """Return ``path`` if safe, else :data:`REDACTED_PATH_MARKER`."""
    return REDACTED_PATH_MARKER if is_secret_path(path) else path


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
    preserving first-seen order. Paths matching
    :data:`SECRET_PATH_PATTERNS` are replaced with
    :data:`REDACTED_PATH_MARKER` (security reviewer F4).
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
        redacted = redact_path(c)
        if redacted not in seen:
            seen.add(redacted)
            out.append(redacted)
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
