"""Marker-bounded rewrite helper (T-55).

Every adapter target file gets exactly one managed region. The helper
tolerates three initial shapes:

1. **File missing / empty** — write just the managed block.
2. **File has user content, no markers** — prepend the managed block,
   then a blank line, then the user content.
3. **File already has markers** — replace content between them,
   preserving everything outside. If stray extra marker pairs exist
   (malformed prior run), collapse everything between the outermost
   BEGIN and the outermost END into a single managed region.
"""

from __future__ import annotations

__all__ = ["BEGIN_MARKER", "END_MARKER", "apply_managed_block"]


BEGIN_MARKER = "<!-- BEGIN engram -->"
END_MARKER = "<!-- END engram -->"


def apply_managed_block(existing: str, managed_content: str) -> str:
    """Return a new file text with ``managed_content`` in the engram block."""
    body = managed_content.strip("\n")
    managed_section = f"{BEGIN_MARKER}\n{body}\n{END_MARKER}"

    if not existing.strip():
        return managed_section + "\n"

    if BEGIN_MARKER in existing and END_MARKER in existing:
        first = existing.index(BEGIN_MARKER)
        last = existing.rindex(END_MARKER) + len(END_MARKER)
        before = existing[:first].rstrip("\n")
        after = existing[last:].lstrip("\n")
        pieces: list[str] = []
        if before:
            pieces.append(before)
        pieces.append(managed_section)
        if after:
            pieces.append(after)
        joined = "\n\n".join(pieces).rstrip("\n") + "\n"
        return joined

    # No markers yet — prepend.
    user = existing.lstrip("\n").rstrip("\n")
    return f"{managed_section}\n\n{user}\n"
