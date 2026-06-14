"""Tests for Consistency Phase 3 — supersedes-graph health (T-47r)."""

from __future__ import annotations

from pathlib import Path

from engram.consistency.engine import run_consistency_scan
from engram.consistency.phase3_references import detect_phase3
from engram.consistency.types import ConflictClass


def _write(project: Path, asset_id: str, *, supersedes: str | None = None) -> None:
    """Write a minimal local memory asset; asset_id like 'project_alpha'."""
    local = project / ".memory" / "local"
    local.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {asset_id.replace('_', ' ')}",
        "description: test asset",
        "type: project",
        "scope: project",
        "created: 2026-04-25",
    ]
    if supersedes is not None:
        lines.append(f"supersedes: {supersedes}")
    lines.append("---")
    (local / f"{asset_id}.md").write_text("\n".join(lines) + "\n\nbody\n", encoding="utf-8")


def test_no_supersedes_no_reports(tmp_path: Path) -> None:
    _write(tmp_path, "project_a")
    _write(tmp_path, "project_b")
    assert detect_phase3(tmp_path) == []


def test_dangling_supersedes(tmp_path: Path) -> None:
    _write(tmp_path, "project_new", supersedes="local/project_ghost")
    reports = detect_phase3(tmp_path)
    assert len(reports) == 1
    r = reports[0]
    assert r.conflict_class == ConflictClass.REFERENCE_ROT
    assert r.primary_asset == "local/project_new"
    assert "dangling" in r.message
    assert r.phase == 3


def test_valid_supersedes_chain_is_clean(tmp_path: Path) -> None:
    # a supersedes b supersedes c — a valid linear chain, no fork/cycle.
    _write(tmp_path, "project_c")
    _write(tmp_path, "project_b", supersedes="local/project_c")
    _write(tmp_path, "project_a", supersedes="local/project_b")
    assert detect_phase3(tmp_path) == []


def test_circular_supersedes(tmp_path: Path) -> None:
    _write(tmp_path, "project_a", supersedes="local/project_b")
    _write(tmp_path, "project_b", supersedes="local/project_a")
    reports = [r for r in detect_phase3(tmp_path) if "circular" in r.message]
    assert len(reports) == 1
    assert reports[0].conflict_class == ConflictClass.REFERENCE_ROT
    assert {reports[0].primary_asset, *reports[0].related_assets} == {
        "local/project_a",
        "local/project_b",
    }


def test_self_supersede_is_a_cycle(tmp_path: Path) -> None:
    _write(tmp_path, "project_a", supersedes="local/project_a")
    reports = [r for r in detect_phase3(tmp_path) if "circular" in r.message]
    assert len(reports) == 1


def test_fork_two_supersedors(tmp_path: Path) -> None:
    _write(tmp_path, "project_target")
    _write(tmp_path, "project_x", supersedes="local/project_target")
    _write(tmp_path, "project_y", supersedes="local/project_target")
    forks = [r for r in detect_phase3(tmp_path) if r.conflict_class == ConflictClass.SILENT_OVERRIDE]
    assert len(forks) == 1
    assert forks[0].primary_asset == "local/project_x"
    assert "local/project_y" in forks[0].related_assets
    assert "local/project_target" in forks[0].related_assets


def test_phase3_wired_into_engine(tmp_path: Path) -> None:
    # init a graph.db so the full scan runs (engine runs all phases).
    from engram.commands.init import init_project

    init_project(tmp_path, name="t")
    _write(tmp_path, "project_new", supersedes="local/project_ghost")
    report = run_consistency_scan(tmp_path)
    assert report.phase_counts.get(3, 0) >= 1


def test_circular_reported_once(tmp_path: Path) -> None:
    # A 3-cycle must surface exactly one circular report, not three.
    _write(tmp_path, "project_a", supersedes="local/project_b")
    _write(tmp_path, "project_b", supersedes="local/project_c")
    _write(tmp_path, "project_c", supersedes="local/project_a")
    circs = [r for r in detect_phase3(tmp_path) if "circular" in r.message]
    assert len(circs) == 1
