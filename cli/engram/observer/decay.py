"""Confidence-driven decay for Session assets.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §7.1.

Sessions don't expire on a fixed clock — they expire on a
confidence-weighted clock:

    base_ttl              = 30 days
    exposure_bonus        = min(exposure_count * 3 days, +60 days)
    contradicted_penalty  = contradicted_score * 5 days
    abandoned_penalty     = (outcome == "abandoned") ? 14 days : 0

    effective_ttl = max(7 days, base_ttl + bonus - contradicted - abandoned)

Sessions whose ``ended_at + effective_ttl`` is past the current date
are eligible for archival to ``~/.engram/archive/sessions/<YYYY-MM>/``.
This module computes that — the actual move is performed by
``engram observer decay --apply`` (which lands in a separate task) or
by a daemon job.

The function is **pure**: it takes a SessionFrontmatter and returns a
DecayDecision with the effective_ttl and whether the session is now
archivable. No filesystem access, no datetime side-effects, easy to
unit-test against fixed dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from engram.observer.session import SessionFrontmatter

__all__ = [
    "DEFAULT_ABANDONED_PENALTY_DAYS",
    "DEFAULT_BASE_TTL_DAYS",
    "DEFAULT_CONTRADICTED_PENALTY_PER_HIT_DAYS",
    "DEFAULT_EXPOSURE_BONUS_CAP_DAYS",
    "DEFAULT_EXPOSURE_BONUS_PER_HIT_DAYS",
    "MIN_TTL_DAYS",
    "DecayDecision",
    "compute_effective_ttl_days",
    "decide_decay",
]


DEFAULT_BASE_TTL_DAYS = 30
DEFAULT_EXPOSURE_BONUS_PER_HIT_DAYS = 3
DEFAULT_EXPOSURE_BONUS_CAP_DAYS = 60
DEFAULT_CONTRADICTED_PENALTY_PER_HIT_DAYS = 5
DEFAULT_ABANDONED_PENALTY_DAYS = 14
MIN_TTL_DAYS = 7


@dataclass(frozen=True)
class DecayDecision:
    """How a session's TTL was computed and whether to archive it now."""

    session_id: str
    base_ttl_days: int
    exposure_bonus_days: int
    contradicted_penalty_days: int
    abandoned_penalty_days: int
    effective_ttl_days: int
    expiry_anchor: date  # ended_at if set, else started_at
    expires_on: date
    archivable: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "base_ttl_days": self.base_ttl_days,
            "exposure_bonus_days": self.exposure_bonus_days,
            "contradicted_penalty_days": self.contradicted_penalty_days,
            "abandoned_penalty_days": self.abandoned_penalty_days,
            "effective_ttl_days": self.effective_ttl_days,
            "expiry_anchor": self.expiry_anchor.isoformat(),
            "expires_on": self.expires_on.isoformat(),
            "archivable": self.archivable,
        }


def compute_effective_ttl_days(
    fm: SessionFrontmatter,
    *,
    base_ttl_days: int = DEFAULT_BASE_TTL_DAYS,
    exposure_bonus_per_hit_days: int = DEFAULT_EXPOSURE_BONUS_PER_HIT_DAYS,
    exposure_bonus_cap_days: int = DEFAULT_EXPOSURE_BONUS_CAP_DAYS,
    contradicted_penalty_per_hit_days: int = DEFAULT_CONTRADICTED_PENALTY_PER_HIT_DAYS,
    abandoned_penalty_days: int = DEFAULT_ABANDONED_PENALTY_DAYS,
    min_ttl_days: int = MIN_TTL_DAYS,
) -> int:
    """Apply the spec §7.1 formula to one SessionFrontmatter."""
    bonus_raw = fm.confidence.exposure_count * exposure_bonus_per_hit_days
    bonus = min(bonus_raw, exposure_bonus_cap_days)
    penalty_contradicted = int(
        fm.confidence.contradicted_score * contradicted_penalty_per_hit_days
    )
    penalty_abandoned = (
        abandoned_penalty_days if fm.outcome == "abandoned" else 0
    )
    raw = base_ttl_days + bonus - penalty_contradicted - penalty_abandoned
    return max(min_ttl_days, raw)


def decide_decay(
    fm: SessionFrontmatter,
    *,
    today: date,
    base_ttl_days: int = DEFAULT_BASE_TTL_DAYS,
    exposure_bonus_per_hit_days: int = DEFAULT_EXPOSURE_BONUS_PER_HIT_DAYS,
    exposure_bonus_cap_days: int = DEFAULT_EXPOSURE_BONUS_CAP_DAYS,
    contradicted_penalty_per_hit_days: int = DEFAULT_CONTRADICTED_PENALTY_PER_HIT_DAYS,
    abandoned_penalty_days: int = DEFAULT_ABANDONED_PENALTY_DAYS,
    min_ttl_days: int = MIN_TTL_DAYS,
) -> DecayDecision:
    """Compute a full decay decision for a session.

    The ``today`` parameter is required so callers (CLI / daemon)
    decide what "now" means; tests pass a fixed date.
    """
    bonus_raw = fm.confidence.exposure_count * exposure_bonus_per_hit_days
    bonus = min(bonus_raw, exposure_bonus_cap_days)
    penalty_contradicted = int(
        fm.confidence.contradicted_score * contradicted_penalty_per_hit_days
    )
    penalty_abandoned = (
        abandoned_penalty_days if fm.outcome == "abandoned" else 0
    )
    raw_ttl = base_ttl_days + bonus - penalty_contradicted - penalty_abandoned
    effective_ttl = max(min_ttl_days, raw_ttl)

    anchor_dt = fm.ended_at if fm.ended_at is not None else fm.started_at
    anchor = anchor_dt.date()
    expires = anchor + timedelta(days=effective_ttl)
    archivable = today >= expires

    return DecayDecision(
        session_id=fm.session_id,
        base_ttl_days=base_ttl_days,
        exposure_bonus_days=bonus,
        contradicted_penalty_days=penalty_contradicted,
        abandoned_penalty_days=penalty_abandoned,
        effective_ttl_days=effective_ttl,
        expiry_anchor=anchor,
        expires_on=expires,
        archivable=archivable,
    )
