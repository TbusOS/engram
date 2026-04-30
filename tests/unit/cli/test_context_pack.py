"""T-56 tests: ``engram context pack`` — Relevance-Gate-driven context CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli


def _invoke(runner: CliRunner, *args: str) -> str:
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
    return result.output


@pytest.fixture
def populated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init", "--name", "ctx-test")

    # Seed a few assets mixing scopes and enforcement levels.
    for name, subtype, enforcement, body in (
        (
            "kernel fluency",
            "user",
            None,
            "The user reads kernel mm/ and fs/ code regularly.",
        ),
        (
            "confirm before push",
            "feedback",
            "mandatory",
            "Ask before pushing.\n\n**Why:** safety.\n\n**How to apply:** all repos.",
        ),
        (
            "k8s migration",
            "project",
            None,
            "Migrating services to k8s by Q2.\n\n"
            "**Why:** nomad EOL.\n\n**How to apply:** one service at a time.",
        ),
    ):
        args = [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            subtype,
            "--name",
            name,
            "--description",
            f"{name} description",
            "--body",
            body,
        ]
        if enforcement:
            args.extend(["--enforcement", enforcement])
        _invoke(runner, *args)
    return project


# ------------------------------------------------------------------
# Happy path across formats
# ------------------------------------------------------------------


def test_context_pack_default_prompt_format(populated_project: Path) -> None:
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel work",
    )
    assert "# Context pack" in out
    assert "kernel" in out.lower()


def test_context_pack_mandatory_always_included(populated_project: Path) -> None:
    """Mandatory assets bypass ranking. The push-rule mandatory asset
    should appear in the pack regardless of the query."""
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "sharding",  # doesn't match any seeded body
    )
    assert "Mandatory" in out
    assert "confirm_before_push" in out or "feedback_confirm" in out


def test_context_pack_json_format_is_valid(populated_project: Path) -> None:
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel",
        "--format",
        "json",
    )
    payload = json.loads(out.strip())
    assert payload["task"] == "kernel"
    assert "mandatory" in payload
    assert "included" in payload
    assert "excluded_due_to_budget" in payload
    assert payload["total_tokens"] >= 0


def test_context_pack_markdown_format_has_breakdown(
    populated_project: Path,
) -> None:
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel",
        "--format",
        "markdown",
    )
    assert "Mandatory" in out
    assert "Ranked included" in out


def test_context_pack_budget_excludes_overflow(populated_project: Path) -> None:
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel k8s migration",
        "--budget",
        "2",  # absurdly small; everything ranked gets excluded
        "--format",
        "json",
    )
    payload = json.loads(out.strip())
    # Mandatory always survives; ranked items should fall into excluded.
    assert len(payload["mandatory"]) >= 1
    # Either we included nothing, or something with very low tokens_est.
    assert payload["total_tokens"] <= 10


def test_context_pack_empty_store_produces_usable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "empty"
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    out = _invoke(
        runner,
        "--dir",
        str(project),
        "context",
        "pack",
        "--task",
        "anything",
        "--format",
        "json",
    )
    payload = json.loads(out.strip())
    assert payload["included"] == []
    assert payload["mandatory"] == []


def test_context_pack_requires_task_flag(populated_project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(populated_project), "context", "pack"]
    )
    assert result.exit_code != 0
    assert "--task" in result.output or "Missing option" in result.output


# ------------------------------------------------------------------
# Q8 / T-206 — Stage 0 task_hash wiring through the CLI
# ------------------------------------------------------------------


def _seed_session(project: Path, *, sid: str, task_hash: str, body: str) -> None:
    from datetime import datetime, timezone

    from engram.observer.session import (
        SessionFrontmatter,
        render_session_file,
        session_path,
    )

    started = datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    fm = SessionFrontmatter(
        type="session",
        session_id=sid,
        client="claude-code",
        started_at=started,
        ended_at=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
        task_hash=task_hash,
    )
    p = session_path(sid, started_at=started, memory_dir=project / ".memory")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, body))


def test_context_pack_explicit_task_hash_injects_session(
    populated_project: Path,
) -> None:
    _seed_session(
        populated_project,
        sid="abc",
        task_hash="explicit-hash",
        body="## Investigated\n- Stage 0 must surface this body\n",
    )
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel work",
        "--task-hash",
        "explicit-hash",
    )
    assert "Recent session continuation (Stage 0)" in out
    assert "Stage 0 must surface this body" in out


def test_context_pack_no_continuation_skips_stage0(
    populated_project: Path,
) -> None:
    _seed_session(
        populated_project,
        sid="abc",
        task_hash="explicit-hash",
        body="must NOT appear when --no-continuation is set",
    )
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel work",
        "--task-hash",
        "explicit-hash",
        "--no-continuation",
    )
    assert "must NOT appear" not in out
    assert "Stage 0" not in out


def test_context_pack_empty_task_hash_disables_stage0(
    populated_project: Path,
) -> None:
    _seed_session(
        populated_project,
        sid="abc",
        task_hash="some-hash",
        body="should be skipped",
    )
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel work",
        "--task-hash",
        "",
    )
    assert "Stage 0" not in out


def test_context_pack_json_includes_sessions(populated_project: Path) -> None:
    _seed_session(
        populated_project,
        sid="abc",
        task_hash="some-hash",
        body="body content",
    )
    runner = CliRunner()
    out = _invoke(
        runner,
        "--dir",
        str(populated_project),
        "context",
        "pack",
        "--task",
        "kernel work",
        "--task-hash",
        "some-hash",
        "--format",
        "json",
    )
    payload = json.loads(out)
    assert "sessions" in payload
    assert any(s["session_id"] == "abc" for s in payload["sessions"])
    assert payload["sessions_tokens"] > 0
