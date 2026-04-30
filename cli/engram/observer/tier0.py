"""Tier 0 mechanical compactor — fact extraction with no LLM.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2.

Tier 0 is the floor of the observer pipeline:

- Runs on every queue tick.
- Never calls an LLM. Never opens a network socket.
- Treats the queue jsonl as the source of truth and produces a
  derived ``timeline.jsonl`` with extracted facts: tool name, file
  paths, errors, timestamps, token counts.
- Cannot fail: malformed lines are skipped with a ``parse_error``
  marker, never stop the pipeline.

Tier 1 / 2 / 3 are not allowed to bypass Tier 0 — every line a higher
tier reads must already exist in the timeline. This is the
RAG-over-own-trace anchor: LLM hallucinations cannot survive because
narratives reference timeline facts.

Output schema (one canonical line per input event)::

    {"t": "...", "kind": "tool_use", "tool": "Read",
     "files": ["src/foo.ts"], "tokens_in": 120, "tokens_out": 340}

Fields trimmed from the queue line (stderr, prompt body) never appear
in the timeline — only their hashes / first-line summaries.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engram.observer.daemon import PendingSession
from engram.observer.paths import validate_session_id

__all__ = [
    "FactRecord",
    "Tier0Result",
    "compact_session",
    "extract_facts",
    "iter_queue_lines",
    "render_narrative_from_timeline",
    "run_tier0",
    "session_timeline_path",
]


# ----------------------------------------------------------------------
# Output paths
# ----------------------------------------------------------------------


def session_timeline_path(session_id: str, *, sessions_dir: Path) -> Path:
    """Path to ``<sessions_dir>/<id>.timeline.jsonl``.

    ``sessions_dir`` is ``.memory/sessions/<YYYY-MM-DD>/`` for production
    use, or any directory in tests. Tier 0 never decides the date
    bucket itself — that's a Tier 1 / Session-asset concern.
    """
    sid = validate_session_id(session_id)
    return sessions_dir / f"{sid}.timeline.jsonl"


# ----------------------------------------------------------------------
# Fact extraction
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class FactRecord:
    """One fact line in the timeline.

    Mirrors the queue event shape but with all dropped / truncated
    fields removed and a couple of derived counters added (tool /
    files counts get aggregated by the Session writer, not here).
    """

    t: str
    kind: str
    payload: dict[str, Any]

    def to_line(self) -> str:
        line = {"t": self.t, "kind": self.kind}
        line.update(self.payload)
        return json.dumps(line, ensure_ascii=False, separators=(",", ":"))


# Fields we keep verbatim from queue lines into timeline.
_KEPT_FIELDS = (
    "tool",
    "client",
    "session_id",
    "files",
    "files_modified",
    "tokens_in",
    "tokens_out",
    "exit_code",
    "stderr_first_line",
    "diff_lines_added",
    "diff_lines_removed",
    "outcome",
    "prompt_chars",
    "prompt_hash",
    "args_hash",
    "result_chars",
    "truncated",
)


def extract_facts(queue_line: dict[str, Any]) -> FactRecord | None:
    """Pull a single fact record from a parsed queue line.

    Returns ``None`` for unrecognised lines (kind missing or unknown).
    Tier 0 is permissive on payload keys — anything in ``_KEPT_FIELDS``
    survives — so the schema can grow without re-issuing this module.
    """
    kind = queue_line.get("kind")
    t = queue_line.get("t")
    if not isinstance(kind, str) or not isinstance(t, str):
        return None
    payload: dict[str, Any] = {}
    for key in _KEPT_FIELDS:
        if key in queue_line:
            payload[key] = queue_line[key]
    return FactRecord(t=t, kind=kind, payload=payload)


def iter_queue_lines(queue_path: Path) -> Iterator[dict[str, Any] | None]:
    """Yield parsed queue lines; ``None`` for lines that fail to parse."""
    if not queue_path.exists():
        return iter(())

    def _gen() -> Iterator[dict[str, Any] | None]:
        with open(queue_path, encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield None
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return _gen()


# ----------------------------------------------------------------------
# Compaction
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Tier0Result:
    """Stats from one compaction pass over a session queue."""

    session_id: str
    facts_written: int
    parse_errors: int
    timeline_path: Path


def compact_session(
    session_id: str,
    *,
    queue_path: Path,
    sessions_dir: Path,
) -> Tier0Result:
    """Read every line in ``queue_path`` and append derived facts.

    Idempotency: Tier 0 only **appends**. Re-running it on the same
    queue produces duplicate timeline lines. Higher tiers are expected
    to consume + truncate the queue file once they're done, which makes
    the next Tier 0 run a no-op.
    """
    sid = validate_session_id(session_id)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = session_timeline_path(sid, sessions_dir=sessions_dir)

    written = 0
    parse_errors = 0
    # Single-write contract (code reviewer C4, 2026-04-30): each line
    # MUST be one ``out.write(...)`` call so a SIGKILL between the
    # payload and the trailing newline is impossible. POSIX guarantees
    # atomicity for writes < PIPE_BUF (>= 512 bytes); events are capped
    # at 4 KB by ``protocol.MAX_EVENT_BYTES``.
    with open(timeline_path, "a", encoding="utf-8") as out:
        fcntl.flock(out.fileno(), fcntl.LOCK_EX)
        try:
            for parsed in iter_queue_lines(queue_path):
                if parsed is None:
                    parse_errors += 1
                    out.write(
                        json.dumps(
                            {"t": "0", "kind": "parse_error"},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    continue
                fact = extract_facts(parsed)
                if fact is None:
                    parse_errors += 1
                    continue
                out.write(fact.to_line() + "\n")
                written += 1
            out.flush()
        finally:
            fcntl.flock(out.fileno(), fcntl.LOCK_UN)

    return Tier0Result(
        session_id=sid,
        facts_written=written,
        parse_errors=parse_errors,
        timeline_path=timeline_path,
    )


def run_tier0(pending: PendingSession, *, sessions_dir: Path) -> Tier0Result:
    """Daemon-facing entry point — compatible with ObserverDaemon.tier0_runner."""
    return compact_session(
        pending.session_id,
        queue_path=pending.queue_path,
        sessions_dir=sessions_dir,
    )


# ----------------------------------------------------------------------
# Mechanical narrative (Tier 1 fallback when no LLM is configured)
# ----------------------------------------------------------------------


def render_narrative_from_timeline(timeline_path: Path) -> str:
    """Render a deterministic, LLM-free Markdown narrative.

    This is the fallback that lets engram run fully offline: when no
    LLM is configured for Tier 1, the timeline is converted into a
    bulleted Markdown summary with the same structure (Investigated /
    Learned / Completed / Next) the LLM compactor produces, but with
    purely mechanical content.
    """
    if not timeline_path.exists():
        return _empty_narrative_template()

    tools_used: dict[str, int] = {}
    files_touched: set[str] = set()
    errors: list[str] = []
    outcome: str | None = None
    user_prompts = 0
    tool_calls = 0

    with open(timeline_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = rec.get("kind")
            if kind == "tool_use":
                tool_calls += 1
                tool = rec.get("tool")
                if isinstance(tool, str):
                    tools_used[tool] = tools_used.get(tool, 0) + 1
                for fld in ("files", "files_modified"):
                    val = rec.get(fld)
                    if isinstance(val, list):
                        for f_path in val:
                            if isinstance(f_path, str):
                                files_touched.add(f_path)
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

    lines: list[str] = []
    lines.append("# Narrative (mechanical)")
    lines.append("")
    lines.append("## Investigated")
    if tool_calls == 0:
        lines.append("- (no tool calls recorded)")
    else:
        lines.append(f"- {tool_calls} tool calls; {user_prompts} user prompts.")
        for tool, count in sorted(tools_used.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{tool}`: {count} call(s)")
    lines.append("")
    lines.append("## Learned")
    if not files_touched:
        lines.append("- (no files touched)")
    else:
        for fp in sorted(files_touched):
            lines.append(f"- touched `{fp}`")
    lines.append("")
    lines.append("## Completed")
    if outcome:
        lines.append(f"- outcome: {outcome}")
    elif errors:
        lines.append(f"- {len(errors)} error(s) recorded")
    else:
        lines.append("- (outcome unknown)")
    lines.append("")
    lines.append("## Next steps")
    if errors:
        lines.append(f"- resolve: `{errors[0]}`")
    else:
        lines.append("- (no follow-ups inferred mechanically)")
    lines.append("")
    return "\n".join(lines)


def _empty_narrative_template() -> str:
    return (
        "# Narrative (mechanical)\n\n"
        "## Investigated\n- (no events)\n\n"
        "## Learned\n- (no events)\n\n"
        "## Completed\n- (no events)\n\n"
        "## Next steps\n- (no events)\n"
    )
