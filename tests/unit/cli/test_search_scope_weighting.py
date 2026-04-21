"""T-38 tests: scope + enforcement weighting in ``engram memory search``.

SPEC context:

- **Scope weighting** (DESIGN §5.1 Stage 6): project=1.5, user=1.2, team=1.0,
  org=0.8. Pool assets inherit the weight of their ``subscribed_at`` level.
- **Enforcement weighting** (M3 subset): ``mandatory`` > ``default`` > ``hint``.
  The M4 Relevance Gate will move mandatory to Stage-1 bypass; the M3 search
  subcommand folds enforcement into the final score as a multiplier so
  operators get deterministic, scope-aware ranking today.

The tests construct small fixtures where BM25 similarity is near-identical
across candidates and verify the weighting alone drives the final order.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.memory import (
    ENFORCEMENT_WEIGHTS,
    SCOPE_WEIGHTS,
    apply_scope_weighting,
)


def _seed_project(root: Path) -> None:
    init_project(root)


def _write_asset(root: Path, filename: str, body: str, **fm_extra: object) -> None:
    fm: dict[str, object] = {
        "name": fm_extra.pop("name", filename.replace(".md", "")),
        "description": fm_extra.pop("description", "asset for search ranking tests"),
        "type": fm_extra.pop("type", "feedback"),
        "scope": fm_extra.pop("scope", "project"),
    }
    # feedback requires enforcement; respect the caller's value
    fm.update(fm_extra)

    import yaml

    yaml_block = yaml.dump(fm, sort_keys=False)
    (root / ".memory" / "local" / filename).write_text(
        f"---\n{yaml_block}---\n\n{body}\n", encoding="utf-8"
    )
    # Keep MEMORY.md in sync so engram memory search (which walks graph.db)
    # still works — but we do not need E-IDX-002 clean here.


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    return fake


@pytest.fixture
def project(tmp_path: Path, home: Path) -> Path:
    root = tmp_path / "proj"
    _seed_project(root)
    return root


# ------------------------------------------------------------------
# Weight tables
# ------------------------------------------------------------------


def test_scope_weight_ordering_matches_design() -> None:
    """DESIGN §5.1 stage 6: project > user > team > org."""
    assert SCOPE_WEIGHTS["project"] > SCOPE_WEIGHTS["user"]
    assert SCOPE_WEIGHTS["user"] > SCOPE_WEIGHTS["team"]
    assert SCOPE_WEIGHTS["team"] > SCOPE_WEIGHTS["org"]
    assert SCOPE_WEIGHTS["project"] == pytest.approx(1.5)


def test_enforcement_weight_ordering_matches_t38() -> None:
    assert ENFORCEMENT_WEIGHTS["mandatory"] > ENFORCEMENT_WEIGHTS["default"]
    assert ENFORCEMENT_WEIGHTS["default"] > ENFORCEMENT_WEIGHTS["hint"]


# ------------------------------------------------------------------
# Pure function — apply_scope_weighting
# ------------------------------------------------------------------


def test_apply_scope_weighting_applies_enforcement_multiplier() -> None:
    bm25 = [("a", 1.0), ("b", 1.0), ("c", 1.0)]
    meta = {
        "a": ("project", "mandatory", None),
        "b": ("project", "default", None),
        "c": ("project", "hint", None),
    }
    ranked = apply_scope_weighting(bm25, meta)
    # Tied BM25 → order by enforcement weight only.
    assert [r[0] for r in ranked] == ["a", "b", "c"]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]


def test_apply_scope_weighting_applies_scope_multiplier() -> None:
    bm25 = [("p", 1.0), ("u", 1.0), ("t", 1.0), ("o", 1.0)]
    meta = {
        "p": ("project", "default", None),
        "u": ("user", "default", None),
        "t": ("team", "default", None),
        "o": ("org", "default", None),
    }
    ranked = apply_scope_weighting(bm25, meta)
    assert [r[0] for r in ranked] == ["p", "u", "t", "o"]


def test_apply_scope_weighting_pool_uses_subscribed_at() -> None:
    """A pool asset subscribed at team level ranks like a team asset."""
    bm25 = [("pool_team", 1.0), ("project_asset", 1.0)]
    meta = {
        "pool_team": ("pool", "default", "team"),
        "project_asset": ("project", "default", None),
    }
    ranked = apply_scope_weighting(bm25, meta)
    # project (1.5) > team-subscribed pool (1.0)
    assert ranked[0][0] == "project_asset"


def test_apply_scope_weighting_pool_without_subscribed_at_defaults_to_pool() -> None:
    bm25 = [("orphan", 1.0)]
    meta = {"orphan": ("pool", "default", None)}
    ranked = apply_scope_weighting(bm25, meta)
    # Not missing from output; degrades gracefully with the pool baseline weight.
    assert ranked == [("orphan", pytest.approx(SCOPE_WEIGHTS["pool"]))]


def test_apply_scope_weighting_combined_scope_and_enforcement() -> None:
    """Scope and enforcement multiply together (both tags matter)."""
    bm25 = [("p_hint", 1.0), ("o_mand", 1.0)]
    meta = {
        "p_hint": ("project", "hint", None),
        "o_mand": ("org", "mandatory", None),
    }
    ranked = apply_scope_weighting(bm25, meta)
    # org*mandatory = 0.8 * 2.0 = 1.6 > project*hint = 1.5 * 0.5 = 0.75
    assert ranked[0][0] == "o_mand"


def test_apply_scope_weighting_unknown_scope_or_enforcement_uses_1() -> None:
    bm25 = [("weird", 2.0)]
    meta = {"weird": ("unknown-scope", "unknown-enforcement", None)}
    ranked = apply_scope_weighting(bm25, meta)
    # Neutral multipliers of 1.0 → raw BM25 preserved.
    assert ranked == [("weird", pytest.approx(2.0))]


# ------------------------------------------------------------------
# End-to-end via `engram memory search`
# ------------------------------------------------------------------


def test_search_cli_mandatory_outranks_hint_on_identical_text(
    project: Path,
) -> None:
    """Two assets with identical queryable text — enforcement tie-breaks."""
    # Both mention "alpha beta" in the description + body.
    _write_asset(
        project,
        "feedback_alpha_mandatory.md",
        "Why: reasoning about alpha beta.\n\n"
        "**Why:** one.\n\n**How to apply:** here.\n",
        name="alpha mandatory",
        description="alpha beta hint",
        enforcement="mandatory",
    )
    _write_asset(
        project,
        "feedback_alpha_hint.md",
        "Why: reasoning about alpha beta.\n\n"
        "**Why:** one.\n\n**How to apply:** here.\n",
        name="alpha hint",
        description="alpha beta hint",
        enforcement="hint",
    )

    runner = CliRunner()
    # First populate graph.db by adding via CLI; but the assets were written
    # manually. Use `engram memory list` indirectly? The search_cmd reads
    # graph.db, so we need entries there. Register them by running `list`?
    # Simpler: the M2 search walks `graph.db` which is only populated by
    # `engram memory add`. For this test we run add via CLI with enforcement
    # flags so the DB is seeded.
    #
    # Replace the manual _write_asset calls with CLI-driven adds:
    (project / ".memory" / "local" / "feedback_alpha_mandatory.md").unlink()
    (project / ".memory" / "local" / "feedback_alpha_hint.md").unlink()

    for enforcement in ("mandatory", "hint"):
        result = runner.invoke(
            cli,
            [
                "--dir",
                str(project),
                "memory",
                "add",
                "--type",
                "feedback",
                "--name",
                f"alpha {enforcement}",
                "--description",
                "alpha beta ranking test fixture",
                "--enforcement",
                enforcement,
                "--body",
                "alpha beta match fodder.\n\n**Why:** x\n\n**How to apply:** y",
            ],
        )
        assert result.exit_code == 0, result.output

    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "memory",
            "search",
            "alpha beta",
        ],
    )
    assert result.exit_code == 0, result.output
    ranked = json.loads(result.output)
    assert len(ranked) >= 2
    # mandatory must outrank hint when BM25 is equal.
    top_id = ranked[0]["id"]
    second_id = ranked[1]["id"]
    assert "mandatory" in top_id, f"expected mandatory on top, got {top_id}"
    assert "hint" in second_id, f"expected hint second, got {second_id}"
    # JSON payload must expose scope + enforcement for observability.
    assert "scope" in ranked[0]
    assert "enforcement" in ranked[0]
    assert ranked[0]["enforcement"] == "mandatory"


def test_search_cli_exposes_weighted_score(project: Path) -> None:
    runner = CliRunner()
    _invoke = lambda *args: runner.invoke(cli, list(args))  # noqa: E731
    result = _invoke(
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        "feedback",
        "--name",
        "kernel pref",
        "--description",
        "kernel memory alignment alpha",
        "--enforcement",
        "mandatory",
        "--body",
        "body.\n\n**Why:** a\n\n**How to apply:** b",
    )
    assert result.exit_code == 0, result.output

    result = _invoke(
        "--format", "json", "--dir", str(project), "memory", "search", "kernel"
    )
    ranked = json.loads(result.output)
    hit = ranked[0]
    # Weighted score is the BM25 score × scope × enforcement. Mandatory = 2.0,
    # project scope = 1.5, so weighted must be 3.0 × raw.
    assert "score" in hit
    assert "raw_score" in hit, "payload must expose unweighted BM25 for debugging"
    assert hit["score"] > hit["raw_score"]
    assert hit["score"] == pytest.approx(
        hit["raw_score"] * SCOPE_WEIGHTS["project"] * ENFORCEMENT_WEIGHTS["mandatory"],
        rel=1e-4,
    )


def test_search_cli_zero_match_returns_empty(project: Path) -> None:
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
            "operator",
            "--description",
            "alpha beta content",
            "--body",
            "body",
        ],
    )
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "memory",
            "search",
            "xylophone-never-in-corpus",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == []
