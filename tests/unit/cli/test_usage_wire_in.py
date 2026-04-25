"""T-171 integration tests: ``engram context pack`` and ``engram consistency
apply`` MUST emit usage events into ``~/.engram/journal/usage.jsonl``.

These guard the wiring between the user-facing commands and the usage bus
(T-170). Without them, the bus is built but unfed, and the wisdom curves
(C1-C6) have no data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.consistency.resolve import apply_resolution
from engram.consistency.types import Resolution, ResolutionKind
from engram.usage import EventType, EvidenceKind, iter_events


@pytest.fixture
def isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Sandbox HOME + ENGRAM_DIR so usage.jsonl writes are scoped to test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENGRAM_DIR", str(home / ".engram"))
    project = tmp_path / "proj"
    init_project(project)
    yield project


def _quick_add(project: Path, body: str) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "memory", "quick", body],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output


# ------------------------------------------------------------------
# context pack → loaded_only events
# ------------------------------------------------------------------


class TestContextPackEmitsLoadedEvents:
    def test_loaded_event_per_included_asset(self, isolated: Path) -> None:
        _quick_add(isolated, "kinit before ssh to build.acme.internal")
        _quick_add(isolated, "always rebase before merge")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dir", str(isolated), "context", "pack", "--task=ssh build", "--budget=4000"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output

        events = list(iter_events(event_type=EventType.LOADED))
        assert events, "context pack should emit at least one loaded event"
        assert all(e.evidence_kind is EvidenceKind.LOADED_ONLY for e in events)
        # All loaded events for one task share a task_hash
        assert len({e.task_hash for e in events}) == 1

    def test_co_assets_recorded_when_multiple_loaded(self, isolated: Path) -> None:
        for body in (
            "kinit before ssh to build.acme.internal",
            "kinit before ssh to other host kinit",
            "kinit ticket lifecycle and renewal kinit",
        ):
            _quick_add(isolated, body)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dir", str(isolated), "context", "pack", "--task=kinit", "--budget=8000"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output

        events = list(iter_events(event_type=EventType.LOADED))
        # When more than one asset is loaded, every event MUST list the
        # other assets in co_assets so confidence derivation can attribute
        # task-success heuristics proportionally
        if len(events) >= 2:
            for ev in events:
                assert ev.co_assets, (
                    f"event for {ev.asset_uri} has empty co_assets but "
                    f"{len(events)} assets were loaded together"
                )
                assert ev.asset_uri not in ev.co_assets


# ------------------------------------------------------------------
# consistency apply (dismiss) → false_positive_dismissed event
# ------------------------------------------------------------------


class TestConsistencyDismissEmitsEvent:
    def test_dismiss_emits_false_positive_dismissed(self, isolated: Path) -> None:
        _quick_add(isolated, "the asset getting dismissed")
        # Asset id that exists per memory_quick id rule:
        # local/<type>_<slug> with type=project + body slugified
        target = "local/project_the_asset_getting_dismissed"
        resolution = Resolution(
            kind=ResolutionKind.DISMISS,
            target=target,
            related=(),
            detail="false positive — both rules are correct in their own scope",
        )
        result = apply_resolution(isolated, resolution, consent=True)
        assert result.applied

        events = list(iter_events(asset_uri=target))
        kinds = [e.evidence_kind for e in events]
        assert EvidenceKind.FALSE_POSITIVE_DISMISSED in kinds
