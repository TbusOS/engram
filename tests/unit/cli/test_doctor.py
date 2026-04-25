"""T-162 tests for ``engram doctor`` — health check + executable repair hints.

doctor is the **user-facing troubleshooter**, distinct from:

- ``engram validate``: SPEC §12 contract enforcement (errors / warnings on
  asset format, with stable INV-IDs)
- ``engram review``: SPEC §16 percentile signals + low-confidence + expired
  items (aggregate health snapshot)

doctor answers a single question: **"what's wrong with my store right now,
and what command do I run to fix it?"** Every issue line ends with a
``→ run: <command>`` so the operator does not have to look up the fix.

Five check categories:

1. layout — `.memory/` / `.engram/` / version file present
2. index — every asset reachable from MEMORY.md (issue #5 reachability
   semantics will land in T-181; today: directly listed per INV-I1)
3. graph_db — DB-vs-disk drift (asset row → file missing, file → no row)
4. pools — subscribed pools' last_synced_rev vs available `rev/current`
5. mandatory_budget — sum of mandatory body sizes vs SPEC-recommended cap
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import adopt_project, init_project
from engram.commands.memory import graph_db_path
from engram.core.graph_db import open_graph_db
from engram.doctor import run_doctor
from engram.doctor.types import CheckIssue, DoctorReport, Severity


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    """Empty engram project — passes all doctor checks."""
    init_project(tmp_path)
    yield tmp_path


_VALID_FEEDBACK = """\
---
name: confirm before push
description: prompt before any git push
type: feedback
scope: project
enforcement: default
created: 2026-04-20
---

