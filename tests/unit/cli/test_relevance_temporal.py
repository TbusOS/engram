"""T-43 tests: engram/relevance/temporal.py — "N weeks ago" parsing + boost.

DESIGN §5.1 Stage 5 "temporal boost": up to 40% distance reduction for
candidates whose ``updated`` date falls near a reference time pulled from
the query. The two pieces are independently testable pure functions:

- ``parse_temporal_hint(query, now)`` → ``date | None`` — interprets
  phrases like "yesterday", "last week", "3 weeks ago", "in March".
- ``temporal_distance_multiplier(candidate_date, reference_date)`` →
  ``float`` in ``[0.6, 1.0]``, where 0.6 is the maximum 40% reduction
  (for same-day candidates) and 1.0 means no boost (far enough apart
  that temporal signal carries no weight).
"""

from __future__ import annotations

from datetime import date

import pytest

from engram.relevance.temporal import (
    MAX_DISTANCE_REDUCTION,
    TEMPORAL_WINDOW_DAYS,
    parse_temporal_hint,
    temporal_distance_multiplier,
)


REFERENCE = date(2026, 4, 22)


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------


def test_max_distance_reduction_matches_design() -> None:
    """DESIGN §5.1 Stage 5: 'up to 40% distance reduction'."""
    assert MAX_DISTANCE_REDUCTION == pytest.approx(0.4)


def test_temporal_window_is_reasonable() -> None:
    """Window must be positive and non-trivial — 1-day windows collapse to binary."""
    assert TEMPORAL_WINDOW_DAYS >= 14


# ------------------------------------------------------------------
# Hint parsing
# ------------------------------------------------------------------


def test_parse_no_temporal_hint_returns_none() -> None:
    assert parse_temporal_hint("how do I rebase a branch", now=REFERENCE) is None
    assert parse_temporal_hint("", now=REFERENCE) is None


def test_parse_today() -> None:
    assert parse_temporal_hint("what did we decide today", now=REFERENCE) == REFERENCE


def test_parse_yesterday() -> None:
    assert parse_temporal_hint("the bug from yesterday", now=REFERENCE) == date(2026, 4, 21)


def test_parse_n_days_ago() -> None:
    assert parse_temporal_hint("postmortem 3 days ago", now=REFERENCE) == date(2026, 4, 19)
    assert parse_temporal_hint("10 days ago", now=REFERENCE) == date(2026, 4, 12)


def test_parse_last_week() -> None:
    got = parse_temporal_hint("rules we shipped last week", now=REFERENCE)
    assert got == date(2026, 4, 15)  # reference - 7 days


def test_parse_n_weeks_ago() -> None:
    assert parse_temporal_hint("2 weeks ago", now=REFERENCE) == date(2026, 4, 8)
    assert parse_temporal_hint("standups from 4 weeks ago", now=REFERENCE) == date(2026, 3, 25)


def test_parse_last_month() -> None:
    assert parse_temporal_hint("release cut last month", now=REFERENCE) == date(2026, 3, 23)


def test_parse_n_months_ago_is_approximate() -> None:
    """Month == 30 days for predictable arithmetic (calendar-aware is M5+)."""
    got = parse_temporal_hint("an incident 2 months ago", now=REFERENCE)
    assert got == date(2026, 2, 21)  # reference - 60 days


def test_parse_multiple_phrases_uses_first() -> None:
    """If a query mentions two temporal phrases, the first wins — further
    refinement is outside M4 scope."""
    got = parse_temporal_hint("yesterday not last week", now=REFERENCE)
    assert got == date(2026, 4, 21)


def test_parse_case_insensitive() -> None:
    assert parse_temporal_hint("Yesterday", now=REFERENCE) == date(2026, 4, 21)
    assert parse_temporal_hint("LAST WEEK", now=REFERENCE) == date(2026, 4, 15)


# ------------------------------------------------------------------
# Distance multiplier
# ------------------------------------------------------------------


def test_multiplier_same_day_is_maximum_boost() -> None:
    mult = temporal_distance_multiplier(REFERENCE, REFERENCE)
    assert mult == pytest.approx(1.0 - MAX_DISTANCE_REDUCTION)


def test_multiplier_outside_window_is_identity() -> None:
    far = date(2000, 1, 1)
    assert temporal_distance_multiplier(far, REFERENCE) == pytest.approx(1.0)


def test_multiplier_decays_linearly_in_window() -> None:
    """Half-way into the window ≈ 20% reduction (mult == 0.8)."""
    mid = date(REFERENCE.year, REFERENCE.month, REFERENCE.day)
    mid = date.fromordinal(REFERENCE.toordinal() - TEMPORAL_WINDOW_DAYS // 2)
    mult = temporal_distance_multiplier(mid, REFERENCE)
    assert mult == pytest.approx(0.8, rel=0.01)


def test_multiplier_symmetric_past_and_future() -> None:
    past = date.fromordinal(REFERENCE.toordinal() - 5)
    future = date.fromordinal(REFERENCE.toordinal() + 5)
    assert temporal_distance_multiplier(past, REFERENCE) == pytest.approx(
        temporal_distance_multiplier(future, REFERENCE)
    )


def test_multiplier_none_reference_is_identity() -> None:
    """When the query has no temporal hint, the multiplier is always 1.0."""
    assert temporal_distance_multiplier(REFERENCE, None) == 1.0


def test_multiplier_bounds() -> None:
    """Regardless of dates, multiplier stays in [0.6, 1.0]."""
    for offset in (-100, -30, -5, 0, 5, 30, 100):
        d = date.fromordinal(REFERENCE.toordinal() + offset)
        mult = temporal_distance_multiplier(d, REFERENCE)
        assert 0.6 - 1e-9 <= mult <= 1.0 + 1e-9
