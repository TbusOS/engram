"""T-170 tests for ``engram/usage/`` — append-only event bus that feeds
confidence + 6 wisdom curves.

Per docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md week 2:
the usage bus is the **single data spine** for the entire learning
neural system. Issue #9's confidence-as-derived-cache model rides on top.

Schema (one event = one JSON object in
``~/.engram/journal/usage.jsonl``):

  asset_uri      str       canonical URI (T-180) or local id (M5 fallback)
  task_hash      str       opaque correlation key for one task / session
  event_type     enum      loaded | validated | contradicted
  actor_type     enum      human | llm | workflow | consistency_engine
  evidence_kind  enum      8 kinds (see trust_weights table)
  trust_weight   float     defaults from evidence_kind, override allowed
  co_assets      list[str] sibling assets loaded for the same task_hash
  timestamp      str       ISO-8601
  session_id     str|None
  model_id       str|None
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from engram.usage import (
    ActorType,
    EventType,
    EvidenceKind,
    UsageEvent,
    append_usage_event,
    derive_confidence_cache,
    iter_events,
)
from engram.usage.trust_weights import DEFAULT_TRUST_WEIGHTS


@pytest.fixture
def isolated_engram_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Sandbox ``~/.engram/`` so writes do not touch the real home dir."""
    home = tmp_path / "fake_home"
    home.mkdir()
    monkeypatch.setenv("ENGRAM_DIR", str(home / ".engram"))
    monkeypatch.setenv("HOME", str(home))
    yield home / ".engram"


# ------------------------------------------------------------------
# Trust weights table — authoritative per issue #9
# ------------------------------------------------------------------


class TestTrustWeights:
    def test_all_eight_evidence_kinds_present(self) -> None:
        for kind in (
            EvidenceKind.EXPLICIT_USER_CONFIRMATION,
            EvidenceKind.EXPLICIT_USER_CORRECTION,
            EvidenceKind.WORKFLOW_FIXTURE_PASS,
            EvidenceKind.WORKFLOW_FIXTURE_FAIL,
            EvidenceKind.TASK_SUCCESS_HEURISTIC,
            EvidenceKind.TASK_FAILURE_HEURISTIC,
            EvidenceKind.FALSE_POSITIVE_DISMISSED,
            EvidenceKind.LOADED_ONLY,
        ):
            assert kind in DEFAULT_TRUST_WEIGHTS

    def test_user_signals_have_strongest_weights(self) -> None:
        # |user_confirmation| > |workflow| > |llm-self-report| > |loaded|
        user = abs(DEFAULT_TRUST_WEIGHTS[EvidenceKind.EXPLICIT_USER_CONFIRMATION])
        wf = abs(DEFAULT_TRUST_WEIGHTS[EvidenceKind.WORKFLOW_FIXTURE_PASS])
        llm = abs(DEFAULT_TRUST_WEIGHTS[EvidenceKind.TASK_SUCCESS_HEURISTIC])
        loaded = abs(DEFAULT_TRUST_WEIGHTS[EvidenceKind.LOADED_ONLY])
        assert user > wf > llm
        assert loaded == 0.0

    def test_corrections_are_negative(self) -> None:
        assert DEFAULT_TRUST_WEIGHTS[EvidenceKind.EXPLICIT_USER_CORRECTION] < 0
        assert DEFAULT_TRUST_WEIGHTS[EvidenceKind.WORKFLOW_FIXTURE_FAIL] < 0
        assert DEFAULT_TRUST_WEIGHTS[EvidenceKind.TASK_FAILURE_HEURISTIC] < 0


# ------------------------------------------------------------------
# UsageEvent dataclass
# ------------------------------------------------------------------


class TestUsageEvent:
    def test_construct_with_required_fields(self) -> None:
        ev = UsageEvent(
            asset_uri="local/feedback_x",
            task_hash="abc123",
            event_type=EventType.LOADED,
            actor_type=ActorType.LLM,
            evidence_kind=EvidenceKind.LOADED_ONLY,
        )
        assert ev.trust_weight == 0.0  # auto-default from evidence_kind
        assert ev.timestamp  # auto-stamped
        assert isinstance(ev.timestamp, str)

    def test_to_dict_roundtrip_via_json(self) -> None:
        ev = UsageEvent(
            asset_uri="local/feedback_x",
            task_hash="abc123",
            event_type=EventType.VALIDATED,
            actor_type=ActorType.HUMAN,
            evidence_kind=EvidenceKind.EXPLICIT_USER_CONFIRMATION,
            co_assets=("local/project_y",),
            session_id="s-001",
            model_id="claude-opus-4-7",
        )
        as_dict = ev.to_dict()
        # Must be JSON-serializable (no enum objects leak through)
        encoded = json.dumps(as_dict)
        decoded = json.loads(encoded)
        assert decoded["asset_uri"] == "local/feedback_x"
        assert decoded["event_type"] == "validated"
        assert decoded["evidence_kind"] == "explicit_user_confirmation"
        assert decoded["co_assets"] == ["local/project_y"]


# ------------------------------------------------------------------
# Appender / Reader
# ------------------------------------------------------------------


