"""Tier 2 — semantic distiller across sessions.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2.

Tier 2 reads multiple Session assets (Tier 1 output), spots stable
facts that recur or settle across sessions, and writes candidate
Memory assets to ``.memory/distilled/<name>.proposed.md``. **It never
writes into ``.memory/local/``** — promotion is gated by
:mod:`engram.commands.distill` (T-209) and requires a deliberate
``engram distill promote`` invocation.

Design notes:

- The distiller is **provider-pluggable** the same way Tier 1 is. A
  Tier 2 LLM (qwen2.5-32b / llama-3.3-70b / DeepSeek-V3) is recommended
  but the function still returns sensible output when the provider is
  the mechanical fallback: it deduplicates the union of every session's
  ``files_touched`` into a single candidate Memory titled "session-
  files". It is not as good as a real distillation, but it is honest
  and never hallucinates a fact that isn't present.

- The LLM prompt asks for a JSON array of candidates with strict keys:
  ``[{name, description, body, source_sessions}]``. We parse loosely:
  if the response is wrapped in markdown fences, we strip; if a
  candidate is missing a required key, it is skipped, not raised.

- Each candidate becomes one ``.proposed.md`` file with Memory
  frontmatter (``type: agent``, ``scope: project``, ``enforcement:
  hint``, zero confidence). The ``source_sessions`` field records
  which sessions contributed; promotion can write a back-link.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from engram.core.fs import write_atomic
from engram.observer.providers import (
    MECHANICAL_MARKER,
    Provider,
    ProviderError,
    mechanical_provider,
)
from engram.observer.session import (
    parse_session_file,
)

__all__ = [
    "DEFAULT_DISTILL_PROMPT",
    "DEFAULT_TIER2_MIN_SESSIONS",
    "DistillResult",
    "DistilledCandidate",
    "build_distill_prompt",
    "distill_sessions",
    "distilled_dir",
    "load_session_for_distill",
    "render_proposed_file",
    "run_tier2",
    "select_sessions_for_distill",
    "slugify_topic",
]


DEFAULT_TIER2_MIN_SESSIONS = 5


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def distilled_dir(*, memory_dir: Path) -> Path:
    """``<memory_dir>/distilled/`` — staging area for candidate Memory."""
    return memory_dir / "distilled"


_SLUG_BAD = re.compile(r"[^a-z0-9]+")


def slugify_topic(name: str) -> str:
    """Make ``name`` safe for use as the file stem.

    Collapses runs of non-alphanumeric characters to ``-``, lowercases,
    and trims to 96 chars. Collisions are caller's problem (Tier 2 names
    its candidates with deterministic prefixes so collisions only
    happen on intentional re-runs).
    """
    s = _SLUG_BAD.sub("-", name.lower()).strip("-")
    if not s:
        s = "untitled"
    return s[:96]


# ----------------------------------------------------------------------
# Session selection
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SessionForDistill:
    """A Session asset preview the distiller can consume.

    Carries just enough context for prompt construction without
    forcing the distiller to re-parse every session file.
    """

    session_id: str
    task_hash: str | None
    files_touched: tuple[str, ...]
    outcome: str
    body: str


def load_session_for_distill(path: Path) -> SessionForDistill | None:
    """Parse a Session asset file into a distillation-friendly view.

    Returns None for unparseable files; the caller iterates and skips.
    """
    try:
        fm, body = parse_session_file(path)
    except Exception:
        return None
    return SessionForDistill(
        session_id=fm.session_id,
        task_hash=fm.task_hash,
        files_touched=fm.files_touched,
        outcome=fm.outcome,
        body=body,
    )


def select_sessions_for_distill(
    sessions: Sequence[SessionForDistill],
    *,
    min_sessions: int = DEFAULT_TIER2_MIN_SESSIONS,
) -> tuple[SessionForDistill, ...]:
    """Return a copy of ``sessions`` if ``len >= min_sessions`` else empty."""
    if len(sessions) < min_sessions:
        return ()
    return tuple(sessions)


# ----------------------------------------------------------------------
# Prompt + LLM call
# ----------------------------------------------------------------------


DEFAULT_DISTILL_PROMPT = """\
You are distilling stable, project-level facts from multiple LLM
coding sessions. The narratives below are mechanically extracted from
tool-use traces; treat them as the only ground truth.

