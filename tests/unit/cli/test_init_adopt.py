"""T-161 tests for ``engram init --adopt`` (issue #1).

Adopt mode handles the highest-frequency portability scenario: a teammate
has already maintained `.memory/` for months, you just cloned the repo, and
you need engram to register the existing assets in your local graph.db
*without* clobbering the hand-curated MEMORY.md.

The flag contract:

- ``adopt_project(root)`` is the pure function: never writes MEMORY.md /
  pools.toml; ensures `.engram/version`; scans `local/`, `workflows/`,
  `kb/` for `*.md` with valid frontmatter; registers each in graph.db;
  returns a result with counts + per-file warnings.
- ``engram init`` on an existing `.memory/`:
  - defaults to adopt mode (no longer errors)
  - explicit ``--adopt`` is also accepted (idempotent)
  - ``--force`` keeps current overwrite-skeleton behavior
- ``engram init --adopt`` on a missing `.memory/` raises (you cannot adopt
  what does not exist; use plain ``engram init``)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import STORE_VERSION, adopt_project, init_project
from engram.commands.memory import graph_db_path
from engram.core.graph_db import open_graph_db


_VALID_FM = """\
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

_INVALID_FM = """\
---
type: not-a-real-type
scope: project
---

Broken frontmatter — wrong subtype enum.
"""


@pytest.fixture
def precurated_store(tmp_path: Path) -> Iterator[Path]:
    """A `.memory/` tree populated by hand, no `.engram/` yet — like a
    fresh clone of someone else's engram-managed repo."""
    memory = tmp_path / ".memory"
    for sub in ("local", "pools", "workflows", "kb"):
        (memory / sub).mkdir(parents=True)
    # User-curated MEMORY.md that adopt MUST NOT touch
    memory.joinpath("MEMORY.md").write_text(
        "# MEMORY.md\n\n## Identity\n- Hand-curated identity line\n", encoding="utf-8"
    )
    memory.joinpath("pools.toml").write_text(
        "# user-curated pool subscription stub\n", encoding="utf-8"
    )
    (memory / "local" / "feedback_confirm_before_push.md").write_text(
        _VALID_FM, encoding="utf-8"
    )
    yield tmp_path


# ------------------------------------------------------------------
# adopt_project() pure function
# ------------------------------------------------------------------


class TestAdoptProject:
    def test_adopt_requires_existing_memory_dir(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match="not a SPEC-compliant"):
            adopt_project(tmp_path)

    def test_adopt_creates_engram_version_when_missing(
        self, precurated_store: Path
    ) -> None:
        adopt_project(precurated_store)
        version_file = precurated_store / ".engram" / "version"
        assert version_file.exists()
        assert version_file.read_text(encoding="utf-8").strip() == STORE_VERSION

    def test_adopt_does_not_overwrite_memory_md(self, precurated_store: Path) -> None:
        original = (precurated_store / ".memory" / "MEMORY.md").read_text(
            encoding="utf-8"
        )
        adopt_project(precurated_store)
        after = (precurated_store / ".memory" / "MEMORY.md").read_text(
            encoding="utf-8"
        )
        assert after == original
        assert "Hand-curated identity line" in after

    def test_adopt_does_not_overwrite_pools_toml(self, precurated_store: Path) -> None:
        original = (precurated_store / ".memory" / "pools.toml").read_text(
            encoding="utf-8"
        )
        adopt_project(precurated_store)
        after = (precurated_store / ".memory" / "pools.toml").read_text(
            encoding="utf-8"
        )
        assert after == original

    def test_adopt_registers_valid_assets_in_graph_db(
        self, precurated_store: Path
    ) -> None:
        result = adopt_project(precurated_store)
        with open_graph_db(graph_db_path(precurated_store)) as conn:
            rows = conn.execute(
                "SELECT id, subtype, scope FROM assets WHERE kind='memory'"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == "local/feedback_confirm_before_push"
        assert rows[0]["subtype"] == "feedback"
        assert result.registered == 1
        assert result.skipped == 0

    def test_adopt_skips_invalid_frontmatter_with_warning(
        self, precurated_store: Path
    ) -> None:
        (precurated_store / ".memory" / "local" / "broken.md").write_text(
            _INVALID_FM, encoding="utf-8"
        )
        result = adopt_project(precurated_store)
        assert result.registered == 1  # the valid one still got in
        assert result.skipped == 1
        assert any("broken.md" in w for w in result.warnings)

    def test_adopt_is_idempotent(self, precurated_store: Path) -> None:
        # Running twice must not double-register or error. The graph.db state
        # must match either way; the second run should report the asset as
        # skipped (already present), not registered again.
        first = adopt_project(precurated_store)
        second = adopt_project(precurated_store)
        assert first.registered == 1
        assert second.registered == 0
        assert second.skipped == 1
        with open_graph_db(graph_db_path(precurated_store)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM assets WHERE kind='memory'"
            ).fetchone()["c"]
        assert count == 1

    def test_adopt_walks_workflows_and_kb_directories(
        self, precurated_store: Path
    ) -> None:
        # workflow_ptr and kb files (when valid) should also be picked up
        wp_dir = precurated_store / ".memory" / "local"
        wp = """\
---
name: git rebase workflow ptr
description: pointer to git rebase workflow
type: workflow_ptr
scope: project
workflow_ref: workflows/git-rebase
created: 2026-04-20
---

Pointer body.
"""
        (wp_dir / "workflow_ptr_git_rebase.md").write_text(wp, encoding="utf-8")
        result = adopt_project(precurated_store)
        assert result.registered == 2


# ------------------------------------------------------------------
# CLI dispatch — `engram init` on existing `.memory/`
# ------------------------------------------------------------------


def _run(target: Path, *args: str) -> "object":
    runner = CliRunner()
    return runner.invoke(
        cli, ["--dir", str(target), "init", *args], catch_exceptions=False
    )


class TestInitCliAdoptDispatch:
    def test_init_on_existing_memory_defaults_to_adopt(
        self, precurated_store: Path
    ) -> None:
        result = _run(precurated_store)
        assert result.exit_code == 0
        # Curated MEMORY.md preserved
        text = (precurated_store / ".memory" / "MEMORY.md").read_text(
            encoding="utf-8"
        )
        assert "Hand-curated identity line" in text
        # Asset registered
        with open_graph_db(graph_db_path(precurated_store)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM assets WHERE kind='memory'"
            ).fetchone()["c"]
        assert count == 1

    def test_init_explicit_adopt_flag(self, precurated_store: Path) -> None:
        result = _run(precurated_store, "--adopt")
        assert result.exit_code == 0
        assert "adopted" in result.output.lower() or "registered" in result.output.lower()

    def test_init_adopt_on_missing_memory_errors(self, tmp_path: Path) -> None:
        result = _run(tmp_path, "--adopt")
        assert result.exit_code != 0
        assert "no .memory/" in result.output.lower() or "not a spec" in result.output.lower()

    def test_init_force_still_overwrites(self, precurated_store: Path) -> None:
        result = _run(precurated_store, "--force")
        assert result.exit_code == 0
        text = (precurated_store / ".memory" / "MEMORY.md").read_text(
            encoding="utf-8"
        )
        # --force regenerates the skeleton, so the hand-curated line is gone
        assert "Hand-curated identity line" not in text

    def test_init_json_output_reports_adopt_counts(
        self, precurated_store: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--dir", str(precurated_store), "init", "--adopt"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload.get("adopted") is True
        assert payload.get("registered") == 1
        assert payload.get("skipped") == 0
