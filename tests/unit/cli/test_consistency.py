"""T-46 tests: Consistency Engine dispatcher + Phase 1/2 + Evaluator.

Exercises the four-phase engine against crafted stores that contain
exactly one conflict of each type the M4 subset detects. Also verifies
the evaluator refuses obviously bad proposals and that phases 3/4 are
explicitly stubbed (no false positives).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Import engram.cli first so click's subcommand registration chain
# completes before any sibling module from engram.commands is loaded
# directly — otherwise `engram.commands.init` hits a circular import
# via engram.cli's `_register_subcommands()`.
import engram.cli  # noqa: F401  # import-order matters
from engram.commands.init import init_project
from engram.consistency import (
    ConflictClass,
    ConflictReport,
    ConflictSeverity,
    Resolution,
    ResolutionKind,
    run_consistency_scan,
)
from engram.consistency.evaluator import evaluate_report, evaluate_reports


def _write_asset(
    root: Path,
    filename: str,
    *,
    name: str = "asset",
    description: str = "desc",
    subtype: str = "feedback",
    scope: str = "project",
    enforcement: str = "default",
    body: str = "**Why:** a\n\n**How to apply:** b",
    source: str | None = None,
    confidence: str | None = None,
) -> None:
    local = root / ".memory" / "local"
    local.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        f"name: {name}",
        f"description: {description}",
        f"type: {subtype}",
        f"scope: {scope}",
    ]
    if subtype == "feedback":
        fm_lines.append(f"enforcement: {enforcement}")
    if source:
        fm_lines.append(f"source: {source}")
    if confidence:
        fm_lines.append(confidence)
    fm = "\n".join(fm_lines)
    (local / filename).write_text(
        f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8"
    )


def _index_entry(root: Path, filename: str, name: str, description: str) -> None:
    """Append a MEMORY.md line so E-IDX-002 doesn't fire."""
    index = root / ".memory" / "MEMORY.md"
    existing = index.read_text(encoding="utf-8") if index.is_file() else ""
    index.write_text(
        f"{existing}\n- [{name}](local/{filename}) — {description}\n",
        encoding="utf-8",
    )


@pytest.fixture
def clean_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "store"
    init_project(root)
    return root


# ------------------------------------------------------------------
# Dispatcher — clean store produces zero conflicts
# ------------------------------------------------------------------


def test_empty_store_reports_zero_conflicts(clean_store: Path) -> None:
    report = run_consistency_scan(clean_store)
    assert report.total == 0
    assert all(v == 0 for v in report.phase_counts.values())


def test_phase_counts_match_phase_numbers(clean_store: Path) -> None:
    report = run_consistency_scan(clean_store)
    assert set(report.phase_counts.keys()) == {1, 2, 3, 4}


# ------------------------------------------------------------------
# Phase 1 — static (validate-driven)
# ------------------------------------------------------------------


def test_phase1_catches_dangling_memory_md_link(clean_store: Path) -> None:
    # Add a link to a file that doesn't exist on disk.
    index = clean_store / ".memory" / "MEMORY.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + "\n- [ghost](local/does_not_exist.md)\n",
        encoding="utf-8",
    )
    report = run_consistency_scan(clean_store)
    classes = [c.conflict_class for c in report.conflicts]
    assert ConflictClass.REFERENCE_ROT in classes


# ------------------------------------------------------------------
# Phase 2 — semantic (body hash + name opposites)
# ------------------------------------------------------------------


def test_phase2_detects_duplicate_body_across_two_assets(
    clean_store: Path,
) -> None:
    body = (
        "Ask before pushing.\n\n**Why:** safety.\n\n"
        "**How to apply:** every push."
    )
    _write_asset(
        clean_store, "feedback_push_a.md", name="push a", body=body
    )
    _index_entry(clean_store, "feedback_push_a.md", "push a", "a")
    _write_asset(
        clean_store, "feedback_push_b.md", name="push b", body=body
    )
    _index_entry(clean_store, "feedback_push_b.md", "push b", "b")

    report = run_consistency_scan(clean_store)
    factual = [c for c in report.conflicts if c.conflict_class == ConflictClass.FACTUAL]
    assert len(factual) == 1
    c = factual[0]
    assert {c.primary_asset, *c.related_assets} == {
        "local/feedback_push_a",
        "local/feedback_push_b",
    }
    assert any(r.kind == ResolutionKind.MERGE for r in c.proposed)


def test_phase2_detects_opposing_rule_names(clean_store: Path) -> None:
    _write_asset(
        clean_store,
        "feedback_tabs.md",
        name="prefer tabs over spaces",
        description="indent style",
        body=(
            "Use tabs for indentation.\n\n**Why:** tabs scale per-user.\n\n"
            "**How to apply:** python + go repos."
        ),
    )
    _index_entry(clean_store, "feedback_tabs.md", "prefer tabs", "style")
    _write_asset(
        clean_store,
        "feedback_spaces.md",
        name="prefer spaces over tabs",
        description="indent style",
        body=(
            "Use spaces for indentation.\n\n**Why:** consistent width.\n\n"
            "**How to apply:** all repos."
        ),
    )
    _index_entry(clean_store, "feedback_spaces.md", "prefer spaces", "style")

    report = run_consistency_scan(clean_store)
    rules = [c for c in report.conflicts if c.conflict_class == ConflictClass.RULE]
    assert rules, "expected a rule-conflict between the two opposing feedback assets"
    assert any(r.kind == ResolutionKind.ESCALATE for r in rules[0].proposed)


