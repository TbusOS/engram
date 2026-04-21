"""T-21 tests for engram.commands.review — aggregated health summary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.review import Review, run_review


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    init_project(tmp_path)
    yield tmp_path


def _add(project: Path, **overrides: str) -> None:
    runner = CliRunner()
    args = [
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        overrides.pop("type", "user"),
        "--name",
        overrides.pop("name", "thing"),
        "--description",
        overrides.pop("description", "desc"),
        "--body",
        overrides.pop("body", "body"),
    ]
    for k, v in overrides.items():
        args.extend([f"--{k.replace('_', '-')}", v])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output


# ------------------------------------------------------------------
# run_review pure function
# ------------------------------------------------------------------


def test_run_review_empty_project_has_structural_warning(project: Path) -> None:
    report = run_review(project)
    assert isinstance(report, Review)
    assert report.total_assets == 0
    # W-STR-001 (empty store) should appear
    codes = {i.code for i in report.issues}
    assert "W-STR-001" in codes


def test_run_review_counts_assets_by_subtype(project: Path) -> None:
    _add(project, type="user", name="u1")
    _add(project, type="user", name="u2")
    _add(project, type="project", name="p1", body="fact.\n\n**Why:** r.\n\n**How to apply:** a.")

    report = run_review(project)
    assert report.total_assets == 3
    assert report.by_subtype == {"user": 2, "project": 1}


def test_run_review_counts_by_lifecycle(project: Path) -> None:
    _add(project, name="one")
    _add(project, name="two")
    report = run_review(project)
    # Both are active by default
    assert report.by_lifecycle.get("active") == 2


def test_run_review_groups_issues_by_severity(project: Path) -> None:
    # Craft one error (bad scope) + rely on W-STR-001 via empty local/ being
    # avoided by adding a valid asset + an invalid one.
    _add(project, name="good")
    (project / ".memory" / "local" / "user_bad.md").write_text(
        "---\nname: x\ndescription: y\ntype: fabricated\nscope: user\n---\n\nbody\n",
        encoding="utf-8",
    )
    report = run_review(project)
    assert report.by_severity["error"] >= 1


def test_run_review_groups_issues_by_category(project: Path) -> None:
    (project / ".memory" / "local" / "user_bad.md").write_text(
        "---\nname: x\ndescription: y\ntype: fabricated\nscope: galaxy\n---\n\nbody\n",
        encoding="utf-8",
    )
    report = run_review(project)
    assert report.by_category.get("FM", 0) >= 2  # E-FM-006 + E-FM-008


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_review_always_exits_zero_even_with_errors(project: Path) -> None:
    """review is informational — unlike validate it never propagates CI failure."""
    (project / ".memory" / "local" / "user_bad.md").write_text(
        "---\nname: x\ndescription: y\ntype: fabricated\nscope: user\n---\n\nbody\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "review"])
    assert result.exit_code == 0, result.output


def test_cli_review_text_output_has_sections(project: Path) -> None:
    _add(project, name="hi")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "review"])
    assert result.exit_code == 0
    # Expect section headings in text output
    lowered = result.output.lower()
    assert "assets" in lowered
    assert "validation" in lowered or "issues" in lowered


def test_cli_review_shows_asset_counts(project: Path) -> None:
    _add(project, type="user", name="u1")
    _add(project, type="user", name="u2")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "review"])
    assert "user" in result.output
    assert "2" in result.output


def test_cli_review_json_output_structure(project: Path) -> None:
    _add(project, type="user", name="u1")
    _add(project, type="user", name="u2")
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "review"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert "assets" in payload
    assert "validation" in payload
    assert payload["assets"]["total"] == 2
    assert payload["assets"]["by_subtype"]["user"] == 2
    assert "by_severity" in payload["validation"]
    assert "by_category" in payload["validation"]
    assert "issues" in payload["validation"]


def test_cli_review_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "review" in result.output


def test_run_review_in_uninitialized_dir(tmp_path: Path) -> None:
    """review on a non-initialized dir still runs — validate catches E-STR-001."""
    report = run_review(tmp_path)
    codes = {i.code for i in report.issues}
    assert "E-STR-001" in codes
    assert report.total_assets == 0