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
