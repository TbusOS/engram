"""Tier 1 — local episodic compactor.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2.

Tier 1 turns a per-session ``timeline.jsonl`` (Tier 0 output) into a
narrative session asset. The compactor is **provider-pluggable**:

- LLM provider configured -> run an LLM call producing a 150-300 token
  Markdown narrative anchored to timeline facts.
- No provider / LLM error / timeout → fall back to the Tier 0
  mechanical narrative (deterministic bulleted summary).

Either way, the output is a valid Session asset with frontmatter +
body, written to ``.memory/sessions/<YYYY-MM-DD>/sess_<id>.md`` (or
``~/.engram/sessions/...`` for cross-project use when the queue did
not declare a project root).

This module never imports a client SDK. The only network surface is
through :mod:`engram.observer.providers`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram.core.fs import write_atomic
from engram.core.paths import user_root
from engram.observer.providers import (
    MECHANICAL_MARKER,
    Provider,
    ProviderError,
    mechanical_provider,
)
from engram.observer.session import (
    SessionConfidence,
    SessionFrontmatter,
    render_session_file,
    session_path,
    sessions_root,
)
from engram.observer.tier0 import render_narrative_from_timeline

__all__ = [
    "DEFAULT_PROMPT_HEADER",
    "Tier1Result",
    "build_prompt",
    "compact_to_narrative",
    "compact_to_session_asset",
    "summarize_timeline",
]


# ----------------------------------------------------------------------
# Prompt construction
# ----------------------------------------------------------------------


DEFAULT_PROMPT_HEADER = """\
You are summarising one work session of an LLM coding agent. The facts
below are MECHANICALLY EXTRACTED from the agent's tool-use trace —
treat them as the only ground truth. DO NOT invent files, decisions,
or outcomes that are not in the facts. If a section has no facts,
write "(none)" rather than padding.

Output exactly four Markdown sections, in this order, with these exact
headings: ## Investigated, ## Learned, ## Completed, ## Next steps.