Output exactly one JSON array. Each element MUST be an object with
keys: name, description, body, source_sessions. NO prose outside the
array, NO code fences, NO comments.

- name: kebab-case slug, <=64 chars. e.g. "auth-middleware-uses-jwt".
- description: one short sentence, <=160 chars, third person.
- body: 3-8 short bullet lines (Markdown). Each bullet must be a
  specific, verifiable claim referencing a file path in backticks or
  a tool name. NEVER invent file paths that do not appear in the
  sessions. NEVER write buzzwords (synergy / leverage / 闭环 / 赋能).
- source_sessions: array of session ids that supported this claim.

Constraints:
- Skip facts that only appear in one session — distill what is stable.
- If nothing recurs, return [] — an honest empty answer is correct.
- Maximum 6 candidates per call.
"""


def build_distill_prompt(
    sessions: Sequence[SessionForDistill],
    *,
    header: str = DEFAULT_DISTILL_PROMPT,
) -> str:
    """Render the full prompt: header + each session's body block."""
    parts: list[str] = [header, "## Sessions"]
    for s in sessions:
        parts.append(f"\n### {s.session_id} (outcome={s.outcome})")
        if s.files_touched:
            parts.append(
                "Files touched: " + ", ".join(f"`{f}`" for f in s.files_touched)
            )
        if s.task_hash:
            parts.append(f"task_hash: {s.task_hash}")
        parts.append("")
        parts.append(s.body.strip())
    return "\n".join(parts) + "\n"