class TestAppendAndIter:
    def test_round_trip(self, isolated_engram_home: Path) -> None:
        ev = UsageEvent(
            asset_uri="local/feedback_x",
            task_hash="abc123",
            event_type=EventType.LOADED,
            actor_type=ActorType.LLM,
            evidence_kind=EvidenceKind.LOADED_ONLY,
        )
        append_usage_event(ev)
        events = list(iter_events())
        assert len(events) == 1
        assert events[0].asset_uri == "local/feedback_x"
        assert events[0].evidence_kind is EvidenceKind.LOADED_ONLY

    def test_filter_by_asset_uri(self, isolated_engram_home: Path) -> None:
        for uri in ("local/a", "local/b", "local/a"):
            append_usage_event(
                UsageEvent(
                    asset_uri=uri,
                    task_hash="t1",
                    event_type=EventType.LOADED,
                    actor_type=ActorType.LLM,
                    evidence_kind=EvidenceKind.LOADED_ONLY,
                )
            )
        only_a = list(iter_events(asset_uri="local/a"))
        assert len(only_a) == 2
        assert all(e.asset_uri == "local/a" for e in only_a)

    def test_filter_by_evidence_kind(self, isolated_engram_home: Path) -> None:
        append_usage_event(
            UsageEvent(
                asset_uri="local/a",
                task_hash="t1",
                event_type=EventType.LOADED,
                actor_type=ActorType.LLM,
                evidence_kind=EvidenceKind.LOADED_ONLY,
            )
        )
        append_usage_event(
            UsageEvent(
                asset_uri="local/a",
                task_hash="t1",
                event_type=EventType.VALIDATED,
                actor_type=ActorType.HUMAN,
                evidence_kind=EvidenceKind.EXPLICIT_USER_CONFIRMATION,
            )
        )
        validated = list(
            iter_events(evidence_kind=EvidenceKind.EXPLICIT_USER_CONFIRMATION)
        )
        assert len(validated) == 1


# ------------------------------------------------------------------
# Confidence derivation
# ------------------------------------------------------------------


class TestDeriveConfidence:
    def test_empty_history_returns_neutral_cache(
        self, isolated_engram_home: Path
    ) -> None:
        cache = derive_confidence_cache("local/never_loaded")
        assert cache.validated_score == 0.0
        assert cache.contradicted_score == 0.0
        assert cache.exposure_count == 0

    def test_single_user_confirmation(self, isolated_engram_home: Path) -> None:
        append_usage_event(
            UsageEvent(
                asset_uri="local/x",
                task_hash="t1",
                event_type=EventType.VALIDATED,
                actor_type=ActorType.HUMAN,
                evidence_kind=EvidenceKind.EXPLICIT_USER_CONFIRMATION,
            )
        )
        cache = derive_confidence_cache("local/x")
        assert cache.validated_score == 1.0
        assert cache.contradicted_score == 0.0
        assert cache.exposure_count == 1
        assert cache.last_validated  # ISO date string

    def test_correction_drives_contradicted_score(
        self, isolated_engram_home: Path
    ) -> None:
        append_usage_event(
            UsageEvent(
                asset_uri="local/x",
                task_hash="t1",
                event_type=EventType.CONTRADICTED,
                actor_type=ActorType.HUMAN,
                evidence_kind=EvidenceKind.EXPLICIT_USER_CORRECTION,
            )
        )
        cache = derive_confidence_cache("local/x")
        assert cache.validated_score == 0.0
        assert cache.contradicted_score == 1.0
        assert cache.exposure_count == 1

    def test_loaded_only_increases_exposure_not_correctness(
        self, isolated_engram_home: Path
    ) -> None:
        for _ in range(5):
            append_usage_event(
                UsageEvent(
                    asset_uri="local/x",
                    task_hash=f"t{_}",
                    event_type=EventType.LOADED,
                    actor_type=ActorType.LLM,
                    evidence_kind=EvidenceKind.LOADED_ONLY,
                )
            )
        cache = derive_confidence_cache("local/x")
        assert cache.exposure_count == 5
        assert cache.validated_score == 0.0
        assert cache.contradicted_score == 0.0

    def test_co_assets_split_task_success_heuristic(
        self, isolated_engram_home: Path
    ) -> None:
        # Task loaded 4 assets; LLM self-reported success → each asset
        # gets task_success_heuristic / 4
        for uri in ("local/a", "local/b", "local/c", "local/d"):
            append_usage_event(
                UsageEvent(
                    asset_uri=uri,
                    task_hash="t1",
                    event_type=EventType.VALIDATED,
                    actor_type=ActorType.LLM,
                    evidence_kind=EvidenceKind.TASK_SUCCESS_HEURISTIC,
                    co_assets=("local/a", "local/b", "local/c", "local/d"),
                )
            )
        cache = derive_confidence_cache("local/a")
        # task_success_heuristic default = 0.2; with 4 co_assets → 0.05 per asset
        expected = DEFAULT_TRUST_WEIGHTS[EvidenceKind.TASK_SUCCESS_HEURISTIC] / 4
        assert cache.validated_score == pytest.approx(expected, rel=1e-6)

    def test_user_signal_outweighs_llm_self_report(
        self, isolated_engram_home: Path
    ) -> None:
        # 5 LLM self-reports of success vs 1 human correction
        for i in range(5):
            append_usage_event(
                UsageEvent(
                    asset_uri="local/x",
                    task_hash=f"t{i}",
                    event_type=EventType.VALIDATED,
                    actor_type=ActorType.LLM,
                    evidence_kind=EvidenceKind.TASK_SUCCESS_HEURISTIC,
                )
            )
        append_usage_event(
            UsageEvent(
                asset_uri="local/x",
                task_hash="t-correction",
                event_type=EventType.CONTRADICTED,
                actor_type=ActorType.HUMAN,
                evidence_kind=EvidenceKind.EXPLICIT_USER_CORRECTION,
            )
        )
        cache = derive_confidence_cache("local/x")
        # 5 * 0.2 = 1.0 validated_score ; 1.0 contradicted_score
        # The signed net should be near-zero or negative — the user signal
        # genuinely cancels several LLM self-reports.
        net = cache.validated_score - cache.contradicted_score
        assert abs(net) <= 0.1
