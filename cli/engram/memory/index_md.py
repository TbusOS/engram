"""MEMORY.md landing-index maintenance (SPEC §7.2 / T-181).

Both helpers touch only the ``## Recently added`` section so manual edits
elsewhere in MEMORY.md stay intact, and both are best-effort no-ops when the
file or section is missing rather than corrupting the landing index.
"""

from __future__ import annotations

from pathlib import Path

from engram.core.fs import write_atomic
from engram.core.paths import memory_dir


def remove_from_memory_index(project_root: Path, *, rel_path: str) -> None:
    """Strip any line in MEMORY.md whose target equals ``rel_path``.

    Mirrors :func:`append_to_memory_index`: we only touch the ``Recently
    added`` section so manual edits elsewhere stay intact. Best-effort —
    no-op when MEMORY.md is missing or the link isn't present. Called
    from ``engram memory archive`` so archived assets do not leave
    dangling links (validate E-IDX-001) behind.
    """
    index = memory_dir(project_root) / "MEMORY.md"
    if not index.is_file():
        return
    text = index.read_text(encoding="utf-8")
    if rel_path not in text:
        return

    marker = "## Recently added"
    section_start = text.find(marker)
    if section_start < 0:
        return
    body_start = text.find("\n", section_start) + 1
    rest = text[body_start:]
    next_section_idx = rest.find("\n## ")
    section_body = rest if next_section_idx < 0 else rest[:next_section_idx]
    after_section = "" if next_section_idx < 0 else rest[next_section_idx:]

    kept_lines: list[str] = []
    for line in section_body.splitlines():
        if line.startswith("- ") and rel_path in line:
            continue
        if line.strip():
            kept_lines.append(line)
    rebuilt_section = "\n".join(kept_lines) + ("\n" if kept_lines else "")
    new_text = text[:body_start] + rebuilt_section + after_section
    if new_text != text:
        write_atomic(index, new_text)


def append_to_memory_index(
    project_root: Path,
    *,
    rel_path: str,
    name: str,
    description: str,
    max_recent: int = 5,
) -> None:
    """Insert one ``- [name](rel_path) — description`` line under
    ``## Recently added`` in MEMORY.md (T-181 / SPEC §7.2).

    Best-effort: no-op when MEMORY.md is missing or already lists the
    asset. Keeps the section bounded to ``max_recent`` lines so the
    landing index does not balloon over time. Newest entry is inserted
    at the top of the section.
    """
    index = memory_dir(project_root) / "MEMORY.md"
    if not index.is_file():
        return
    text = index.read_text(encoding="utf-8")
    if rel_path in text:
        return

    marker = "## Recently added"
    section_start = text.find(marker)
    if section_start < 0:
        # No section to append to — refuse silently rather than corrupt
        # the file. T-181 P1 lands a more aggressive doctor check.
        return

    body_start = text.find("\n", section_start) + 1
    rest = text[body_start:]
    next_section_idx = rest.find("\n## ")
    section_body = rest if next_section_idx < 0 else rest[:next_section_idx]
    after_section = "" if next_section_idx < 0 else rest[next_section_idx:]

    existing_lines = [
        line for line in section_body.splitlines() if line.startswith("- ")
    ]
    new_line = f"- [{name}]({rel_path}) — {description}"
    new_lines = [new_line] + [line for line in existing_lines if line != new_line]
    new_lines = new_lines[:max_recent]

    rebuilt_section = "\n".join(new_lines) + ("\n" if new_lines else "")
    new_text = text[:body_start] + rebuilt_section + after_section
    write_atomic(index, new_text)
