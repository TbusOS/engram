"""Auto-derive a memory name + description from body text.

Powers ``engram memory quick``, which lets a session capture a thought
without the four required ``add`` flags. Pure string functions.
"""

from __future__ import annotations

import re

_HEADING_PREFIX_RE = re.compile(r"^#+\s*")
_QUICK_NAME_CAP = 80
_QUICK_DESC_CAP = 150


def _first_non_blank_line(body: str) -> str:
    for raw in body.splitlines():
        line = raw.strip()
        if line:
            return _HEADING_PREFIX_RE.sub("", line).strip()
    return ""


def derive_quick_name(body: str) -> str:
    """Extract a memory name from ``body`` for ``engram memory quick``.

    Rules: first non-blank line, leading markdown ``#`` stripped, capped at
    80 chars. Falls back to ``"untitled"`` for empty input.
    """
    head = _first_non_blank_line(body)
    if not head:
        return "untitled"
    return head[:_QUICK_NAME_CAP]


def derive_quick_description(body: str) -> str:
    """Extract a description from ``body`` for ``engram memory quick``.

    Rules: collapse newlines to single spaces, strip leading markdown
    heading marks on the first line, cap at 150 chars (truncate with
    ``...`` when longer). Returns empty string for empty input.
    """
    head = _first_non_blank_line(body)
    if not head:
        return ""
    # Collapse remaining body into single-line description; the first line
    # already had heading marks stripped via _first_non_blank_line.
    rest_lines = []
    seen_first = False
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not seen_first:
            seen_first = True
            rest_lines.append(head)
        else:
            rest_lines.append(line)
    flat = " ".join(rest_lines)
    if len(flat) <= _QUICK_DESC_CAP:
        return flat
    return flat[: _QUICK_DESC_CAP - 3] + "..."
