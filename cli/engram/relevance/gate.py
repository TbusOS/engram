"""Relevance Gate pipeline (T-40, DESIGN §5.1).

Orchestrates six stages of candidate selection for a given query:

1. **Mandatory bypass** — every ``enforcement=mandatory`` asset is
   unconditionally returned (DESIGN §5.1 Stage 1).
2. **BM25 recall** — keyword score on asset body (T-42).
3. **Vector recall** — deferred to T-41; the gate passes through when
   no embedder is configured. Present as a named hook so T-41 is a
   drop-in addition later.
4. **Temporal boost** — when the query contains a "last week" /
   "yesterday" / "N weeks ago" phrase, candidates whose ``updated``
   date falls near the reference receive up to 40% distance reduction
   (T-43).
5. **Scope + enforcement weighting** — project > user > team > org;
   mandatory > default > hint (T-38).
6. **Budget pack** — greedy fill by score-per-token; the tail that
   doesn't fit is reported as ``excluded_due_to_budget`` for the
   caller's diagnostics.

The gate is a pure function: no IO, no DB, no network. Callers (the
M2 search subcommand today, ``engram context pack`` tomorrow) hydrate
the ``Asset`` tuples from ``graph.db`` + filesystem and interpret the
``RelevanceResult``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from engram.relevance.bm25 import bm25_scores
from engram.relevance.temporal import (
    parse_temporal_hint,
    temporal_distance_multiplier,
)
from engram.relevance.weights import (
    ENFORCEMENT_WEIGHTS,
    SCOPE_WEIGHTS,
)

__all__ = [
    "Asset",
    "RankedCandidate",
    "RelevanceRequest",
    "RelevanceResult",
    "run_relevance_gate",
]


_TOKENS_PER_BYTE = 0.25
"""DESIGN §5.1.3 token estimator — 4 bytes per token on average."""


@dataclass(frozen=True, slots=True)
class Asset:
    """Minimum asset view the Relevance Gate needs.

    Callers hydrate this from ``graph.db`` + the asset file on disk.
    Keeping the view small lets the gate stay pure (no Path dependence,
    no re-reads) and simplifies testing.
    """

    id: str
    scope: str
    enforcement: str
    subscribed_at: str | None
    body: str
    updated: date
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One asset's position in the Gate's output ranking."""

    asset: Asset
    bm25: float
    temporal_mult: float
    scope_weight: float
    enforcement_weight: float
    final_score: float
    tokens_est: int


@dataclass(frozen=True, slots=True)
class RelevanceRequest:
    query: str
    assets: Sequence[Asset]
    budget_tokens: int = 8000
    now: date = date(1970, 1, 1)  # overridden by caller; default is epoch
    recency_halflife_days: float = 30.0


@dataclass(frozen=True, slots=True)
class RelevanceResult:
    included: tuple[RankedCandidate, ...]
    excluded_due_to_budget: tuple[RankedCandidate, ...]
    mandatory: tuple[Asset, ...]
    total_tokens: int
    budget: int


def _tokens(asset: Asset) -> int:
    return max(1, int(asset.size_bytes * _TOKENS_PER_BYTE))


def _scope_weight_for(asset: Asset) -> float:
    if asset.scope == "pool" and asset.subscribed_at in SCOPE_WEIGHTS:
        return SCOPE_WEIGHTS[asset.subscribed_at]
    return SCOPE_WEIGHTS.get(asset.scope, 1.0)


def _recency_decay(asset: Asset, now: date, halflife_days: float) -> float:
    """DESIGN §5.1 Stage 5 recency decay: exp(-days / halflife_days)."""
    days = max(0, (now - asset.updated).days)
    return math.exp(-days / halflife_days) if halflife_days > 0 else 1.0


def run_relevance_gate(request: RelevanceRequest) -> RelevanceResult:
    """Run the full pipeline. Pure function; safe to call in any context."""
    assets = list(request.assets)

    # ------------- Stage 1 — mandatory bypass -------------
    mandatory_assets = tuple(a for a in assets if a.enforcement == "mandatory")
    ranking_pool = [a for a in assets if a.enforcement != "mandatory"]

    # ------------- Stage 2 — BM25 recall ------------------
    documents = [(a.id, a.body) for a in ranking_pool]
    raw = dict(bm25_scores(request.query, documents))

    # ------------- Stage 3 — vector recall (T-41 placeholder) -----
    # No-op until an embedder is wired in.

    # ------------- Stage 4 — temporal boost ----------------
    ref_date = parse_temporal_hint(request.query, now=request.now)

    # ------------- Stage 5 — scope + enforcement weighting -----
    # Recency decay + temporal multiplier both activate only when the
    # query contains a temporal phrase. A task query with no "last week"
    # / "yesterday" / "N days ago" hint should rank on relevance + scope
    # + enforcement alone, so old curated rules don't get decayed out.
    ranked: list[RankedCandidate] = []
    for a in ranking_pool:
        bm = raw.get(a.id, 0.0)
        if bm <= 0.0:
            continue
        temp_mult = temporal_distance_multiplier(a.updated, ref_date)
        scope_w = _scope_weight_for(a)
        enf_w = ENFORCEMENT_WEIGHTS.get(a.enforcement, 1.0)
        if ref_date is None:
            score_temp = 1.0
            decay = 1.0
        else:
            # temporal multiplier is distance-space — invert into score-space.
            score_temp = 1.0 / temp_mult if temp_mult > 0 else 1.0
            decay = _recency_decay(a, request.now, request.recency_halflife_days)
        final = bm * scope_w * enf_w * decay * score_temp
        ranked.append(
            RankedCandidate(
                asset=a,
                bm25=bm,
                temporal_mult=temp_mult,
                scope_weight=scope_w,
                enforcement_weight=enf_w,
                final_score=final,
                tokens_est=_tokens(a),
            )
        )

    ranked.sort(key=lambda c: c.final_score, reverse=True)

    # ------------- Stage 6 — budget pack -------------------
    # Greedy fill by score-per-token descending (DESIGN §5.1 Stage 7).
    remaining_budget = request.budget_tokens
    included: list[RankedCandidate] = []
    excluded: list[RankedCandidate] = []
    by_density = sorted(
        ranked,
        key=lambda c: (c.final_score / max(1, c.tokens_est)),
        reverse=True,
    )
    for c in by_density:
        if c.tokens_est <= remaining_budget:
            included.append(c)
            remaining_budget -= c.tokens_est
        else:
            excluded.append(c)

    # Re-sort kept candidates by their final score so the caller's output
    # respects the ranking order, not the packing order.
    included.sort(key=lambda c: c.final_score, reverse=True)

    return RelevanceResult(
        included=tuple(included),
        excluded_due_to_budget=tuple(excluded),
        mandatory=mandatory_assets,
        total_tokens=sum(c.tokens_est for c in included),
        budget=request.budget_tokens,
    )
