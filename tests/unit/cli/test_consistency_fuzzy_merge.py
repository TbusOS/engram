"""T-189 tests — Phase 2 detector emits MERGE proposals for fuzzy
near-duplicate bodies (Jaccard shingle similarity ≥ 0.85).

Today's exact-byte-hash detector misses the common case where two assets
say the same thing with minor wording differences. Per master plan
``2026-04-25-越用越好用-12周主线.md`` Week 8: this is what makes wisdom
curve C5 (redundancy) actually move.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from engram.commands.init import init_project
from engram.consistency.engine import run_consistency_scan
from engram.consistency.phase2_semantic import detect_phase2
from engram.consistency.types import ConflictClass, ResolutionKind


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    init_project(tmp_path)
    yield tmp_path


def _write_asset(project: Path, name: str, body: str, type_: str = "project") -> None:
    file = project / ".memory" / "local" / f"{type_}_{name}.md"
    fm = (
        f"---\n"
        f"name: {name.replace('_', ' ')}\n"
        f"description: test asset\n"
        f"type: {type_}\n"
        f"scope: project\n"
        f"created: 2026-04-25\n"
        f"---\n\n{body}\n"
    )
    file.write_text(fm, encoding="utf-8")


# ------------------------------------------------------------------
# Fuzzy MERGE detection
# ------------------------------------------------------------------


class TestFuzzyMerge:
    def test_byte_identical_still_merges(self, project: Path) -> None:
        body = "always rebase before merge to keep history linear and clean"
        _write_asset(project, "rebase_a", body)
        _write_asset(project, "rebase_b", body)
        reports = detect_phase2(project)
        merges = [r for r in reports if any(p.kind is ResolutionKind.MERGE for p in r.proposed)]
        assert merges, "byte-identical bodies must still produce MERGE"

    def test_high_similarity_emits_merge(self, project: Path) -> None:
        # Two near-duplicates: long identical body + 1 trailing word added
        # to body_b (≥ 0.85 Jaccard on 3-word shingles).
        common = (
            "Always rebase before merge to keep history linear. "
            "Never push directly to the main branch. "
            "Tag releases with semantic version numbers. "
            "Run pytest before opening any pull request. "
            "Rotate API keys every ninety days for security purposes. "
            "Document every public function with one-line docstrings. "
            "Lint with ruff and format with black on every commit."
        )
        body_a = common
        body_b = common + " Always."
        _write_asset(project, "rules_a", body_a)
        _write_asset(project, "rules_b", body_b)
        reports = detect_phase2(project)
        merges = [
            r
            for r in reports
            if r.conflict_class is ConflictClass.FACTUAL
            and any(p.kind is ResolutionKind.MERGE for p in r.proposed)
        ]
        assert merges, "near-duplicates (Jaccard ≥ 0.85) must emit MERGE"
        # Message must call out fuzzy similarity (so reviewer knows it
        # is not a byte-identical match)
        assert any(
            "similar" in r.message.lower() or "%" in r.message for r in merges
        )

    def test_low_similarity_does_not_emit(self, project: Path) -> None:
        _write_asset(
            project, "topic_a",
            "Use rebase to flatten feature branch history before merging upstream",
        )
        _write_asset(
            project, "topic_b",
            "Configure pre-commit hooks to run linters on every staged change",
        )
        reports = detect_phase2(project)
        # Two unrelated bodies must not produce a MERGE proposal
        merges = [
            r
            for r in reports
            if any(p.kind is ResolutionKind.MERGE for p in r.proposed)
        ]
        assert not merges

    def test_three_way_fuzzy_yields_pairs_not_explosion(self, project: Path) -> None:
        # 3 highly similar assets — must produce at most 3 pair reports
        # (3 choose 2), not explode quadratically with weird cross-products
        body = (
            "Always rebase before merge to keep history linear. "
            "Never push directly to the main branch. "
            "Tag releases with semantic version numbers."
        )
        for tag in ("a", "b", "c"):
            _write_asset(project, f"rules_{tag}", body + f" Variant {tag}.")
        reports = detect_phase2(project)
        merges = [
            r
            for r in reports
            if any(p.kind is ResolutionKind.MERGE for p in r.proposed)
        ]
        # At most 3 pairs (a-b, a-c, b-c). The exact-hash path may collapse
        # to chain reporting only one duplicate per second-occurrence; with
        # fuzzy we expect the pair reports.
        assert 1 <= len(merges) <= 3


# ------------------------------------------------------------------
# Engine integration — run_consistency_scan must surface MERGE
# ------------------------------------------------------------------


class TestEngineSurfacesMerge:
    def test_scan_includes_fuzzy_merges(self, project: Path) -> None:
        common = (
            "Always rebase before merge to keep history linear. "
            "Never push directly to the main branch. "
            "Tag releases with semantic version numbers. "
            "Run pytest before opening any pull request. "
            "Rotate API keys every ninety days for security purposes."
        )
        body_a = common
        body_b = common + " Always."
        _write_asset(project, "rules_a", body_a)
        _write_asset(project, "rules_b", body_b)

        report = run_consistency_scan(project)
        merge_conflicts = [
            c
            for c in report.conflicts
            if any(p.kind is ResolutionKind.MERGE for p in c.proposed)
        ]
        assert merge_conflicts, (
            "run_consistency_scan must surface fuzzy MERGE proposals "
            "from Phase 2 — currently sees no MERGE conflicts at all"
        )