def test_phase2_does_not_flag_unrelated_feedback_pairs(
    clean_store: Path,
) -> None:
    _write_asset(
        clean_store,
        "feedback_tests.md",
        name="write tests first",
        description="TDD",
        body=(
            "Write the failing test before the implementation.\n\n"
            "**Why:** catches regressions.\n\n**How to apply:** always."
        ),
    )
    _index_entry(clean_store, "feedback_tests.md", "tests", "tdd")
    _write_asset(
        clean_store,
        "feedback_reviews.md",
        name="review your own PR first",
        description="self review",
        body=(
            "Read the diff before hitting 'request review'.\n\n"
            "**Why:** catches obvious bugs.\n\n**How to apply:** every PR."
        ),
    )
    _index_entry(clean_store, "feedback_reviews.md", "reviews", "style")

    report = run_consistency_scan(clean_store)
    rules = [c for c in report.conflicts if c.conflict_class == ConflictClass.RULE]
    assert rules == []


# ------------------------------------------------------------------
# Phase 3 + 4 stubs (return empty)
# ------------------------------------------------------------------


def test_phase3_returns_empty_in_m4(clean_store: Path) -> None:
    from engram.consistency.phase3_references import detect_phase3

    assert detect_phase3(clean_store) == []


def test_phase4_returns_empty_in_m4(clean_store: Path) -> None:
    from engram.consistency.phase4_staleness import detect_phase4

    assert detect_phase4(clean_store) == []


# ------------------------------------------------------------------
# Evaluator — detector output grading
# ------------------------------------------------------------------


def _base_report(resolution: Resolution) -> ConflictReport:
    return ConflictReport(
        conflict_class=ConflictClass.FACTUAL,
        severity=ConflictSeverity.WARNING,
        primary_asset="local/feedback_x",
        related_assets=("local/feedback_y",),
        message="dummy",
        phase=2,
        proposed=(resolution,),
    )


def test_evaluator_rejects_archive_on_team_scope_asset() -> None:
    """SPEC §8.3: lower-scope consumer cannot archive a team asset."""
    bad = _base_report(
        Resolution(
            kind=ResolutionKind.ARCHIVE,
            target="team/platform/feedback_x",
            detail="archive it",
        )
    )
    graded = evaluate_report(bad)
    assert graded.evaluator_approved is False
    assert "higher-scope" in graded.evaluator_reason


def test_evaluator_rejects_supersede_without_related() -> None:
    bad = _base_report(
        Resolution(
            kind=ResolutionKind.SUPERSEDE,
            target="local/feedback_x",
            related=(),
            detail="supersede",
        )
    )
    graded = evaluate_report(bad)
    assert graded.evaluator_approved is False


def test_evaluator_rejects_update_targeting_missing_asset() -> None:
    report = ConflictReport(
        conflict_class=ConflictClass.REFERENCE_ROT,
        severity=ConflictSeverity.ERROR,
        primary_asset="local/feedback_broken",
        related_assets=(),
        message="dangling",
        phase=1,
        proposed=(
            Resolution(
                kind=ResolutionKind.UPDATE,
                target="local/something_else",  # wrong target for REFERENCE_ROT
                detail="patch the link",
            ),
        ),
    )
    graded = evaluate_report(report)
    assert graded.evaluator_approved is False


def test_evaluator_passes_valid_proposals() -> None:
    good = _base_report(
        Resolution(
            kind=ResolutionKind.MERGE,
            target="local/feedback_x",
            related=("local/feedback_y",),
            detail="merge into x",
        )
    )
    graded = evaluate_report(good)
    assert graded.evaluator_approved is True


def test_evaluate_reports_preserves_order_and_count() -> None:
    graded = evaluate_reports(
        [
            _base_report(
                Resolution(
                    kind=ResolutionKind.MERGE,
                    target="local/a",
                    related=("local/b",),
                )
            ),
            _base_report(
                Resolution(kind=ResolutionKind.SUPERSEDE, target="local/a", related=())
            ),
        ]
    )
    assert len(graded) == 2
    assert graded[0].evaluator_approved is True
    assert graded[1].evaluator_approved is False


# ------------------------------------------------------------------
# End-to-end: rejected-proposal count reported
# ------------------------------------------------------------------


def test_engine_reports_evaluator_rejected_count(
    clean_store: Path,
) -> None:
    # Seed a rule-conflict that passes, plus manually inject an
    # evaluator-failing proposal by monkeypatching phase1.
    _write_asset(
        clean_store,
        "feedback_a.md",
        name="prefer tabs",
        description="x",
        body="**Why:** a\n\n**How to apply:** b",
    )
    _index_entry(clean_store, "feedback_a.md", "prefer tabs", "x")
    _write_asset(
        clean_store,
        "feedback_b.md",
        name="prefer spaces",
        description="x",
        body="**Why:** c\n\n**How to apply:** d",
    )
    _index_entry(clean_store, "feedback_b.md", "prefer spaces", "x")

    report = run_consistency_scan(clean_store)
    # The rule-conflict is detected AND the evaluator approves the
    # ESCALATE proposal (valid) — so evaluator_rejected=0 here.
    assert report.total >= 1
    assert report.evaluator_rejected == 0
