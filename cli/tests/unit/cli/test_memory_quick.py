"""T-160 tests for ``engram memory quick`` — zero-config one-line entry.

Per `docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md` Week 1, T-160
implements the friction-zero entry point that issue #2 requested. The flag
contract:

- single positional ``BODY`` argument (stdin via ``-``)
- ``--type`` defaults to ``project`` (note: no ``note`` subtype exists in
  the SPEC §4 enum, so ``project`` is the closest semantic match for
  "I just want to record a fact")
- ``--scope`` defaults to ``project``
- ``name`` is derived from body first non-empty line (markdown ``#``
  stripped), capped at 80 chars
- ``description`` is derived from body first 150 chars (newlines collapsed),
  truncated with ``...`` if longer
- name slug collisions get ``-2``, ``-3``, ... suffixes
- ``--name`` / ``--description`` flags override the auto-derivation
- the produced asset must validate clean — no errors, no warnings beyond
  pre-existing project state
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.memory import (
    compute_id,
    derive_quick_name,
    derive_quick_description,
    graph_db_path,
    memory_file_path,
)
from engram.core.frontmatter import parse_file
from engram.core.graph_db import open_graph_db


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    init_project(tmp_path)
    yield tmp_path


# ------------------------------------------------------------------
# derivation helpers (pure functions — fastest tests)
# ------------------------------------------------------------------


class TestDeriveName:
    def test_first_line_under_cap(self) -> None:
        assert derive_quick_name("kinit before ssh\nthen run ...") == "kinit before ssh"

    def test_strips_markdown_heading_marks(self) -> None:
        assert derive_quick_name("## A heading line\nbody") == "A heading line"
        assert derive_quick_name("# Heading") == "Heading"
        assert derive_quick_name("###   leading hash spaces") == "leading hash spaces"

    def test_skips_blank_leading_lines(self) -> None:
        assert derive_quick_name("\n\n  \nfirst real line\nbody") == "first real line"

    def test_caps_at_80_chars(self) -> None:
        long = "x" * 200
        out = derive_quick_name(long)
        assert len(out) <= 80
        assert out == "x" * 80

    def test_empty_body_falls_back(self) -> None:
        assert derive_quick_name("") == "untitled"
        assert derive_quick_name("\n\n  \n") == "untitled"

    def test_strips_trailing_whitespace(self) -> None:
        assert derive_quick_name("  hello world   \nbody") == "hello world"


class TestDeriveDescription:
    def test_short_body_passthrough(self) -> None:
        assert derive_quick_description("a short note") == "a short note"

    def test_collapses_newlines(self) -> None:
        out = derive_quick_description("line one\nline two\nline three")
        assert "\n" not in out
        assert out.startswith("line one")

    def test_truncates_at_150_with_ellipsis(self) -> None:
        body = "x" * 300
        out = derive_quick_description(body)
        assert len(out) == 150
        assert out.endswith("...")

    def test_empty_body(self) -> None:
        assert derive_quick_description("") == ""

    def test_strips_markdown_heading_marks_first_line(self) -> None:
        out = derive_quick_description("## title\nthe body content here")
        assert out.startswith("title")


# ------------------------------------------------------------------
# CLI behavior
# ------------------------------------------------------------------


def _run(project_root: Path, *args: str, input: str | None = None) -> "object":
    runner = CliRunner()
    return runner.invoke(
        cli,
        ["--dir", str(project_root), *args],
        input=input,
        catch_exceptions=False,
    )


class TestQuickCmd:
    def test_body_only_invocation(self, project: Path) -> None:
        result = _run(
            project,
            "memory",
            "quick",
            "kinit before ssh to build.acme.internal",
        )
        assert result.exit_code == 0, result.output

        # Asset registered to graph.db with project subtype + project scope
        with open_graph_db(graph_db_path(project)) as conn:
            rows = conn.execute(
                "SELECT id, subtype, scope FROM assets WHERE kind='memory'"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["subtype"] == "project"
        assert rows[0]["scope"] == "project"
        assert rows[0]["id"].startswith("local/project_kinit_before_ssh")

    def test_auto_derived_frontmatter_validates(self, project: Path) -> None:
        result = _run(
            project,
            "memory",
            "quick",
            "kinit before ssh to build.acme.internal",
        )
        assert result.exit_code == 0

        # The on-disk file must round-trip through parse_file without errors
        file_path = memory_file_path(
            project, "local", "project", "kinit_before_ssh_to_build_acme_internal"
        )
        assert file_path.exists()
        fm, _body = parse_file(file_path)
        assert fm.type.value == "project"
        assert fm.scope.value == "project"
        assert fm.name == "kinit before ssh to build.acme.internal"
        assert fm.description.startswith("kinit before ssh")

    def test_explicit_type_and_scope_overrides(self, project: Path) -> None:
        result = _run(
            project,
            "memory",
            "quick",
            "Always run black before commit",
            "--type",
            "feedback",
            "--enforcement",
            "default",
        )
        assert result.exit_code == 0
        with open_graph_db(graph_db_path(project)) as conn:
            row = conn.execute(
                "SELECT subtype, enforcement FROM assets WHERE kind='memory'"
            ).fetchone()
        assert row["subtype"] == "feedback"
        assert row["enforcement"] == "default"

    def test_explicit_name_and_description_override_derivation(self, project: Path) -> None:
        result = _run(
            project,
            "memory",
            "quick",
            "body content here",
            "--name",
            "explicit name",
            "--description",
            "explicit description",
        )
        assert result.exit_code == 0
        file_path = memory_file_path(project, "local", "project", "explicit_name")
        assert file_path.exists()
        fm, _body = parse_file(file_path)
        assert fm.name == "explicit name"
        assert fm.description == "explicit description"

    def test_name_collision_appends_suffix(self, project: Path) -> None:
        # Two quicks with the same first line → second one auto-suffixed
        for _ in range(2):
            result = _run(project, "memory", "quick", "duplicate first line\nbody")
            assert result.exit_code == 0

        with open_graph_db(graph_db_path(project)) as conn:
            ids = sorted(
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM assets WHERE kind='memory' ORDER BY id"
                ).fetchall()
            )
        assert ids[0] == "local/project_duplicate_first_line"
        assert ids[1].startswith("local/project_duplicate_first_line_")

    def test_stdin_body(self, project: Path) -> None:
        result = _run(
            project,
            "memory",
            "quick",
            "-",
            input="piped body line\nmore content\n",
        )
        assert result.exit_code == 0
        with open_graph_db(graph_db_path(project)) as conn:
            row = conn.execute(
                "SELECT id, subtype FROM assets WHERE kind='memory'"
            ).fetchone()
        assert row["id"].startswith("local/project_piped_body_line")

    def test_empty_body_rejected(self, project: Path) -> None:
        result = _run(project, "memory", "quick", "")
        assert result.exit_code != 0
        assert "empty" in result.output.lower() or "body" in result.output.lower()

    def test_json_output_format(self, project: Path) -> None:
        result = _run(
            project,
            "--format",
            "json",
            "memory",
            "quick",
            "json output test",
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "id" in payload
        assert "path" in payload
        assert payload["id"].startswith("local/project_json_output_test")

    def test_feedback_without_enforcement_uses_default(self, project: Path) -> None:
        # feedback subtype requires enforcement per SPEC §4.3; quick supplies
        # enforcement=default automatically when --type=feedback and the
        # operator did not pass --enforcement
        result = _run(
            project,
            "memory",
            "quick",
            "Always rebase before merge",
            "--type",
            "feedback",
        )
        assert result.exit_code == 0
        file_path = memory_file_path(project, "local", "feedback", "always_rebase_before_merge")
        fm, _body = parse_file(file_path)
        assert fm.enforcement.value == "default"

    def test_long_body_description_truncated(self, project: Path) -> None:
        long = "first short line\n" + ("y" * 500)
        result = _run(project, "memory", "quick", long)
        assert result.exit_code == 0
        file_path = memory_file_path(project, "local", "project", "first_short_line")
        fm, _body = parse_file(file_path)
        assert len(fm.description) <= 150
