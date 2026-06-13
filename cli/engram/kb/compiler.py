"""KB digest compiler + staleness detection (SPEC §6.5).

The default compile is **rule-based and fully offline** (``model:
local/none``): it lifts each chapter's headings and lead paragraph into
a navigable digest, guaranteeing every chapter gets at least one section
heading and a cross-link back to its source. ``_compiled.md`` is a
cached derivation — the chapters remain authoritative — so a stale
digest is flagged, never deleted (SPEC §6.5).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from engram.core.fs import write_atomic
from engram.kb.format import (
    CompileState,
    KbFormatError,
    KbFrontmatter,
    parse_compile_state,
    parse_readme,
    render_compile_state,
    render_readme,
)
from engram.kb.paths import (
    KB_COMPILE_STATE_NAME,
    KB_COMPILED_NAME,
    KB_README_NAME,
)

__all__ = [
    "CompileResult",
    "StalenessReport",
    "chapter_hashes",
    "check_staleness",
    "compile_article",
]

MAX_CHAPTER_BYTES = 4 * 1024 * 1024

# A chapter/source entry from README `chapters:` or `_compile_state.toml`
# `files` is attacker-influenceable on a shared/pulled KB dir. It MUST be
# a plain basename inside the article dir — never absolute, never `..`,
# never a path separator (SPEC §6.1/§6.4 forbid escapes). Otherwise
# ``topic_dir / fname`` would read/hash an out-of-article file.
_SAFE_MEMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _is_safe_member(fname: str) -> bool:
    return (
        isinstance(fname, str)
        and bool(_SAFE_MEMBER_RE.match(fname))
        and Path(fname).name == fname
        and ".." not in fname
    )


@dataclass(frozen=True, slots=True)
class CompileResult:
    topic_dir: Path
    compiled_path: Path
    source_files: tuple[str, ...]
    sections: int


@dataclass(frozen=True, slots=True)
class StalenessReport:
    is_stale: bool
    changed_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    detected_at: str | None


def _read_capped(path: Path, *, cap: int = MAX_CHAPTER_BYTES) -> str:
    with open(path, "rb") as fh:
        raw = fh.read(cap + 1)
    if len(raw) > cap:
        raise KbFormatError(f"{path} exceeds {cap}-byte cap")
    return raw.decode("utf-8", errors="replace")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


def chapter_hashes(topic_dir: Path, files: tuple[str, ...]) -> dict[str, str]:
    """Return ``{filename: sha256}`` for each safe source file that exists."""
    out: dict[str, str] = {}
    for fname in files:
        if not _is_safe_member(fname):
            continue
        p = topic_dir / fname
        if p.is_file() and not p.is_symlink():
            out[fname] = _sha256(p)
    return out


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return text
    after = rest[end + len("\n---") :]
    return after.lstrip("\n")


def _summarize_chapter(text: str) -> tuple[str, list[str]]:
    """Return (lead paragraph, headings) from a chapter body."""
    body = _strip_frontmatter(text)
    headings: list[str] = []
    lead: list[str] = []
    in_lead = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped.lstrip("#").strip())
            continue
        if not stripped:
            if in_lead:
                break
            continue
        # First non-heading text block becomes the lead paragraph.
        in_lead = True
        lead.append(stripped)
        if len(" ".join(lead)) > 400:
            break
    return " ".join(lead), headings


def _chapter_title(fm_title: str | None, headings: list[str], fname: str) -> str:
    if fm_title:
        return fm_title
    if headings:
        return headings[0]
    return fname.rsplit(".", 1)[0]


def compile_article(topic_dir: Path, *, now: datetime | None = None) -> CompileResult:
    """Regenerate ``_compiled.md`` + ``_compile_state.toml`` (rule-based).

    Raises :class:`KbFormatError` if README.md is missing/invalid or no
    chapter file resolves.
    """
    readme = topic_dir / KB_README_NAME
    fm, _ = parse_readme(readme)
    if not fm.chapters:
        raise KbFormatError(f"{readme}: 'chapters' is empty; nothing to compile")

    stamp = (now or datetime.now(tz=timezone.utc)).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    source_files: list[str] = [KB_README_NAME, *fm.chapters]

    # Build digest body. Every chapter MUST get >=1 section heading.
    sections: list[str] = []
    missing: list[str] = []
    for fname in fm.chapters:
        if not _is_safe_member(fname):
            raise KbFormatError(
                f"chapter entry {fname!r} is not a safe in-article filename "
                "(no paths, '..', or absolute references allowed; SPEC §6.1/§6.4)"
            )
        ch_path = topic_dir / fname
        if not ch_path.is_file() or ch_path.is_symlink():
            missing.append(fname)
            sections.append(f"## {fname}\n\n_(chapter file missing)_\n")
            continue
        text = _read_capped(ch_path)
        lead, headings = _summarize_chapter(text)
        title = _chapter_title(None, headings, fname)
        block = [f"## {title}"]
        if lead:
            block.append("")
            block.append(lead)
        if len(headings) > 1:
            block.append("")
            block.append("Sections: " + ", ".join(headings[1:6]))
        block.append("")
        block.append(f"[Read the full chapter]({fname})")
        sections.append("\n".join(block) + "\n")

    present_files = [f for f in source_files if (topic_dir / f).is_file()]

    # Update README frontmatter (compiled_from + compiled_at) FIRST, so the
    # source hash recorded below reflects the README's final on-disk bytes.
    # Otherwise `compile --check` would flag README as changed immediately.
    _, body = parse_readme(readme)
    write_atomic(readme, render_readme(_with_compile_meta(fm, present_files, stamp), body))

    hashes = chapter_hashes(topic_dir, tuple(present_files))
    hash_summary = " ".join(
        f"sha256({f})={hashes.get(f, '').removeprefix('sha256:')[:12]}" for f in present_files
    )

    header = (
        "<!-- AUTO-GENERATED from chapters. DO NOT EDIT DIRECTLY. -->\n"
        "<!-- compile-tool: engram kb compile -->\n"
        f"<!-- compiled_at: {stamp} -->\n"
        f"<!-- compiled_from: {', '.join(present_files)} -->\n"
        f"<!-- source_hashes: {hash_summary} -->\n"
    )
    digest = header + f"\n# {fm.name} — compiled digest\n\n" + "\n".join(sections)
    write_atomic(topic_dir / KB_COMPILED_NAME, digest)

    state = CompileState(
        files=tuple(present_files),
        hashes=hashes,
        compiled_at=stamp,
        model="local/none",
    )
    write_atomic(topic_dir / KB_COMPILE_STATE_NAME, render_compile_state(state))

    return CompileResult(
        topic_dir=topic_dir,
        compiled_path=topic_dir / KB_COMPILED_NAME,
        source_files=tuple(present_files),
        sections=len(sections),
    )


def _with_compile_meta(
    fm: KbFrontmatter, compiled_from: list[str], compiled_at: str
) -> KbFrontmatter:
    from dataclasses import replace

    return replace(fm, compiled_from=tuple(compiled_from), compiled_at=compiled_at)


def check_staleness(topic_dir: Path, *, now: datetime | None = None) -> StalenessReport:
    """Compare current chapter hashes to ``_compile_state.toml`` (SPEC §6.5).

    On any mismatch, marks ``is_stale=true`` + records ``detected_at`` in
    the state file. The ``_compiled.md`` itself is never deleted.
    """
    state_path = topic_dir / KB_COMPILE_STATE_NAME
    if not state_path.is_file():
        return StalenessReport(
            is_stale=True,
            changed_files=(),
            missing_files=("_compile_state.toml",),
            detected_at=None,
        )
    state = parse_compile_state(state_path)
    changed: list[str] = []
    missing: list[str] = []
    for fname in state.files:
        # state.files comes from a possibly-planted _compile_state.toml;
        # an unsafe entry is treated as "missing" (drift), never joined+read.
        if not _is_safe_member(fname):
            missing.append(fname)
            continue
        p = topic_dir / fname
        if not p.is_file() or p.is_symlink():
            missing.append(fname)
            continue
        if _sha256(p) != state.hashes.get(fname):
            changed.append(fname)
    is_stale = bool(changed or missing)
    detected_at: str | None = state.detected_at
    if is_stale:
        detected_at = (now or datetime.now(tz=timezone.utc)).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        from dataclasses import replace

        write_atomic(
            state_path,
            render_compile_state(replace(state, is_stale=True, detected_at=detected_at)),
        )
    return StalenessReport(
        is_stale=is_stale,
        changed_files=tuple(changed),
        missing_files=tuple(missing),
        detected_at=detected_at,
    )