Each section should be 1-4 short bullet points, total length 150-300
tokens. Reference file paths in backticks (e.g. `src/foo.ts`). Use
plain prose, no buzzwords.
"""


@dataclass(frozen=True)
class TimelineSummary:
    """Aggregated facts from a single ``timeline.jsonl``."""

    tool_calls: int
    user_prompts: int
    tool_counts: dict[str, int]
    files_touched: list[str]
    files_modified: list[str]
    errors: list[str]
    outcome: str
    started_at: datetime | None
    ended_at: datetime | None
    raw_lines: int


def summarize_timeline(timeline_path: Path) -> TimelineSummary:
    """Parse a timeline.jsonl into a structured summary.

    The summary feeds both the LLM prompt and the SessionFrontmatter
    fields that get written to the asset file.
    """
    tool_calls = 0
    user_prompts = 0
    tool_counts: dict[str, int] = {}
    files_touched: set[str] = set()
    files_modified: set[str] = set()
    errors: list[str] = []
    outcome = "unknown"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    raw_lines = 0

    if not timeline_path.exists():
        return TimelineSummary(
            tool_calls=0,
            user_prompts=0,
            tool_counts={},
            files_touched=[],
            files_modified=[],
            errors=[],
            outcome="unknown",
            started_at=None,
            ended_at=None,
            raw_lines=0,
        )

    with open(timeline_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw_lines += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            t_str = rec.get("t")
            t_dt = _parse_iso(t_str) if isinstance(t_str, str) else None
            if t_dt is not None:
                if started_at is None or t_dt < started_at:
                    started_at = t_dt
                if ended_at is None or t_dt > ended_at:
                    ended_at = t_dt

            kind = rec.get("kind")
            if kind == "tool_use":
                tool_calls += 1
                tool = rec.get("tool")
                if isinstance(tool, str):
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1
                _absorb_files(rec, "files", files_touched)
                _absorb_files(rec, "files_modified", files_modified)
                files_touched.update(files_modified)
            elif kind == "user_prompt":
                user_prompts += 1
            elif kind == "error":
                first = rec.get("stderr_first_line")
                if isinstance(first, str):
                    errors.append(first)
            elif kind == "session_end":
                out = rec.get("outcome")
                if isinstance(out, str):
                    outcome = out

    return TimelineSummary(
        tool_calls=tool_calls,
        user_prompts=user_prompts,
        tool_counts=dict(tool_counts),
        files_touched=sorted(files_touched),
        files_modified=sorted(files_modified),
        errors=errors,
        outcome=outcome,
        started_at=started_at,
        ended_at=ended_at,
        raw_lines=raw_lines,
    )


def _absorb_files(rec: dict[str, Any], key: str, dest: set[str]) -> None:
    val = rec.get(key)
    if isinstance(val, list):
        for f in val:
            if isinstance(f, str):
                dest.add(f)


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_prompt(summary: TimelineSummary, *, header: str = DEFAULT_PROMPT_HEADER) -> str:
    """Render a self-contained prompt: header + structured facts."""
    facts: list[str] = []
    facts.append(f"Tool calls: {summary.tool_calls}")
    facts.append(f"User prompts: {summary.user_prompts}")
    if summary.tool_counts:
        items = ", ".join(
            f"{tool}: {count}"
            for tool, count in sorted(summary.tool_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        facts.append(f"Tools used: {items}")
    if summary.files_touched:
        facts.append("Files touched: " + ", ".join(f"`{f}`" for f in summary.files_touched))
    if summary.files_modified:
        facts.append(
            "Files modified: " + ", ".join(f"`{f}`" for f in summary.files_modified)
        )
    if summary.errors:
        facts.append("Errors recorded:")
        for e in summary.errors[:5]:
            facts.append(f"  - {e}")
    facts.append(f"Outcome: {summary.outcome}")
    return header + "\n## Facts\n\n" + "\n".join(facts) + "\n"


# ----------------------------------------------------------------------
# Compaction entry points
# ----------------------------------------------------------------------


def compact_to_narrative(
    timeline_path: Path,
    *,
    provider: Provider | None = None,
) -> str:
    """Return a narrative Markdown body for the given timeline.

    On any provider failure, falls back to mechanical narrative — the
    floor of the pipeline (spec §11.6).
    """
    summary = summarize_timeline(timeline_path)
    chosen_provider: Provider = provider if provider is not None else mechanical_provider

    prompt = build_prompt(summary)
    try:
        response = chosen_provider(prompt)
    except ProviderError:
        return render_narrative_from_timeline(timeline_path)

    if response == MECHANICAL_MARKER:
        return render_narrative_from_timeline(timeline_path)

    text = response.strip()
    if not text:
        return render_narrative_from_timeline(timeline_path)
    return text + ("\n" if not text.endswith("\n") else "")


@dataclass(frozen=True)
class Tier1Result:
    """Outcome of a single Tier 1 compaction pass."""

    session_id: str
    asset_path: Path
    used_mechanical_fallback: bool
    summary: TimelineSummary


def compact_to_session_asset(
    session_id: str,
    *,
    timeline_path: Path,
    client: str,
    project_root: Path | None = None,
    provider: Provider | None = None,
    started_at: datetime | None = None,
    task_hash: str | None = None,
) -> Tier1Result:
    """End-to-end Tier 1: timeline → narrative → Session asset on disk.

    ``project_root`` selects the destination:

    - ``None`` → ``~/.engram/sessions/<date>/sess_<id>.md`` (cross-project).
    - given → ``<project_root>/.memory/sessions/<date>/sess_<id>.md``.

    The function is idempotent: re-running over the same timeline
    overwrites the asset (atomic via :func:`engram.core.fs.write_atomic`).
    """
    summary = summarize_timeline(timeline_path)

    chosen_provider: Provider = provider if provider is not None else mechanical_provider
    prompt = build_prompt(summary)
    used_mechanical = False

    try:
        response = chosen_provider(prompt)
    except ProviderError:
        body = render_narrative_from_timeline(timeline_path)
        used_mechanical = True
    else:
        if response == MECHANICAL_MARKER:
            body = render_narrative_from_timeline(timeline_path)
            used_mechanical = True
        else:
            text = response.strip()
            if text:
                body = text + ("\n" if not text.endswith("\n") else "")
            else:
                body = render_narrative_from_timeline(timeline_path)
                used_mechanical = True

    started = started_at or summary.started_at or datetime.now(tz=timezone.utc)
    ended = summary.ended_at

    fm = SessionFrontmatter(
        type="session",
        session_id=session_id,
        client=client,
        started_at=started,
        ended_at=ended,
        task_hash=task_hash,
        tool_calls=summary.tool_calls,
        files_touched=tuple(summary.files_touched),
        files_modified=tuple(summary.files_modified),
        outcome=_normalise_outcome(summary.outcome),
        error_summary=summary.errors[0] if summary.errors else None,
        confidence=SessionConfidence(),
    )

    if project_root is not None:
        asset_path = session_path(
            session_id, started_at=started, memory_dir=project_root / ".memory"
        )
    else:
        asset_path = session_path(
            session_id, started_at=started, memory_dir=user_root()
        )

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(asset_path, render_session_file(fm, body))

    return Tier1Result(
        session_id=session_id,
        asset_path=asset_path,
        used_mechanical_fallback=used_mechanical,
        summary=summary,
    )


def _normalise_outcome(value: str) -> str:
    if value in {"completed", "abandoned", "error", "unknown"}:
        return value
    return "unknown"


def session_destination_dir(
    *,
    project_root: Path | None,
) -> Path:
    """Where this Tier 1 will write session assets.

    Exposed for ``engram observer status`` / tests; equivalent to the
    branch inside :func:`compact_to_session_asset`.
    """
    if project_root is not None:
        return sessions_root(project_root / ".memory")
    return sessions_root(user_root())


def all_session_files(*, project_root: Path | None = None) -> Iterable[Path]:
    """Iterate over every session asset under the chosen destination."""
    root = session_destination_dir(project_root=project_root)
    if not root.is_dir():
        return iter(())
    return (p for p in root.rglob("sess_*.md") if p.is_file())
