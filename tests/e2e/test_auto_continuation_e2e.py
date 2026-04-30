"""T-212 E2E — Auto-Continuation pipeline across 5 sessions.

Mimics one engineer chasing the same bug across:

  s1  claude-code   first investigation, reads source files
  s2  codex         tries a fix, fails (outcome=abandoned)
  s3  cursor        narrows down the cause
  s4  raw-api       offline ollama path (no provider configured)
  s5  claude-code   ships the fix (outcome=completed)

Verifies the full pipeline:

  - engram observe enqueues events from each client.
  - Tier 0 mechanical compactor lays down a per-session timeline.jsonl.
  - Tier 1 produces Session asset under .memory/sessions/<date>/.
  - Cross-session linkage (T-207) wires prev/next chain via task_hash.
  - Stage 0 (T-206) injects same-task-hash sessions into Relevance Gate.
  - Tier 2 (T-208) yields at least one distilled candidate.
  - engram distill promote (T-209) moves a candidate to local/.
  - Wisdom report (T-211) reports C7 + C8 curves on the resulting sessions.

The test is **fully hermetic**: HOME + ENGRAM_DIR are isolated to
``tmp_path``, providers are stubbed callables, no network.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.observer.protocol import parse_event
from engram.observer.queue import enqueue
from engram.observer.session import parse_session_file, sessions_root
from engram.observer.tier0 import compact_session
from engram.observer.tier1 import compact_to_session_asset
from engram.observer.tier2 import (
    SessionForDistill,
    distill_sessions,
    load_session_for_distill,
)
from engram.wisdom import compute_wisdom_report


CLIENTS = ["claude-code", "codex", "cursor", "raw-api", "claude-code"]
TASK_HASH = "bug-42-fix-pipeline"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    init_project(project, name="auto-cont-e2e", force=False)
    monkeypatch.setenv("ENGRAM_DIR", str(project))
    base = tmp_path / "engram-home"
    base.mkdir()
    return {"tmp": tmp_path, "project": project, "base": base}


def _emit_session_events(base: Path, sid: str, client: str, *, t0: datetime, n_tools: int, outcome: str) -> None:
    """Stream events for one session into the observer queue."""
    for i in range(n_tools):
        e = parse_event(
            {"event": "tool_use", "tool": "Read", "files": [f"src/file_{i}.py"]},
            session_id=sid,
            client=client,
            now=(t0 + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        enqueue(e, base=base)
    e = parse_event(
        {"event": "session_end", "outcome": outcome},
        session_id=sid,
        client=client,
        now=(t0 + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    )
    enqueue(e, base=base)


def test_cross_5_session_pipeline(env: dict[str, Path]) -> None:
    project: Path = env["project"]
    base: Path = env["base"]
    timelines = base / "timelines"
    timelines.mkdir(parents=True, exist_ok=True)

    started_dates = [
        datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc),
    ]
    outcomes = ["completed", "abandoned", "completed", "completed", "completed"]
    sids = ["s1_first", "s2_codex", "s3_cursor", "s4_offline", "s5_ship"]

    # 1) Stream events for each session into the queue.
    for sid, client, t0, outcome in zip(sids, CLIENTS, started_dates, outcomes, strict=True):
        _emit_session_events(base, sid, client, t0=t0, n_tools=4, outcome=outcome)

    # 2) Tier 0 compaction for each session.
    for sid in sids:
        compact_session(
            sid,
            queue_path=base / "observe-queue" / f"{sid}.jsonl",
            sessions_dir=timelines,
        )
        timeline = timelines / f"{sid}.timeline.jsonl"
        assert timeline.exists()
        # 4 tool_use + 1 session_end = 5 fact lines
        assert len(timeline.read_text().splitlines()) == 5

    # 3) Tier 1 — every client gets a real provider EXCEPT s4 (offline).
    def real_provider(_p: str) -> str:
        return "## Investigated\n- looked at the bug\n## Completed\n- fixed it\n"

    def offline_provider(_p: str) -> str:
        from engram.observer.providers import MECHANICAL_MARKER

        return MECHANICAL_MARKER

    for sid, client, t0, outcome in zip(sids, CLIENTS, started_dates, outcomes, strict=True):
        provider = offline_provider if sid == "s4_offline" else real_provider
        compact_to_session_asset(
            sid,
            timeline_path=timelines / f"{sid}.timeline.jsonl",
            client=client,
            project_root=project,
            provider=provider,
            task_hash=TASK_HASH,
            started_at=t0,
        )

    # 4) Each session asset lives under .memory/sessions/<date>/.
    found = sorted(
        p.stem for p in (project / ".memory" / "sessions").rglob("sess_*.md")
    )
    assert found == sorted(f"sess_{sid}" for sid in sids)

    # 5) Cross-session linkage chains s1 → s2 → s3 → s4 → s5 via task_hash.
    fms = {}
    for path in (project / ".memory" / "sessions").rglob("sess_*.md"):
        fm, _ = parse_session_file(path)
        fms[fm.session_id] = fm
    for i in range(len(sids)):
        sid = sids[i]
        fm = fms[sid]
        assert fm.task_hash == TASK_HASH
        if i > 0:
            assert fm.prev_session == sids[i - 1], (
                f"{sid} expected prev={sids[i - 1]} got {fm.prev_session}"
            )
        if i < len(sids) - 1:
            assert fm.next_session == sids[i + 1], (
                f"{sid} expected next={sids[i + 1]} got {fm.next_session}"
            )

    # 6) Offline session used mechanical fallback.
    s4_text = next(
        p for p in (project / ".memory" / "sessions").rglob("sess_s4_offline.md")
    ).read_text()
    assert "# Narrative (mechanical)" in s4_text

    # 7) Stage 0: feed sessions back through the Relevance Gate by hand
    #    (the daemon glue is wired separately in T-206 tests).
    from engram.observer.loader import load_session_continuations
    from engram.relevance.gate import (
        Asset,
        RelevanceRequest,
        run_relevance_gate,
    )
    from datetime import date

    sessions_for_gate = load_session_continuations(project_root=project)
    matching = [s for s in sessions_for_gate if s.task_hash == TASK_HASH]
    assert len(matching) == 5

    request = RelevanceRequest(
        query="continue fixing the pipeline bug",
        assets=[
            Asset(
                id="m1",
                scope="project",
                enforcement="default",
                subscribed_at=None,
                body="some unrelated note",
                updated=date(2026, 4, 25),
                size_bytes=64,
            )
        ],
        budget_tokens=8000,
        now=date(2026, 4, 29),
        task_hash=TASK_HASH,
        sessions=sessions_for_gate,
    )
    result = run_relevance_gate(request)
    # Stage 0 picks at most STAGE0_MAX_SESSIONS=3 sessions.
    assert 1 <= len(result.sessions) <= 3
    # Most recent should be s5 (it ended last).
    assert result.sessions[0].session_id == "s5_ship"

    # 8) Tier 2 distillation — yields ≥1 candidate via mechanical fallback
    #    (every session touched files that overlap across multiple sessions
    #    so recurring-files trigger fires).
    sessions_for_distill: list[SessionForDistill] = []
    for path in (project / ".memory" / "sessions").rglob("sess_*.md"):
        sfd = load_session_for_distill(path)
        if sfd is not None:
            sessions_for_distill.append(sfd)
    distill_result = distill_sessions(
        sessions_for_distill,
        memory_dir=project / ".memory",
        provider=lambda _p: json.dumps(
            [
                {
                    "name": "fix-pipeline-bug-42",
                    "description": "Stable approach for bug 42 across 5 sessions.",
                    "body": "- inspect src/file_*.py\n- trace tool ordering\n- ship fix\n",
                    "source_sessions": sids,
                }
            ]
        ),
    )
    assert len(distill_result.candidates) >= 1

    # 9) engram distill promote should move it into local/ (LLM consent path).
    runner = CliRunner()
    result = runner.invoke(
        cli, ["distill", "promote", "fix-pipeline-bug-42"]
    )
    assert result.exit_code == 0, result.output
    promoted = project / ".memory" / "local" / "fix-pipeline-bug-42.md"
    assert promoted.exists()

    # 10) source-session back-link: every contributing session has the
    #     promoted name in its distilled_into list.
    for sid in sids:
        path = next(
            p for p in (project / ".memory" / "sessions").rglob(f"sess_{sid}.md")
        )
        fm, _ = parse_session_file(path)
        assert "fix-pipeline-bug-42" in fm.distilled_into

    # 11) Wisdom report includes C7 + C8 with non-insufficient signal.
    wisdom = compute_wisdom_report(project)
    by_id = {c.id: c for c in wisdom.curves}
    assert "C7" in by_id and "C8" in by_id
    # C8 must show at least one promoted day since 5/5 sessions have
    # distilled_into populated post-promote. The fixture sessions end on
    # 2026-04-25..29, so the day-of-fixture sample is what to inspect —
    # not the last one (which can drift past the fixture window when
    # the test runs after midnight UTC).
    c8 = by_id["C8"]
    assert c8.insufficient is False
    assert any(s.value > 0.0 for s in c8.samples), (
        "expected at least one C8 sample > 0 across the wisdom window"
    )
