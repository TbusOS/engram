"""Temporal hint parsing + distance multiplier (T-43).

DESIGN §5.1 Stage 5 — "temporal boost": up to 40% distance reduction for
candidate assets whose ``updated`` date falls near a reference date
extracted from the query. Two pure functions, independently testable.

Parsing is deliberately simple: regex matches over a short phrase
vocabulary (``today``, ``yesterday``, ``N days/weeks/months ago``,
``last week``, ``last month``). Full calendar-aware natural-language
parsing (``in March``, ``Q1 2026``) is deferred to M5; the M4 Relevance
Gate's job is to boost recency, not to be a date parser.

Months are normalized to 30 days so that ``2 months ago`` is always
``reference - 60 days``. This keeps boosting deterministic and avoids
the "which February" edge cases that creep in with calendar arithmetic.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

__all__ = [
    "MAX_DISTANCE_REDUCTION",
    "TEMPORAL_WINDOW_DAYS",
    "parse_temporal_hint",
    "temporal_distance_multiplier",
]


MAX_DISTANCE_REDUCTION: float = 0.4
"""DESIGN §5.1 Stage 5 ceiling — same-day candidate gets 40% distance drop."""

TEMPORAL_WINDOW_DAYS: int = 30
"""Candidate dates beyond this window receive no temporal boost."""


# Match N days / weeks / months ago. ``\b`` boundaries prevent "3days"
# from matching accidentally and keep word-level precision.
_N_UNIT_RE = re.compile(r"\b(\d+)\s+(day|days|week|weeks|month|months)\s+ago\b")
_LAST_WEEK_RE = re.compile(r"\blast\s+week\b")
_LAST_MONTH_RE = re.compile(r"\blast\s+month\b")
_YESTERDAY_RE = re.compile(r"\byesterday\b")
_TODAY_RE = re.compile(r"\btoday\b")


def parse_temporal_hint(query: str, *, now: date) -> date | None:
    """Return a reference date if ``query`` contains a temporal phrase.

    Returns ``None`` when no phrase matches; the Relevance Gate then
    skips Stage 5 entirely. The earliest-matching phrase wins when the
    query contains multiple (e.g. "yesterday not last week"); picking
    "first match" keeps behaviour predictable without a relevance-of-
    temporal-phrase heuristic.
    """
    if not query:
        return None

    q = query.lower()

    # Collect all (position, date) candidates, pick the earliest.
    candidates: list[tuple[int, date]] = []

    if m := _TODAY_RE.search(q):
        candidates.append((m.start(), now))
    if m := _YESTERDAY_RE.search(q):
        candidates.append((m.start(), now - timedelta(days=1)))
    if m := _LAST_WEEK_RE.search(q):
        candidates.append((m.start(), now - timedelta(days=7)))
    if m := _LAST_MONTH_RE.search(q):
        candidates.append((m.start(), now - timedelta(days=30)))
    for m in _N_UNIT_RE.finditer(q):
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("day"):
            delta = timedelta(days=n)
        elif unit.startswith("week"):
            delta = timedelta(days=n * 7)
        else:  # month / months
            delta = timedelta(days=n * 30)
        candidates.append((m.start(), now - delta))

    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def temporal_distance_multiplier(
    candidate_date: date,
    reference_date: date | None,
) -> float:
    """Return the multiplier to apply to a candidate's distance score.

    The multiplier lives in ``[1 - MAX_DISTANCE_REDUCTION, 1.0]``:

    - 1.0 means "no boost" — no temporal hint in the query, or the
      candidate is outside the ``TEMPORAL_WINDOW_DAYS`` window.
    - 0.6 (= 1 - 0.4) means "maximum boost" — candidate date matches
      the reference date exactly.
    - Linear between.

    Callers apply this multiplier to a distance metric (lower = better),
    so a smaller multiplier ranks the candidate higher. Equivalent to
    multiplying the score by ``1 / multiplier`` if working in score-space.
    """
    if reference_date is None:
        return 1.0
    days = abs((candidate_date - reference_date).days)
    if days >= TEMPORAL_WINDOW_DAYS:
        return 1.0
    # Linear decay: 0 days → 1 - MAX, WINDOW days → 1.0.
    fraction_of_window = days / TEMPORAL_WINDOW_DAYS
    return 1.0 - MAX_DISTANCE_REDUCTION * (1.0 - fraction_of_window)
