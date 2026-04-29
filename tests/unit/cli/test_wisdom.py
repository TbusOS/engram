"""T-188 tests for ``engram wisdom report`` — 6 wisdom curves rendered as
ASCII sparklines.

The 6 curves(per master plan
``docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md``):

- C1 retrieval_hit_rate     — validated / loaded ratio per day
- C2 task_recurrence        — distinct tasks seen N+ times
- C3 write_friction         — average asset add path (proxy: assets/day)
- C4 mandatory_false_pos    — overrides on mandatory / loads on mandatory
- C5 redundancy             — merge proposals / total assets
- C6 confidence_calibration — average per-asset signal-to-exposure

Each curve must:
- handle empty data gracefully(``insufficient data``)
- render a sparkline when ≥1 sample exists
- expose the raw samples + a one-line summary
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.usage import (
    ActorType,
    EventType,
    EvidenceKind,
    UsageEvent,
    append_usage_event,
)
from engram.wisdom import (
    Curve,
    Sample,
    WisdomReport,
    compute_wisdom_report,
)
from engram.wisdom.ascii_render import render_text


@pytest.fixture
def isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENGRAM_DIR", str(home / ".engram"))
    project = tmp_path / "proj"
    init_project(project)
    yield project


def _emit(asset: str, kind: EvidenceKind, days_ago: int = 0) -> None:
    ts = (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).isoformat(
        timespec="seconds"
    )
    append_usage_event(
        UsageEvent(
            asset_uri=asset,
            task_hash=f"task-{asset}-{days_ago}",
            event_type=(
                EventType.LOADED
                if kind is EvidenceKind.LOADED_ONLY
                else EventType.VALIDATED
                if kind in (
                    EvidenceKind.EXPLICIT_USER_CONFIRMATION,
                    EvidenceKind.WORKFLOW_FIXTURE_PASS,
                    EvidenceKind.TASK_SUCCESS_HEURISTIC,
                    EvidenceKind.FALSE_POSITIVE_DISMISSED,
                )
                else EventType.CONTRADICTED
            ),
            actor_type=ActorType.LLM,
            evidence_kind=kind,
            timestamp=ts,
        )
    )


# ------------------------------------------------------------------
# Report shape
# ------------------------------------------------------------------


class TestReportShape:
    def test_empty_store_returns_eight_curves_all_insufficient(
        self, isolated: Path
    ) -> None:
        report = compute_wisdom_report(isolated, days=7)
        assert isinstance(report, WisdomReport)
        assert len(report.curves) == 8
        ids = {c.id for c in report.curves}
        assert ids == {"C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"}
        # All curves should declare insufficient data with no events
        for curve in report.curves:
            assert curve.summary  # always non-empty
            # Empty data → no samples or one-sample-zero
            assert curve.insufficient or curve.samples == ()

    def test_curve_dataclass_fields(self, isolated: Path) -> None:
        report = compute_wisdom_report(isolated, days=7)
        c1 = next(c for c in report.curves if c.id == "C1")
        assert c1.name
        assert isinstance(c1.samples, tuple)
        assert isinstance(c1.summary, str)


# ------------------------------------------------------------------
# Curve C1 — retrieval hit rate
# ------------------------------------------------------------------


class TestC1HitRate:
    def test_only_loaded_events_yields_zero_hit_rate(
        self, isolated: Path
    ) -> None:
        for _ in range(5):
            _emit("local/a", EvidenceKind.LOADED_ONLY)
        report = compute_wisdom_report(isolated, days=7)
        c1 = next(c for c in report.curves if c.id == "C1")
        assert not c1.insufficient
        # 5 loaded, 0 validated → hit rate 0
        assert c1.samples[-1].value == 0.0

    def test_validated_events_increase_hit_rate(self, isolated: Path) -> None:
        for _ in range(2):
            _emit("local/a", EvidenceKind.LOADED_ONLY)
        for _ in range(3):
            _emit("local/a", EvidenceKind.EXPLICIT_USER_CONFIRMATION)
        report = compute_wisdom_report(isolated, days=7)
        c1 = next(c for c in report.curves if c.id == "C1")
        assert c1.samples[-1].value > 0.0


# ------------------------------------------------------------------
# Curve C6 — confidence calibration
# ------------------------------------------------------------------


class TestC6Calibration:
    def test_signal_present_when_any_validated(self, isolated: Path) -> None:
        _emit("local/x", EvidenceKind.EXPLICIT_USER_CONFIRMATION)
        _emit("local/x", EvidenceKind.LOADED_ONLY)
        report = compute_wisdom_report(isolated, days=7)
        c6 = next(c for c in report.curves if c.id == "C6")
        # average per-asset (validated - contradicted) / exposure
        # x has +1.0 validated, exposure 2 → 0.5
        assert not c6.insufficient
        assert c6.samples[-1].value > 0


# ------------------------------------------------------------------
# ASCII renderer
# ------------------------------------------------------------------


class TestAsciiRender:
    def test_renders_six_curve_lines(self, isolated: Path) -> None:
        for kind in (
            EvidenceKind.LOADED_ONLY,
            EvidenceKind.EXPLICIT_USER_CONFIRMATION,
        ):
            _emit("local/a", kind)
        report = compute_wisdom_report(isolated, days=7)
        text = render_text(report)
        # Each curve rendered on its own line with id + name
        for curve_id in ("C1", "C2", "C3", "C4", "C5", "C6"):
            assert curve_id in text
        # Header banner
        assert "WISDOM" in text.upper() or "wisdom" in text

    def test_sparkline_uses_unicode_blocks_when_data_present(
        self, isolated: Path
    ) -> None:
        for d in range(7):
            _emit("local/a", EvidenceKind.LOADED_ONLY, days_ago=d)
            _emit("local/a", EvidenceKind.EXPLICIT_USER_CONFIRMATION, days_ago=d)
        report = compute_wisdom_report(isolated, days=7)
        text = render_text(report)
        # At least one of the unicode block characters must appear
        assert any(ch in text for ch in "▁▂▃▄▅▆▇█")

    def test_insufficient_curves_say_so(self, isolated: Path) -> None:
        report = compute_wisdom_report(isolated, days=7)
        text = render_text(report)
        assert "insufficient" in text.lower() or "no data" in text.lower()


# ------------------------------------------------------------------
# CLI surface
# ------------------------------------------------------------------


class TestWisdomCli:
    def test_clean_invocation_exits_zero(self, isolated: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--dir", str(isolated), "wisdom", "report"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "C1" in result.output

    def test_json_output(self, isolated: Path) -> None:
        _emit("local/a", EvidenceKind.LOADED_ONLY)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--dir", str(isolated), "wisdom", "report"],
            catch_exceptions=False,
        )
        import json

        payload = json.loads(result.output)
        assert "curves" in payload
        assert len(payload["curves"]) == 8

    def test_days_flag(self, isolated: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dir", str(isolated), "wisdom", "report", "--days=14"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
