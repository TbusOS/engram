"""Relevance Gate pipeline (T-40, DESIGN §5.1).

Orchestrates six stages of candidate selection for a given query:

1. **Mandatory bypass** — every ``enforcement=mandatory`` asset is
   unconditionally returned (DESIGN §5.1 Stage 1).
2. **BM25 recall** — keyword score on asset body (T-42).
3. **Vector recall + fusion** — when the caller supplies
   ``vector_scores`` (cosine similarities from a configured embedder),
   they are fused with BM25 by reciprocal-rank fusion; with none, the
   gate runs BM25-only (identical to before, zero dependency).
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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    "STAGE0_DEFAULT_BUDGET_FRACTION",
    "STAGE0_MAX_SESSIONS",
    "Asset",
    "RankedCandidate",
    "RelevanceRequest",
    "RelevanceResult",
    "SessionContinuation",
    "run_relevance_gate",
    "select_session_continuations",
]


_TOKENS_PER_BYTE = 0.25
"""DESIGN §5.1.3 token estimator — 4 bytes per token on average."""

# Stage 0 (T-206): cross-session continuation budget cap. Sessions
# matching the request's task_hash are injected before the mandatory
# bypass stage but their total cost is capped so they cannot starve
# Stage 1 / 5 / 6.
STAGE0_DEFAULT_BUDGET_FRACTION = 0.25
STAGE0_MAX_SESSIONS = 3


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
class SessionContinuation:
    """One Episodic session selected by Stage 0 for context injection.

    Body is the rendered Markdown narrative produced by Tier 1; size is
    used by the Stage 0 budget cap so sessions cannot starve the rest
    of the gate.
    """

    session_id: str
    task_hash: str
    body: str
    size_bytes: int
    ended_at: date | None = None


@dataclass(frozen=True, slots=True)
class RelevanceRequest:
    query: str
    assets: Sequence[Asset]
    budget_tokens: int = 8000
    now: date = date(1970, 1, 1)  # overridden by caller; default is epoch
    recency_halflife_days: float = 30.0
    # Stage 0 (T-206): if ``task_hash`` is set, sessions in
    # ``sessions`` with a matching task_hash get injected first, capped
    # at ``stage0_max_sessions`` and ``stage0_budget_fraction`` of the
    # total budget. Default empty so existing callers are unaffected.
    task_hash: str | None = None
    sessions: Sequence[SessionContinuation] = ()
    stage0_max_sessions: int = STAGE0_MAX_SESSIONS
    stage0_budget_fraction: float = STAGE0_DEFAULT_BUDGET_FRACTION
    # Stage 3 (T-41): optional vector recall. The caller computes per-asset
    # cosine similarities with a configured embedder (built once, reused) and
    # passes them here keyed by asset id; the gate fuses them with BM25 via
    # reciprocal-rank fusion. Empty (default) keeps the pure BM25 path —
    # identical behavior, zero dependency.
    vector_scores: Mapping[str, float] = field(default_factory=dict)
    rrf_k: int = 60
    rrf_weight_bm25: float = 1.0
    rrf_weight_vector: float = 1.0


@dataclass(frozen=True, slots=True)
class RelevanceResult:
    included: tuple[RankedCandidate, ...]
    excluded_due_to_budget: tuple[RankedCandidate, ...]
    mandatory: tuple[Asset, ...]
    total_tokens: int
    budget: int
    # Stage 0 output: sessions that survived task_hash matching + the
    # max-count cap + the per-call budget cap. Empty when no
    # ``task_hash`` was supplied or no sessions matched.
    sessions: tuple[SessionContinuation, ...] = ()
    sessions_tokens: int = 0


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


def _rrf_fuse(
    bm25: Mapping[str, float],
    vector: Mapping[str, float],
    *,
    k: int,
    w_bm25: float,
    w_vector: float,
) -> dict[str, float]:
    """Reciprocal-rank fusion of two score maps into one score per id.

    Each ranker contributes ``weight / (k + rank)`` for the ids it scores
    positively (1-based rank, descending score, id as a deterministic
    tie-breaker). Being rank-based, the two rankers' incomparable score
    scales (BM25 magnitude vs cosine) never need normalizing, and a doc
    only one ranker found still survives — that is how a zero-BM25
    paraphrase gets recalled by the vector side.
    """

    def _ranks(scores: Mapping[str, float]) -> dict[str, int]:
        positive = sorted(
            ((i, s) for i, s in scores.items() if s > 0.0),
            key=lambda x: (-x[1], x[0]),
        )
        return {i: rank for rank, (i, _) in enumerate(positive, start=1)}

    br = _ranks(bm25)
    vr = _ranks(vector)
    fused: dict[str, float] = {}
    for id_ in br.keys() | vr.keys():
        score = 0.0
        # Guard each term's denominator: rank >= 1 always, so this skips only
        # the terms a non-positive k would zero/invert. Safe for any int k
        # (a negative k just drops its lowest ranks); never divides by zero.
        if id_ in br and k + br[id_] > 0:
            score += w_bm25 / (k + br[id_])
        if id_ in vr and k + vr[id_] > 0:
            score += w_vector / (k + vr[id_])
        fused[id_] = score
    return fused


def select_session_continuations(
    *,
    task_hash: str | None,
    sessions: Sequence[SessionContinuation],
    budget_tokens: int,
    max_count: int = STAGE0_MAX_SESSIONS,
    budget_fraction: float = STAGE0_DEFAULT_BUDGET_FRACTION,
) -> tuple[tuple[SessionContinuation, ...], int]:
    """Stage 0 selector — pick at most ``max_count`` sessions matching ``task_hash``.

    Returns ``(picked, tokens_consumed)``. The total ``tokens_consumed``
    is bounded by ``int(budget_tokens * budget_fraction)``: when adding
    the next session would exceed the cap, selection stops. Sessions
    are picked in ``ended_at`` descending order (most-recent first); the
    returned tuple keeps that order so the caller can render newest-first.
    """
    if not task_hash:
        return ((), 0)
    if budget_tokens <= 0 or budget_fraction <= 0.0:
        return ((), 0)

    matching = [s for s in sessions if s.task_hash == task_hash]
    if not matching:
        return ((), 0)

    # Most recent first. ``ended_at`` may be None for in-flight sessions;
    # sort those last so closed sessions are preferred when both apply.
    def _sort_key(s: SessionContinuation) -> tuple[int, date]:
        if s.ended_at is None:
            return (0, date(1970, 1, 1))
        return (1, s.ended_at)

    matching.sort(key=_sort_key, reverse=True)

    cap_tokens = int(budget_tokens * budget_fraction)
    picked: list[SessionContinuation] = []
    spent = 0
    for s in matching:
        if len(picked) >= max_count:
            break
        cost = max(1, int(s.size_bytes * _TOKENS_PER_BYTE))
        if spent + cost > cap_tokens:
            break
        picked.append(s)
        spent += cost
    return (tuple(picked), spent)


def run_relevance_gate(request: RelevanceRequest) -> RelevanceResult:
    """Run the full pipeline. Pure function; safe to call in any context."""
    assets = list(request.assets)

    # ------------- Stage 0 — session continuation (T-206) -------
    sessions, sessions_tokens = select_session_continuations(
        task_hash=request.task_hash,
        sessions=request.sessions,
        budget_tokens=request.budget_tokens,
        max_count=request.stage0_max_sessions,
        budget_fraction=request.stage0_budget_fraction,
    )

    # ------------- Stage 1 — mandatory bypass -------------
    mandatory_assets = tuple(a for a in assets if a.enforcement == "mandatory")
    ranking_pool = [a for a in assets if a.enforcement != "mandatory"]

    # ------------- Stage 2 — BM25 recall ------------------
    documents = [(a.id, a.body) for a in ranking_pool]
    raw = dict(bm25_scores(request.query, documents))

    # ------------- Stage 3 — vector recall + RRF fusion (T-41) -----
    # When the caller supplies vector_scores, fuse them with BM25 by
    # reciprocal rank. Empty → fused is None → the pure BM25 base below.
    # Fuse only when the caller actually supplied a positive vector signal.
    # An empty or all-non-positive map must not switch the base off BM25's
    # scale (which would silently change ranking magnitudes for no gain).
    fused = (
        _rrf_fuse(
            raw,
            request.vector_scores,
            k=request.rrf_k,
            w_bm25=request.rrf_weight_bm25,
            w_vector=request.rrf_weight_vector,
        )
        if any(s > 0.0 for s in request.vector_scores.values())
        else None
    )

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
        # Fused mode blends BM25 + vector by reciprocal rank; BM25-only mode
        # keeps the raw keyword score. Either way a non-positive base means
        # neither signal recalled the asset, so it is dropped.
        base = fused.get(a.id, 0.0) if fused is not None else bm
        if not base > 0.0:  # also drops NaN (NaN > 0 is False)
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
        # CALIBRATION (pending the extended benchmark): in fused mode `base`
        # is an RRF score whose dynamic range is compressed (~1.02x between
        # adjacent ranks), so these multipliers — tuned against BM25's much
        # wider range — weigh more heavily than in BM25 mode and can flip
        # rankings. The current gold-set is uniform scope/date, so it cannot
        # tune this; no caller passes vector_scores yet. The RRF/multiplier
        # composition must be resolved with a mixed-scope/temporal gold-set
        # before any caller is wired to the fused path.
        final = base * scope_w * enf_w * decay * score_temp
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

    # id as a deterministic tie-break: RRF scores quantize, so exact ties are
    # common in fused mode; without it, tied output order would track caller
    # hydration order — fragile for a frozen benchmark.
    ranked.sort(key=lambda c: (-c.final_score, c.asset.id))

    # ------------- Stage 6 — budget pack -------------------
    # Greedy fill by score-per-token descending (DESIGN §5.1 Stage 7).
    remaining_budget = request.budget_tokens
    included: list[RankedCandidate] = []
    excluded: list[RankedCandidate] = []
    by_density = sorted(
        ranked,
        key=lambda c: (-(c.final_score / max(1, c.tokens_est)), c.asset.id),
    )
    for c in by_density:
        if c.tokens_est <= remaining_budget:
            included.append(c)
            remaining_budget -= c.tokens_est
        else:
            excluded.append(c)

    # Re-sort kept candidates by their final score so the caller's output
    # respects the ranking order, not the packing order.
    included.sort(key=lambda c: (-c.final_score, c.asset.id))

    return RelevanceResult(
        included=tuple(included),
        excluded_due_to_budget=tuple(excluded),
        mandatory=mandatory_assets,
        total_tokens=sum(c.tokens_est for c in included),
        budget=request.budget_tokens,
        sessions=sessions,
        sessions_tokens=sessions_tokens,
    )
