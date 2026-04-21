"""Phase 4 — staleness / time-expiry detection.

M4 stub. Full implementation (``time-expired`` class driven by
``deprecated_after`` dates + ``confidence_score`` + usage telemetry)
lands with M5 when the Evolve Engine supplies the usage counters.
"""

from __future__ import annotations

from pathlib import Path

from engram.consistency.types import ConflictReport

__all__ = ["detect_phase4"]


def detect_phase4(store_root: Path) -> list[ConflictReport]:
    """Return an empty list until M5 plumbs usage telemetry.

    Phase 4 is deliberately disabled rather than "naively stub". A
    half-working staleness detector would archive-propose active
    assets that happen to not have been referenced yet this week,
    which violates SPEC §1.2 principle 4 ("never auto-delete") at the
    proposal level."""
    _ = store_root
    return []
