"""Derive ``ConfidenceCache`` for an asset from its usage events.

This is the issue #9 contract: frontmatter ``confidence:`` becomes a
**derived cache**, never a writable field. Tools append to ``usage.jsonl``;
this module recomputes the cache on demand.

Scoring rules (SPEC §11.4 amend candidate):

- ``validated_score`` = sum of positive trust_weights, with co_assets
  attribution: events that mention N co_assets contribute trust_weight / N
  to each. This stops "task succeeded → 10 loaded assets each get +0.2"
  inflation.
- ``contradicted_score`` = sum of |negative trust_weights| with the same
  attribution rule.
- ``exposure_count`` = total event count (including LOADED_ONLY) so
  aggregation can normalize per-exposure correctness.
- ``last_validated`` = max timestamp date among events with positive
  trust_weight; falls back to today when none exist.
- ``evidence_version`` = current trust-weight table version, so a stale
  cache (built under a previous trust-weight table) can be detected
  and refreshed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from engram.usage.reader import iter_events
from engram.usage.trust_weights import EVIDENCE_VERSION


@dataclass(frozen=True)
class ConfidenceCache:
    asset_uri: str
    validated_score: float
    contradicted_score: float
    exposure_count: int
    last_validated: str  # ISO-8601 date
    evidence_version: int = EVIDENCE_VERSION


def derive_confidence_cache(asset_uri: str) -> ConfidenceCache:
    validated = 0.0
    contradicted = 0.0
    exposure = 0
    latest_positive: str | None = None

    for ev in iter_events(asset_uri=asset_uri):
        exposure += 1
        weight = float(ev.trust_weight or 0.0)
        if weight == 0.0:
            continue
        # Co-asset attribution: event lists N co_assets → weight / N per asset.
        # When the asset_uri is the sole load (no co_assets), divisor is 1.
        n_co = max(1, len(ev.co_assets))
        adjusted = weight / n_co
        if adjusted > 0:
            validated += adjusted
            stamp = ev.timestamp.split("T", 1)[0] if ev.timestamp else None
            if stamp and (latest_positive is None or stamp > latest_positive):
                latest_positive = stamp
        else:
            contradicted += -adjusted

    return ConfidenceCache(
        asset_uri=asset_uri,
        validated_score=round(validated, 6),
        contradicted_score=round(contradicted, 6),
        exposure_count=exposure,
        last_validated=latest_positive or date.today().isoformat(),
        evidence_version=EVIDENCE_VERSION,
    )
