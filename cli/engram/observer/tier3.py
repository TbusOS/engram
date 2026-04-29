"""Tier 3 — procedural recognizer across sessions.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2.

Tier 3 reads a *long* horizon of Session assets (weeks, not days),
detects **recurring problem-solution patterns**, and writes candidate
Workflow assets to ``.memory/workflows/<name>/proposal.md``. It runs
on a slower cadence than Tier 2 (default: weekly cron, or manual via
``engram propose run``) because workflows are higher-leverage commits
than Memories — the bar for "this is a procedure worth codifying" is
higher.

The module is intentionally close in shape to Tier 2 (T-208):

- Provider-pluggable. Top-of-the-line model recommended; mechanical
  fallback never invents procedures.
- LLM prompt asks for strict JSON: ``[{name, when_to_use,
  steps[], source_sessions}]``. Parser tolerates fences, missing
  fields are skipped, dedupe by slug.
- Mechanical fallback: when no LLM is configured, group sessions by
  ``task_hash`` and only emit a candidate when ``>=3`` sessions share
  the same task hash AND ``>=2`` reached ``outcome=completed``. This
  is the honest minimum: if a problem keeps coming up *and* gets
  solved, it deserves a workflow proposal.
- Output: a Workflow directory with a ``proposal.md`` containing the
  procedure draft. ``engram propose promote <name>`` (T-210 CLI)
  activates it; until then the directory is invisible to spine
  execution.

Workflows are the most consequential asset class — they have
executable spines, fixtures, metrics. We deliberately keep Tier 3
low-recall: better to miss a workflow than to flood ``workflows/``
with low-quality drafts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
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
from engram.observer.tier2 import (
    SessionForDistill,
    load_session_for_distill,
    slugify_topic,
)

__all__ = [
    "DEFAULT_PROCEDURE_PROMPT",
    "DEFAULT_TIER3_MIN_TASK_RECURRENCES",
    "DEFAULT_TIER3_MIN_COMPLETED",
    "ProcedureProposal",
    "ProcedureResult",
    "build_procedure_prompt",
    "propose_procedures",
    "render_procedure_proposal",
    "run_tier3",
    "workflows_dir",
]


DEFAULT_TIER3_MIN_TASK_RECURRENCES = 3
DEFAULT_TIER3_MIN_COMPLETED = 2


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def workflows_dir(*, memory_dir: Path) -> Path:
    """``<memory_dir>/workflows/`` — Workflow asset root."""
    return memory_dir / "workflows"


# ----------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------


DEFAULT_PROCEDURE_PROMPT = """\
You are recognising recurring problem-solution patterns from many LLM
coding sessions and proposing them as engram Workflow assets.

Output exactly one JSON array. Each element MUST be an object with:
- name: kebab-case slug, <=64 chars (e.g. "debug-grpc-timeout").
- when_to_use: 1-2 sentences describing the trigger conditions.
- steps: array of 3-10 short imperative bullets, each <=120 chars.
- source_sessions: array of session ids that contributed.

Constraints:
- Only propose a procedure when the same problem appears >=3 times
  AND the solution converged (>=2 sessions reached outcome=completed
  using a similar approach).
- NEVER invent file paths or commands not present in the sessions.
- NEVER write buzzwords (synergy / leverage / 闭环 / 赋能).
- If nothing qualifies, return [] — empty is correct.
- Maximum 4 candidates per call (workflows are high-leverage; recall
  is intentionally tight).

