"""T-211 tests for engram.observer.decay — confidence-driven Session TTL."""

from __future__ import annotations

from datetime import date, datetime, timezone

from engram.observer.decay import (
    DEFAULT_BASE_TTL_DAYS,
    MIN_TTL_DAYS,
    DecayDecision,
    compute_effective_ttl_days,
    decide_decay,
)
from engram.observer.session import SessionConfidence, SessionFrontmatter


def _fm(
    *,
    sid: str = "abc",
    started: datetime | None = None,
    ended: datetime | None = None,
    outcome: str = "completed",
    exposure_count: int = 0,
    contradicted_score: float = 0.0,
) -> SessionFrontmatter:
    if started is None:
        started = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    if ended is None:
        ended = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
    return SessionFrontmatter(
        type="session",
        session_id=sid,
        client="claude-code",
        started_at=started,
        ended_at=ended,
        outcome=outcome,
        confidence=SessionConfidence(
            exposure_count=exposure_count,
            contradicted_score=contradicted_score,
        ),
    )


# ----------------------------------------------------------------------
# compute_effective_ttl_days
# ----------------------------------------------------------------------


def test_default_ttl_is_base() -> None:
    fm = _fm()
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS


def test_exposure_adds_bonus_days() -> None:
    fm = _fm(exposure_count=4)
    # 4 hits * 3 days = +12 days
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS + 12


def test_exposure_bonus_caps_at_60() -> None:
    fm = _fm(exposure_count=100)  # would be +300
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS + 60


def test_contradicted_subtracts_days() -> None:
    fm = _fm(contradicted_score=2.0)
    # -10 days
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS - 10


def test_abandoned_subtracts_days() -> None:
    fm = _fm(outcome="abandoned")
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS - 14


def test_min_floor_protects_from_excess_penalty() -> None:
    fm = _fm(outcome="abandoned", contradicted_score=10.0)
    # would be 30 - 14 - 50 = -34; floors to MIN_TTL_DAYS
    assert compute_effective_ttl_days(fm) == MIN_TTL_DAYS


def test_combined_bonus_and_penalty() -> None:
    fm = _fm(exposure_count=2, contradicted_score=1.0, outcome="completed")
    # +6 -5 = +1 → 31
    assert compute_effective_ttl_days(fm) == DEFAULT_BASE_TTL_DAYS + 1


# ----------------------------------------------------------------------
# decide_decay
# ----------------------------------------------------------------------


def test_decide_decay_returns_full_breakdown() -> None:
    fm = _fm(
        ended=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
        exposure_count=2,
        contradicted_score=1.0,
    )
    today = date(2026, 4, 30)
    d = decide_decay(fm, today=today)
    assert isinstance(d, DecayDecision)
    assert d.session_id == "abc"
    assert d.exposure_bonus_days == 6
    assert d.contradicted_penalty_days == 5
    assert d.effective_ttl_days == 31
    assert d.expiry_anchor == date(2026, 4, 1)
    assert d.expires_on == date(2026, 5, 2)
    assert d.archivable is False  # today < expires_on


def test_decide_decay_archivable_when_expired() -> None:
    fm = _fm(
        ended=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
        outcome="abandoned",
    )
    today = date(2026, 4, 25)  # > 30 - 14 = 16 days from anchor
    d = decide_decay(fm, today=today)
    assert d.archivable is True


def test_decide_decay_uses_started_when_no_ended() -> None:
    fm = SessionFrontmatter(
        type="session",
        session_id="abc",
        client="claude-code",
        started_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
        ended_at=None,
    )
    d = decide_decay(fm, today=date(2026, 4, 5))
    assert d.expiry_anchor == date(2026, 4, 1)


def test_decide_decay_as_dict() -> None:
    fm = _fm()
    d = decide_decay(fm, today=date(2026, 4, 30))
    out = d.as_dict()
    assert out["session_id"] == "abc"
    assert out["effective_ttl_days"] == 30
    assert "expires_on" in out