# ----------------------------------------------------------------------
# Candidate parsing
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DistilledCandidate:
    """One distilled candidate Memory, ready to write to disk."""

    name: str
    description: str
    body: str
    source_sessions: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return f"{slugify_topic(self.name)}.proposed.md"


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers if the model added them."""
    s = text.strip()
    if s.startswith("```"):
        # ``` or ```json
        first_nl = s.find("\n")
        if first_nl > 0:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -len("```")]
    return s.strip()


def _parse_candidates_json(text: str) -> list[DistilledCandidate]:
    """Loose JSON parse of the model's array.

    Skips malformed entries rather than raising; the goal is honest
    output, not strict round-trip. Empty inputs / invalid JSON yield
    an empty list.
    """
    s = _strip_markdown_fences(text)
    if not s:
        return []
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    out: list[DistilledCandidate] = []
    seen_names: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        description = item.get("description")
        body = item.get("body")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(description, str) or not description:
            continue
        if not isinstance(body, str) or not body.strip():
            continue
        slug = slugify_topic(name)
        if slug in seen_names:
            continue
        seen_names.add(slug)

        source_sessions_raw = item.get("source_sessions", [])
        if isinstance(source_sessions_raw, list):
            source_sessions = tuple(
                s for s in source_sessions_raw if isinstance(s, str) and s
            )
        else:
            source_sessions = ()

        out.append(
            DistilledCandidate(
                name=slug,
                description=description.strip(),
                body=body.strip() + ("\n" if not body.endswith("\n") else ""),
                source_sessions=source_sessions,
            )
        )
        if len(out) >= 6:
            break
    return out


# ----------------------------------------------------------------------
# Mechanical fallback
# ----------------------------------------------------------------------


def _mechanical_candidates(
    sessions: Sequence[SessionForDistill],
) -> list[DistilledCandidate]:
    """No-LLM distillation: union files touched across >=2 sessions.

    Honest baseline. Picks files that appear in at least two sessions
    so single-session noise does not enter Memory. Returns at most one
    candidate so a Tier 2 with no LLM never floods ``distilled/``.
    """
    from collections import Counter

    counter: Counter[str] = Counter()
    sessions_by_file: dict[str, set[str]] = {}
    for s in sessions:
        for f in s.files_touched:
            counter[f] += 1
            sessions_by_file.setdefault(f, set()).add(s.session_id)
    repeating = [f for f, c in counter.items() if c >= 2]
    if not repeating:
        return []
    repeating.sort(key=lambda f: (-counter[f], f))
    bullets = [
        f"- `{f}` touched in {counter[f]} sessions"
        for f in repeating[:8]
    ]
    body = (
        "Files this project keeps coming back to. Mechanically "
        "extracted across recent sessions; promote with consent if "
        "still relevant.\n\n" + "\n".join(bullets) + "\n"
    )
    contributing_sessions = sorted(
        {sid for f in repeating[:8] for sid in sessions_by_file[f]}
    )
    return [
        DistilledCandidate(
            name="recurring-files",
            description="Files touched across multiple recent sessions.",
            body=body,
            source_sessions=tuple(contributing_sessions),
        )
    ]


# ----------------------------------------------------------------------
# Distillation entrypoint
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class DistillResult:
    """Outcome of one Tier 2 distillation pass."""

    candidates: tuple[DistilledCandidate, ...]
    used_mechanical_fallback: bool
    written_paths: tuple[Path, ...] = ()


def render_proposed_file(
    candidate: DistilledCandidate,
    *,
    today: date,
) -> str:
    """Render a candidate as Memory frontmatter + body for the proposed file.

    Memory schema (SPEC §4.1): type=agent (LLM-inferred), scope=project,
    enforcement=hint (lowest, since unverified). The proposed marker is
    the directory location (``distilled/``) — we deliberately do NOT
    add a custom ``proposed: true`` field so the file becomes a valid
    Memory the moment it moves into ``local/``.
    """
    fm = {
        "name": candidate.name,
        "description": candidate.description,
        "type": "agent",
        "scope": "project",
        "enforcement": "hint",
        "created": today.isoformat(),
        "updated": today.isoformat(),
        "source_sessions": list(candidate.source_sessions),
    }
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    body = candidate.body if candidate.body.endswith("\n") else candidate.body + "\n"
    return f"---\n{yaml_text}---\n{body}"


def distill_sessions(
    sessions: Sequence[SessionForDistill],
    *,
    memory_dir: Path,
    provider: Provider | None = None,
    today: date | None = None,
    min_sessions: int = DEFAULT_TIER2_MIN_SESSIONS,
) -> DistillResult:
    """Run one distillation pass and write candidates to ``distilled/``.

    Returns a :class:`DistillResult` with the parsed candidates + the
    paths written. Skipped (count below threshold) → empty result.

    The function is **idempotent**: re-running over the same sessions
    overwrites the candidate files at the same path. Operators who
    want to keep history should ``engram distill reject`` (archives
    the proposed file with a timestamp).
    """
    selected = select_sessions_for_distill(sessions, min_sessions=min_sessions)
    if not selected:
        return DistillResult(candidates=(), used_mechanical_fallback=False)

    chosen_provider: Provider = provider if provider is not None else mechanical_provider
    today_d = today or date.today()
    used_mechanical = False

    prompt = build_distill_prompt(selected)
    candidates: list[DistilledCandidate] = []
    try:
        response = chosen_provider(prompt)
    except ProviderError:
        used_mechanical = True
        response = MECHANICAL_MARKER

    if response == MECHANICAL_MARKER:
        candidates = _mechanical_candidates(selected)
        used_mechanical = True
    else:
        candidates = _parse_candidates_json(response)
        if not candidates:
            # Empty / invalid JSON — fall back rather than write nothing.
            candidates = _mechanical_candidates(selected)
            used_mechanical = True

    if not candidates:
        return DistillResult(
            candidates=(),
            used_mechanical_fallback=used_mechanical,
        )

    out_dir = distilled_dir(memory_dir=memory_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for c in candidates:
        path = out_dir / c.filename
        write_atomic(path, render_proposed_file(c, today=today_d))
        written_paths.append(path)

    return DistillResult(
        candidates=tuple(candidates),
        used_mechanical_fallback=used_mechanical,
        written_paths=tuple(written_paths),
    )


# ----------------------------------------------------------------------
# Daemon-facing entry
# ----------------------------------------------------------------------


def run_tier2(
    *,
    sessions_paths: Sequence[Path],
    memory_dir: Path,
    provider: Provider | None = None,
    min_sessions: int = DEFAULT_TIER2_MIN_SESSIONS,
) -> DistillResult:
    """Read sessions from disk, distill, write proposed files."""
    sessions: list[SessionForDistill] = []
    for path in sessions_paths:
        sfd = load_session_for_distill(path)
        if sfd is not None:
            sessions.append(sfd)
    return distill_sessions(
        sessions,
        memory_dir=memory_dir,
        provider=provider,
        min_sessions=min_sessions,
    )