NO prose outside the JSON array. NO code fences.
"""


def build_procedure_prompt(
    sessions: Sequence[SessionForDistill],
    *,
    header: str = DEFAULT_PROCEDURE_PROMPT,
) -> str:
    """Render the prompt: header + per-session block (id, hash, body)."""
    parts: list[str] = [header, "## Sessions"]
    for s in sessions:
        parts.append(f"\n### {s.session_id} (outcome={s.outcome})")
        if s.task_hash:
            parts.append(f"task_hash: {s.task_hash}")
        if s.files_touched:
            parts.append(
                "Files touched: " + ", ".join(f"`{f}`" for f in s.files_touched)
            )
        parts.append("")
        parts.append(s.body.strip())
    return "\n".join(parts) + "\n"


# ----------------------------------------------------------------------
# Candidate parsing
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ProcedureProposal:
    """One candidate procedure ready to be written to disk."""

    name: str
    when_to_use: str
    steps: tuple[str, ...]
    source_sessions: tuple[str, ...] = ()

    @property
    def directory_name(self) -> str:
        return slugify_topic(self.name)


def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl > 0:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -len("```")]
    return s.strip()


def _parse_proposals_json(text: str) -> list[ProcedureProposal]:
    s = _strip_fences(text)
    if not s:
        return []
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    out: list[ProcedureProposal] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        when = item.get("when_to_use")
        steps = item.get("steps")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(when, str) or not when.strip():
            continue
        if not isinstance(steps, list) or len(steps) < 3:
            continue
        clean_steps = tuple(
            s.strip() for s in steps if isinstance(s, str) and s.strip()
        )
        if len(clean_steps) < 3:
            continue
        slug = slugify_topic(name)
        if slug in seen:
            continue
        seen.add(slug)

        sources_raw = item.get("source_sessions", [])
        if isinstance(sources_raw, list):
            sources = tuple(s for s in sources_raw if isinstance(s, str) and s)
        else:
            sources = ()

        out.append(
            ProcedureProposal(
                name=slug,
                when_to_use=when.strip(),
                steps=clean_steps,
                source_sessions=sources,
            )
        )
        if len(out) >= 4:
            break
    return out


# ----------------------------------------------------------------------
# Mechanical fallback
# ----------------------------------------------------------------------


def _mechanical_proposals(
    sessions: Sequence[SessionForDistill],
    *,
    min_recurrences: int,
    min_completed: int,
) -> list[ProcedureProposal]:
    """Honest no-LLM proposal: group by task_hash, gate on recurrence + completion.

    Returns at most one proposal per qualifying task_hash. The body is
    a deterministic skeleton: "files touched (union)" as a starting
    point for the human / LLM that promotes it.
    """
    from collections import defaultdict

    by_task: dict[str, list[SessionForDistill]] = defaultdict(list)
    for s in sessions:
        if s.task_hash:
            by_task[s.task_hash].append(s)

    out: list[ProcedureProposal] = []
    for task_hash, group in by_task.items():
        if len(group) < min_recurrences:
            continue
        completed = [s for s in group if s.outcome == "completed"]
        if len(completed) < min_completed:
            continue
        files: set[str] = set()
        for s in completed:
            files.update(s.files_touched)
        steps_list: list[str] = []
        steps_list.append(
            f"Re-verify the symptom matches task {task_hash[:12]} "
            f"(seen {len(group)} times)."
        )
        if files:
            steps_list.append(
                "Inspect the files this task historically touches: "
                + ", ".join(f"`{f}`" for f in sorted(files)[:6])
            )
        steps_list.append(
            "Compare the most recent two completed sessions' approaches and "
            "fold what's common into a single procedure."
        )
        steps_list.append(
            "Promote this proposal to a real Workflow with `engram propose "
            "promote <name>` once the steps are confirmed."
        )
        slug = slugify_topic(f"task-{task_hash[:12]}")
        out.append(
            ProcedureProposal(
                name=slug,
                when_to_use=(
                    f"This task hash recurred {len(group)} times with "
                    f"{len(completed)} completions; replay the proven path."
                ),
                steps=tuple(steps_list),
                source_sessions=tuple(s.session_id for s in group),
            )
        )
        if len(out) >= 4:
            break
    return out


# ----------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------


def render_procedure_proposal(
    proposal: ProcedureProposal,
    *,
    today: date,
) -> str:
    """Render one ProcedureProposal as a Workflow proposal.md file.

    The file is plain Markdown with a YAML frontmatter block that
    matches the Workflow asset schema (SPEC §6) at the seed level.
    Fixtures, spine, metrics, and rev/ are NOT created here — those
    are part of ``engram propose promote`` (or a human authoring the
    workflow). The proposal is the seed.
    """
    fm = {
        "name": proposal.name,
        "type": "workflow_proposal",
        "scope": "project",
        "created": today.isoformat(),
        "updated": today.isoformat(),
        "source_sessions": list(proposal.source_sessions),
    }
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    body_lines = [
        "# " + proposal.name,
        "",
        "## When to use",
        "",
        proposal.when_to_use,
        "",
        "## Steps",
        "",
    ]
    for i, step in enumerate(proposal.steps, 1):
        body_lines.append(f"{i}. {step}")
    body_lines.append("")
    body_lines.append("## Source sessions")
    body_lines.append("")
    if proposal.source_sessions:
        for sid in proposal.source_sessions:
            body_lines.append(f"- `{sid}`")
    else:
        body_lines.append("- (none)")
    body_lines.append("")
    return f"---\n{yaml_text}---\n" + "\n".join(body_lines)


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ProcedureResult:
    """Outcome of a single Tier 3 pass."""

    proposals: tuple[ProcedureProposal, ...]
    used_mechanical_fallback: bool
    written_paths: tuple[Path, ...] = ()


def propose_procedures(
    sessions: Sequence[SessionForDistill],
    *,
    memory_dir: Path,
    provider: Provider | None = None,
    today: date | None = None,
    min_task_recurrences: int = DEFAULT_TIER3_MIN_TASK_RECURRENCES,
    min_completed: int = DEFAULT_TIER3_MIN_COMPLETED,
) -> ProcedureResult:
    """Produce candidate Workflow proposals, write to ``workflows/<slug>/proposal.md``.

    Rules:

    - LLM provider configured + returns valid JSON → use those proposals.
    - LLM provider absent / errors / empty → mechanical fallback grouped
      by task_hash with the recurrence + completion gates.
    - Either way the result is **idempotent**: re-running over the same
      sessions overwrites the same paths.
    """
    if not sessions:
        return ProcedureResult(proposals=(), used_mechanical_fallback=False)

    chosen: Provider = provider if provider is not None else mechanical_provider
    today_d = today or date.today()
    used_mechanical = False
    proposals: list[ProcedureProposal]

    prompt = build_procedure_prompt(sessions)
    try:
        response = chosen(prompt)
    except ProviderError:
        used_mechanical = True
        response = MECHANICAL_MARKER

    if response == MECHANICAL_MARKER:
        proposals = _mechanical_proposals(
            sessions,
            min_recurrences=min_task_recurrences,
            min_completed=min_completed,
        )
        used_mechanical = True
    else:
        proposals = _parse_proposals_json(response)
        if not proposals:
            proposals = _mechanical_proposals(
                sessions,
                min_recurrences=min_task_recurrences,
                min_completed=min_completed,
            )
            used_mechanical = True

    if not proposals:
        return ProcedureResult(
            proposals=(),
            used_mechanical_fallback=used_mechanical,
        )

    out_dir = workflows_dir(memory_dir=memory_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for p in proposals:
        wdir = out_dir / p.directory_name
        wdir.mkdir(parents=True, exist_ok=True)
        path = wdir / "proposal.md"
        write_atomic(path, render_procedure_proposal(p, today=today_d))
        written.append(path)

    return ProcedureResult(
        proposals=tuple(proposals),
        used_mechanical_fallback=used_mechanical,
        written_paths=tuple(written),
    )


def run_tier3(
    *,
    sessions_paths: Sequence[Path],
    memory_dir: Path,
    provider: Provider | None = None,
) -> ProcedureResult:
    """Read sessions from disk, run Tier 3 over them."""
    sessions: list[SessionForDistill] = []
    for path in sessions_paths:
        sfd = load_session_for_distill(path)
        if sfd is not None:
            sessions.append(sfd)
    return propose_procedures(
        sessions, memory_dir=memory_dir, provider=provider
    )
