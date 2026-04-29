"""T-210 tests for engram.observer.tier3 — procedural recognizer."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from engram.observer.providers import ProviderError
from engram.observer.session import (
    SessionFrontmatter,
    render_session_file,
    session_path,
)
from engram.observer.tier2 import SessionForDistill
from engram.observer.tier3 import (
    DEFAULT_TIER3_MIN_COMPLETED,
    DEFAULT_TIER3_MIN_TASK_RECURRENCES,
    ProcedureProposal,
    ProcedureResult,
    build_procedure_prompt,
    propose_procedures,
    render_procedure_proposal,
    run_tier3,
    workflows_dir,
)


def _sfd(
    sid: str,
    *,
    th: str | None = "task-1",
    outcome: str = "completed",
    files: tuple[str, ...] = (),
    body: str = "## Investigated\n- ok\n",
) -> SessionForDistill:
    return SessionForDistill(
        session_id=sid,
        task_hash=th,
        files_touched=files,
        outcome=outcome,
        body=body,
    )


# ----------------------------------------------------------------------
# Defaults + prompt
# ----------------------------------------------------------------------


def test_defaults() -> None:
    assert DEFAULT_TIER3_MIN_TASK_RECURRENCES == 3
    assert DEFAULT_TIER3_MIN_COMPLETED == 2


def test_prompt_includes_sessions() -> None:
    sessions = [_sfd("a", files=("src/foo.ts",))]
    p = build_procedure_prompt(sessions)
    assert "## Sessions" in p
    assert "### a" in p
    assert "`src/foo.ts`" in p


def test_prompt_warns_against_buzzwords() -> None:
    p = build_procedure_prompt([])
    assert "synergy" in p or "buzzword" in p.lower()


# ----------------------------------------------------------------------
# JSON parsing
# ----------------------------------------------------------------------


def test_propose_parses_json(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = json.dumps(
        [
            {
                "name": "Debug gRPC Timeout",
                "when_to_use": "When gRPC calls hang past 5 s.",
                "steps": [
                    "check the deadline header",
                    "inspect the upstream service health",
                    "raise the timeout in client config",
                ],
                "source_sessions": ["s0", "s1"],
            }
        ]
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert isinstance(result, ProcedureResult)
    assert len(result.proposals) == 1
    p = result.proposals[0]
    assert p.name == "debug-grpc-timeout"
    assert len(p.steps) == 3
    assert p.source_sessions == ("s0", "s1")
    assert result.used_mechanical_fallback is False


def test_propose_strips_markdown_fences(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = (
        "```json\n"
        + json.dumps(
            [
                {
                    "name": "x",
                    "when_to_use": "y",
                    "steps": ["a", "b", "c"],
                }
            ]
        )
        + "\n```"
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.proposals) == 1


def test_propose_skips_short_step_lists(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = json.dumps(
        [
            {"name": "ok", "when_to_use": "y", "steps": ["a", "b"]},  # 2 steps → skip
            {
                "name": "good",
                "when_to_use": "y",
                "steps": ["a", "b", "c"],
            },
        ]
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    names = [p.name for p in result.proposals]
    assert names == ["good"]


def test_propose_caps_at_four(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = json.dumps(
        [
            {"name": f"name-{i}", "when_to_use": "y", "steps": ["a", "b", "c"]}
            for i in range(20)
        ]
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.proposals) == 4


def test_propose_dedupes_by_slug(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = json.dumps(
        [
            {"name": "Debug gRPC Timeout", "when_to_use": "y", "steps": ["a", "b", "c"]},
            {"name": "debug-grpc-timeout", "when_to_use": "y", "steps": ["a", "b", "c"]},
        ]
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.proposals) == 1


# ----------------------------------------------------------------------
# Mechanical fallback
# ----------------------------------------------------------------------


def test_mechanical_qualifies_with_recurrence_and_completion(tmp_path: Path) -> None:
    sessions = [
        _sfd("s1", th="t1", outcome="completed", files=("src/a.py",)),
        _sfd("s2", th="t1", outcome="completed", files=("src/a.py",)),
        _sfd("s3", th="t1", outcome="abandoned", files=("src/a.py",)),
    ]
    result = propose_procedures(sessions, memory_dir=tmp_path)
    assert result.used_mechanical_fallback is True
    assert len(result.proposals) == 1
    assert result.proposals[0].source_sessions == ("s1", "s2", "s3")


def test_mechanical_skips_low_recurrence(tmp_path: Path) -> None:
    """Only 2 sessions for the same task — below default threshold of 3."""
    sessions = [
        _sfd("s1", th="t1", outcome="completed"),
        _sfd("s2", th="t1", outcome="completed"),
    ]
    result = propose_procedures(sessions, memory_dir=tmp_path)
    assert result.proposals == ()


def test_mechanical_skips_low_completion(tmp_path: Path) -> None:
    """3 sessions but only 1 completed — below default threshold of 2."""
    sessions = [
        _sfd("s1", th="t1", outcome="completed"),
        _sfd("s2", th="t1", outcome="abandoned"),
        _sfd("s3", th="t1", outcome="abandoned"),
    ]
    result = propose_procedures(sessions, memory_dir=tmp_path)
    assert result.proposals == ()


def test_mechanical_skips_sessions_without_task_hash(tmp_path: Path) -> None:
    sessions = [
        _sfd("s1", th=None, outcome="completed"),
        _sfd("s2", th=None, outcome="completed"),
        _sfd("s3", th=None, outcome="completed"),
    ]
    result = propose_procedures(sessions, memory_dir=tmp_path)
    assert result.proposals == ()


def test_provider_error_falls_back(tmp_path: Path) -> None:
    sessions = [
        _sfd(f"s{i}", th="t1", outcome="completed", files=("a.py",))
        for i in range(3)
    ]

    def boom(_p: str) -> str:
        raise ProviderError("LLM dead")

    result = propose_procedures(sessions, memory_dir=tmp_path, provider=boom)
    assert result.used_mechanical_fallback is True
    assert len(result.proposals) == 1


def test_invalid_json_falls_back(tmp_path: Path) -> None:
    sessions = [
        _sfd(f"s{i}", th="t1", outcome="completed") for i in range(3)
    ]
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: "not json"
    )
    assert result.used_mechanical_fallback is True


# ----------------------------------------------------------------------
# Render + on-disk layout
# ----------------------------------------------------------------------


def test_render_includes_required_sections() -> None:
    p = ProcedureProposal(
        name="x",
        when_to_use="y",
        steps=("a", "b", "c"),
        source_sessions=("s0",),
    )
    text = render_procedure_proposal(p, today=date(2026, 4, 29))
    assert "## When to use" in text
    assert "## Steps" in text
    assert "## Source sessions" in text
    assert "type: workflow_proposal" in text


def test_propose_writes_directory_layout(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    response = json.dumps(
        [
            {
                "name": "deploy-rollback",
                "when_to_use": "After failed deploys.",
                "steps": ["revert head", "redeploy", "verify health"],
                "source_sessions": ["s0", "s1"],
            }
        ]
    )
    result = propose_procedures(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.written_paths) == 1
    written = result.written_paths[0]
    expected = workflows_dir(memory_dir=tmp_path) / "deploy-rollback" / "proposal.md"
    assert written == expected


# ----------------------------------------------------------------------
# run_tier3 end-to-end with disk session fixtures
# ----------------------------------------------------------------------


def test_run_tier3_end_to_end(tmp_path: Path) -> None:
    paths: list[Path] = []
    for sid in ("a", "b", "c"):
        fm = SessionFrontmatter(
            type="session",
            session_id=sid,
            client="claude-code",
            started_at=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
            task_hash="t1",
            outcome="completed",
            files_touched=("src/a.py",),
        )
        p = session_path(sid, started_at=fm.started_at, memory_dir=tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_session_file(fm, "narrative\n"))
        paths.append(p)

    result = run_tier3(sessions_paths=paths, memory_dir=tmp_path)
    assert result.used_mechanical_fallback is True
    assert len(result.proposals) == 1
