"""T-20 tests for engram.commands.validate — SPEC §12 validators."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.memory import render_asset_file
from engram.commands.validate import (
    EXIT_CLEAN,
    EXIT_ERRORS,
    EXIT_WARNINGS,
    Issue,
    compute_exit_code,
    run_validate,
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    init_project(tmp_path)
    yield tmp_path


def _codes(issues: list[Issue]) -> set[str]:
    return {i.code for i in issues}


def _write_asset(project: Path, filename: str, frontmatter: str, body: str = "body") -> Path:
    """Bypass memory add to write raw content (so we can craft invalid files)."""
    path = project / ".memory" / "local" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"---\n{frontmatter}---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


# ------------------------------------------------------------------
# exit code machinery
# ------------------------------------------------------------------


def test_compute_exit_code_clean() -> None:
    assert compute_exit_code([]) == EXIT_CLEAN


def test_compute_exit_code_warnings_only() -> None:
    w = Issue("W-STR-001", "warning", ".memory", None, "empty", "SPEC §3")
    assert compute_exit_code([w]) == EXIT_WARNINGS


def test_compute_exit_code_errors_wins() -> None:
    w = Issue("W-STR-001", "warning", ".memory", None, "w", "SPEC §3")
    e = Issue("E-STR-001", "error", ".memory", None, "e", "SPEC §3.2")
    assert compute_exit_code([w, e]) == EXIT_ERRORS


# ------------------------------------------------------------------
# STR-* structural rules
# ------------------------------------------------------------------


def test_missing_memory_directory_raises_str_001(tmp_path: Path) -> None:
    """No .memory/ at all → E-STR-001."""
    issues = run_validate(tmp_path)
    assert "E-STR-001" in _codes(issues)


def test_missing_memory_md_raises_str_002(project: Path) -> None:
    (project / ".memory" / "MEMORY.md").unlink()
    issues = run_validate(project)
    assert "E-STR-002" in _codes(issues)


def test_missing_local_dir_raises_str_003(project: Path) -> None:
    (project / ".memory" / "local").rmdir()
    issues = run_validate(project)
    assert "E-STR-003" in _codes(issues)


def test_empty_memory_warns_str_001(project: Path) -> None:
    """Fresh init with no memories → W-STR-001."""
    issues = run_validate(project)
    assert "W-STR-001" in _codes(issues)


def test_unexpected_top_level_entry_warns_str_002(project: Path) -> None:
    (project / ".memory" / "surprise.txt").write_text("hi")
    issues = run_validate(project)
    assert "W-STR-002" in _codes(issues)


# ------------------------------------------------------------------
# FM-* frontmatter rules
# ------------------------------------------------------------------


def test_no_frontmatter_block_raises_fm_001(project: Path) -> None:
    (project / ".memory" / "local" / "user_noblock.md").write_text(
        "no frontmatter at all\n", encoding="utf-8"
    )
    issues = run_validate(project)
    assert "E-FM-001" in _codes(issues)


def test_malformed_yaml_raises_fm_002(project: Path) -> None:
    _write_asset(project, "user_bad.md", "name: [unclosed\n")
    issues = run_validate(project)
    assert "E-FM-002" in _codes(issues)


def test_missing_name_raises_fm_003(project: Path) -> None:
    _write_asset(project, "user_nameless.md", "description: d\ntype: user\nscope: user\n")
    issues = run_validate(project)
    assert "E-FM-003" in _codes(issues)


def test_missing_type_raises_fm_005(project: Path) -> None:
    _write_asset(project, "user_typeless.md", "name: a\ndescription: d\nscope: user\n")
    issues = run_validate(project)
    assert "E-FM-005" in _codes(issues)


def test_invalid_type_raises_fm_006(project: Path) -> None:
    _write_asset(
        project, "user_bad_type.md", "name: a\ndescription: d\ntype: fabricated\nscope: user\n"
    )
    issues = run_validate(project)
    assert "E-FM-006" in _codes(issues)


def test_missing_scope_raises_fm_007(project: Path) -> None:
    _write_asset(project, "user_scopeless.md", "name: a\ndescription: d\ntype: user\n")
    issues = run_validate(project)
    assert "E-FM-007" in _codes(issues)


def test_invalid_scope_raises_fm_008(project: Path) -> None:
    _write_asset(
        project, "user_bad_scope.md", "name: a\ndescription: d\ntype: user\nscope: galaxy\n"
    )
    issues = run_validate(project)
    assert "E-FM-008" in _codes(issues)


def test_long_description_warns_fm_002(project: Path) -> None:
    long_desc = "x" * 180
    _write_asset(
        project,
        "user_long.md",
        f"name: a\ndescription: {long_desc}\ntype: user\nscope: user\n",
    )
    issues = run_validate(project)
    assert "W-FM-002" in _codes(issues)


# ------------------------------------------------------------------
# MEM-* subtype rules
# ------------------------------------------------------------------


def test_feedback_without_enforcement_raises_mem_001(project: Path) -> None:
    _write_asset(
        project,
        "feedback_noenf.md",
        "name: a\ndescription: d\ntype: feedback\nscope: user\n",
    )
    issues = run_validate(project)
    assert "E-MEM-001" in _codes(issues)


def test_feedback_body_missing_why_raises_mem_003(project: Path) -> None:
    _write_asset(
        project,
        "feedback_no_why.md",
        "name: a\ndescription: d\ntype: feedback\nscope: user\nenforcement: hint\n",
        body="just a rule, no why or how",
    )
    issues = run_validate(project)
    assert "E-MEM-003" in _codes(issues)


def test_feedback_body_with_why_and_how_passes_mem_003(project: Path) -> None:
    _write_asset(
        project,
        "feedback_good.md",
        "name: a\ndescription: d\ntype: feedback\nscope: user\nenforcement: hint\n",
        body="Rule.\n\n**Why:** reason.\n\n**How to apply:** always.",
    )
    issues = run_validate(project)
    assert "E-MEM-003" not in _codes(issues)


def test_project_body_missing_why_raises_mem_004(project: Path) -> None:
    _write_asset(
        project,
        "project_no_why.md",
        "name: a\ndescription: d\ntype: project\nscope: project\n",
        body="just a fact",
    )
    issues = run_validate(project)
    assert "E-MEM-004" in _codes(issues)


def test_workflow_ptr_missing_workflow_ref_raises_mem_005(project: Path) -> None:
    _write_asset(
        project,
        "workflow_ptr_no_ref.md",
        "name: a\ndescription: d\ntype: workflow_ptr\nscope: project\n",
    )
    issues = run_validate(project)
    assert "E-MEM-005" in _codes(issues)


def test_agent_missing_source_raises_mem_007(project: Path) -> None:
    _write_asset(
        project,
        "agent_no_source.md",
        "name: a\ndescription: d\ntype: agent\nscope: project\nenforcement: hint\n",
        body="Heuristic.\n\n**Why:** observed.\n\n**How to apply:** here.",
    )
    issues = run_validate(project)
    assert "E-MEM-007" in _codes(issues)


def test_agent_without_confidence_warns_mem_002(project: Path) -> None:
    _write_asset(
        project,
        "agent_no_conf.md",
        "name: a\ndescription: d\ntype: agent\nscope: project\n"
        "enforcement: hint\nsource: agent-learned\n",
        body="Heuristic.\n\n**Why:** observed.\n\n**How to apply:** here.",
    )
    issues = run_validate(project)
    assert "W-MEM-002" in _codes(issues)


# ------------------------------------------------------------------
# IDX-* index rules
# ------------------------------------------------------------------


def test_unindexed_asset_raises_idx_002(project: Path) -> None:
    _write_asset(
        project,
        "user_orphan.md",
        "name: a\ndescription: d\ntype: user\nscope: user\n",
    )
    # MEMORY.md from init_project has no entry for this file.
    issues = run_validate(project)
    assert "E-IDX-002" in _codes(issues)


def test_indexed_asset_passes_idx_002(project: Path) -> None:
    _write_asset(
        project,
        "user_listed.md",
        "name: a\ndescription: d\ntype: user\nscope: user\n",
    )
    index = project / ".memory" / "MEMORY.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(
        text + "\n- [user_listed](local/user_listed.md) — hook\n", encoding="utf-8"
    )
    issues = run_validate(project)
    assert "E-IDX-002" not in _codes(issues)


def test_dangling_index_link_raises_idx_001(project: Path) -> None:
    index = project / ".memory" / "MEMORY.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(
        text + "\n- [nope](local/does_not_exist.md) — hook\n", encoding="utf-8"
    )
    issues = run_validate(project)
    assert "E-IDX-001" in _codes(issues)


# ------------------------------------------------------------------
# REF-* reference graph rules
# ------------------------------------------------------------------


def test_dangling_reference_raises_ref_001(project: Path) -> None:
    _write_asset(
        project,
        "user_dangling.md",
        "name: a\ndescription: d\ntype: user\nscope: user\n"
        "references:\n  - local/user_missing\n",
    )
    issues = run_validate(project)
    assert "E-REF-001" in _codes(issues)


def test_valid_reference_passes(project: Path) -> None:
    _write_asset(
        project,
        "user_target.md",
        "name: target\ndescription: t\ntype: user\nscope: user\n",
    )
    _write_asset(
        project,
        "user_source.md",
        "name: source\ndescription: s\ntype: user\nscope: user\n"
        "references:\n  - local/user_target\n",
    )
    issues = run_validate(project)
    assert "E-REF-001" not in _codes(issues)


def test_supersedes_dangling_raises_ref_003(project: Path) -> None:
    _write_asset(
        project,
        "user_super.md",
        "name: a\ndescription: d\ntype: user\nscope: user\n"
        "supersedes: local/user_ghost\n",
    )
    issues = run_validate(project)
    assert "E-REF-003" in _codes(issues)


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_validate_clean_project_text(project: Path) -> None:
    """Fresh project with no memories: W-STR-001 only (empty store) → exit 1."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "validate"])
    assert result.exit_code == EXIT_WARNINGS