The body of the rule.
"""


def _add_via_adopt(project: Path, filename: str, content: str) -> None:
    """Helper: write a file to local/ then re-adopt to register it."""
    (project / ".memory" / "local" / filename).write_text(content, encoding="utf-8")
    adopt_project(project)


# ------------------------------------------------------------------
# DoctorReport / CheckIssue contract
# ------------------------------------------------------------------


class TestReportShape:
    def test_clean_project_has_no_issues(self, project: Path) -> None:
        report = run_doctor(project)
        assert isinstance(report, DoctorReport)
        assert report.issues == []
        assert report.is_healthy() is True

    def test_issue_has_required_fields(self, project: Path) -> None:
        # Force one known issue: delete .engram/version
        (project / ".engram" / "version").unlink()
        report = run_doctor(project)
        assert report.issues, "expected at least one issue"
        issue = report.issues[0]
        assert isinstance(issue, CheckIssue)
        assert issue.code  # stable check id
        assert issue.severity in {Severity.ERROR, Severity.WARNING, Severity.INFO}
        assert issue.message
        assert issue.fix_command  # every issue MUST tell user how to fix


# ------------------------------------------------------------------
# Layout checks
# ------------------------------------------------------------------


class TestLayoutChecks:
    def test_missing_memory_dir(self, tmp_path: Path) -> None:
        # .memory/ does not exist at all
        report = run_doctor(tmp_path)
        codes = {i.code for i in report.issues}
        assert "DOC-LAYOUT-001" in codes
        assert any("engram init" in i.fix_command for i in report.issues)

    def test_missing_engram_version(self, project: Path) -> None:
        (project / ".engram" / "version").unlink()
        report = run_doctor(project)
        codes = {i.code for i in report.issues}
        assert "DOC-LAYOUT-002" in codes


# ------------------------------------------------------------------
# graph.db drift checks
# ------------------------------------------------------------------


class TestGraphDbDrift:
    def test_file_present_but_no_db_row(self, project: Path) -> None:
        # Write a valid asset but do NOT register it in graph.db
        (project / ".memory" / "local" / "feedback_orphan.md").write_text(
            _VALID_FEEDBACK, encoding="utf-8"
        )
        report = run_doctor(project)
        codes = [i.code for i in report.issues]
        assert "DOC-GRAPH-001" in codes
        # Fix command must reference adopt
        graph_issue = next(i for i in report.issues if i.code == "DOC-GRAPH-001")
        assert "adopt" in graph_issue.fix_command

    def test_db_row_but_file_deleted(self, project: Path) -> None:
        _add_via_adopt(project, "feedback_will_vanish.md", _VALID_FEEDBACK)
        # Remove the file but leave the row
        (project / ".memory" / "local" / "feedback_will_vanish.md").unlink()
        report = run_doctor(project)
        codes = [i.code for i in report.issues]
        assert "DOC-GRAPH-002" in codes


# ------------------------------------------------------------------
# Index reachability
# ------------------------------------------------------------------


class TestIndexReachability:
    def test_asset_not_in_memory_md(self, project: Path) -> None:
        _add_via_adopt(project, "feedback_unindexed.md", _VALID_FEEDBACK)
        # MEMORY.md skeleton from init has no entry for this asset
        report = run_doctor(project)
        codes = [i.code for i in report.issues]
        assert "DOC-INDEX-001" in codes
        # Fix command must reference index rebuild or manual edit
        idx_issue = next(i for i in report.issues if i.code == "DOC-INDEX-001")
        assert (
            "MEMORY.md" in idx_issue.fix_command
            or "index" in idx_issue.fix_command.lower()
        )


# ------------------------------------------------------------------
# Mandatory budget
# ------------------------------------------------------------------


class TestMandatoryBudget:
    def test_under_budget_no_warning(self, project: Path) -> None:
        # The default project after init has zero mandatory assets.
        report = run_doctor(project)
        budget_issues = [i for i in report.issues if i.code.startswith("DOC-MAND-")]
        assert budget_issues == []

    def test_over_budget_warns(self, project: Path) -> None:
        # Create a single mandatory asset with a large body to exceed the
        # default doctor budget threshold.
        large = "y" * 10_000
        big_mandatory = (
            "---\n"
            "name: huge mandatory rule\n"
            "description: an oversized mandatory rule for budget test\n"
            "type: feedback\n"
            "scope: project\n"
            "enforcement: mandatory\n"
            "created: 2026-04-20\n"
            "---\n\n"
            f"{large}\n"
        )
        _add_via_adopt(project, "feedback_huge_mandatory.md", big_mandatory)
        # Lower the budget to a small value so the test does not depend on
        # the production default
        report = run_doctor(project, mandatory_budget_bytes=2_000)
        codes = [i.code for i in report.issues]
        assert "DOC-MAND-001" in codes
        mand_issue = next(i for i in report.issues if i.code == "DOC-MAND-001")
        assert "directive" in mand_issue.fix_command.lower() or "engram" in mand_issue.fix_command


# ------------------------------------------------------------------
# CLI surface
# ------------------------------------------------------------------


def _run(project: Path, *args: str) -> "object":
    runner = CliRunner()
    return runner.invoke(
        cli, ["--dir", str(project), "doctor", *args], catch_exceptions=False
    )


class TestDoctorCli:
    def test_clean_project_exits_zero(self, project: Path) -> None:
        result = _run(project)
        assert result.exit_code == 0
        assert "healthy" in result.output.lower()

    def test_issues_exit_nonzero(self, project: Path) -> None:
        (project / ".engram" / "version").unlink()
        result = _run(project)
        assert result.exit_code != 0
        # Output must include the fix command
        assert "→ run:" in result.output or "run:" in result.output

    def test_json_output(self, project: Path) -> None:
        (project / ".engram" / "version").unlink()
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--format", "json", "--dir", str(project), "doctor"],
            catch_exceptions=False,
        )
        # Non-zero exit because of issues, but the JSON must still parse
        payload = json.loads(result.output)
        assert "issues" in payload
        assert payload["issues"]
        for issue in payload["issues"]:
            for required_field in ("code", "severity", "message", "fix_command"):
                assert required_field in issue