def test_cli_validate_project_with_valid_memory_text(project: Path) -> None:
    """A project with one well-formed, indexed memory should exit 0."""
    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "hello",
            "--description",
            "d",
            "--body",
            "body",
        ],
    )
    # Add index entry so E-IDX-002 doesn't fire.
    index = project / ".memory" / "MEMORY.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(
        text + "\n- [hello](local/user_hello.md) — hook\n", encoding="utf-8"
    )
    result = runner.invoke(cli, ["--dir", str(project), "validate"])
    assert result.exit_code == EXIT_CLEAN, result.output


def test_cli_validate_errors_exit_2(project: Path) -> None:
    _write_asset(
        project,
        "user_bad.md",
        "name: a\ndescription: d\ntype: fabricated\nscope: user\n",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "validate"])
    assert result.exit_code == EXIT_ERRORS


def test_cli_validate_text_output_shows_codes(project: Path) -> None:
    _write_asset(
        project,
        "user_bad.md",
        "name: a\ndescription: d\ntype: fabricated\nscope: user\n",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "validate"])
    assert "E-FM-006" in result.output
    assert "error" in result.output.lower()


def test_cli_validate_json_output(project: Path) -> None:
    _write_asset(
        project,
        "user_bad.md",
        "name: a\ndescription: d\ntype: fabricated\nscope: user\n",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "validate"]
    )
    assert result.exit_code == EXIT_ERRORS
    payload = json.loads(result.output.strip())
    assert "summary" in payload
    assert "issues" in payload
    assert payload["summary"]["errors"] >= 1
    codes = {i["code"] for i in payload["issues"]}
    assert "E-FM-006" in codes


def test_cli_validate_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "validate" in result.output
