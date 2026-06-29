"""T-40 tests: engram/relevance/gate.py — 7-stage Relevance Gate pipeline.

Scope for M4:

- **Stage 1** (mandatory bypass, DESIGN §5.1): any ``enforcement=mandatory``
  asset is unconditionally included.
- **Stage 2** (BM25, T-42): raw keyword similarity.
- **Stage 3** (vector): deferred to T-41; the gate passes through.
- **Stage 4** (temporal, T-43): query-aware date boost.
- **Stage 5** (scope + enforcement weighting, T-38): project > user >
  team > org; mandatory > default > hint.
- **Stage 6** (budget pack): greedy fill by score-per-token, SPEC §7.2
  ordering.

The tests use small, curated asset sets where one factor (BM25 /
scope / enforcement / temporal / budget) drives the outcome so the
assertion never depends on brittle score arithmetic.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from engram.relevance.gate import (
    Asset,
    RelevanceRequest,
    run_relevance_gate,
)


NOW = date(2026, 4, 22)


def _a(
    id_: str,
    body: str,
    *,
    scope: str = "project",
    enforcement: str = "default",
    subscribed_at: str | None = None,
    updated: date = NOW,
    size_bytes: int = 400,
) -> Asset:
    return Asset(
        id=id_,
        scope=scope,
        enforcement=enforcement,
        subscribed_at=subscribed_at,
        body=body,
        updated=updated,
        size_bytes=size_bytes,
    )


# ------------------------------------------------------------------
# Degenerate cases
# ------------------------------------------------------------------


def test_empty_assets_returns_empty_result() -> None:
    req = RelevanceRequest(query="kernel", assets=(), budget_tokens=1000, now=NOW)
    result = run_relevance_gate(req)
    assert result.included == ()
    assert result.excluded_due_to_budget == ()
    assert result.mandatory == ()


def test_zero_budget_drops_everything_even_if_matching() -> None:
    req = RelevanceRequest(
        query="kernel",
        assets=(_a("a", "kernel match kernel"),),
        budget_tokens=0,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert result.included == ()
    assert len(result.excluded_due_to_budget) == 1


# ------------------------------------------------------------------
# Stage 1 — mandatory bypass
# ------------------------------------------------------------------


def test_mandatory_included_even_without_query_match() -> None:
    """A mandatory asset with zero BM25 relevance still lands in the pack."""
    req = RelevanceRequest(
        query="database sharding",
        assets=(
            _a("mand", "rule about pushes", enforcement="mandatory"),
            _a("match", "database sharding strategies"),
        ),
        budget_tokens=1000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert any(a.id == "mand" for a in result.mandatory)
    # Mandatory does not appear in `included` — it is accounted separately.
    assert all(c.asset.id != "mand" for c in result.included)


def test_mandatory_consumes_budget_first() -> None:
    """Mandatory consumes budget before ranked candidates; when the budget
    is tight, ranked candidates get squeezed out."""
    big_mandatory = _a("big", "x " * 1000, enforcement="mandatory", size_bytes=4000)
    req = RelevanceRequest(
        query="topic",
        assets=(big_mandatory, _a("topic-hit", "topic match", size_bytes=100)),
        budget_tokens=500,  # mandatory alone fits (~1000 token estimate exceeds)
        now=NOW,
    )
    result = run_relevance_gate(req)
    # Mandatory is always kept; it may over-spend — DESIGN §5.1 Stage 1
    # permits mandatory to blow the budget. Ranked candidates get dropped.
    assert result.mandatory and result.mandatory[0].id == "big"


# ------------------------------------------------------------------
# Stage 2 — BM25 surfaces matching docs
# ------------------------------------------------------------------


def test_bm25_ranks_matching_doc_first() -> None:
    req = RelevanceRequest(
        query="kernel",
        assets=(
            _a("unrelated", "cake sugar flour"),
            _a("match", "kernel module patch kernel"),
        ),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    ids = [c.asset.id for c in result.included]
    # Unrelated doc is dropped for zero BM25; only match appears.
    assert ids == ["match"]


# ------------------------------------------------------------------
# Stage 5 — scope + enforcement weighting
# ------------------------------------------------------------------


def test_project_outranks_org_with_equal_bm25() -> None:
    req = RelevanceRequest(
        query="topic",
        assets=(
            _a("proj", "topic topic", scope="project"),
            _a("orgn", "topic topic", scope="org"),
        ),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "proj"


def test_default_enforcement_outranks_hint_with_equal_bm25() -> None:
    req = RelevanceRequest(
        query="topic",
        assets=(
            _a("hint", "topic topic", enforcement="hint"),
            _a("deflt", "topic topic", enforcement="default"),
        ),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "deflt"


# ------------------------------------------------------------------
# Stage 4 — temporal
# ------------------------------------------------------------------


def test_temporal_boost_favors_recent_when_query_has_hint() -> None:
    old = _a("old", "topic topic", updated=NOW - timedelta(days=60))
    recent = _a("recent", "topic topic", updated=NOW - timedelta(days=1))
    req = RelevanceRequest(
        query="topic yesterday",
        assets=(old, recent),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "recent"


def test_temporal_no_hint_no_effect() -> None:
    """Without a temporal phrase, old/new assets rank by BM25 + weights alone."""
    old = _a("old", "topic topic match", updated=NOW - timedelta(days=60))
    recent = _a("recent", "topic topic", updated=NOW - timedelta(days=1))
    req = RelevanceRequest(
        query="topic match",
        assets=(old, recent),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    # "match" appears only in old → old wins regardless of age.
    assert result.included[0].asset.id == "old"


# ------------------------------------------------------------------
# Stage 6 — budget pack
# ------------------------------------------------------------------


def test_budget_cap_respected_and_excess_reported() -> None:
    big = _a("big", "topic topic", size_bytes=3600)  # ~900 tokens
    small_a = _a("small-a", "topic", size_bytes=200)
    small_b = _a("small-b", "topic", size_bytes=200)
    req = RelevanceRequest(
        query="topic",
        assets=(big, small_a, small_b),
        budget_tokens=400,  # only one small fits
        now=NOW,
    )
    result = run_relevance_gate(req)
    included_ids = {c.asset.id for c in result.included}
    excluded_ids = {c.asset.id for c in result.excluded_due_to_budget}
    assert included_ids | excluded_ids == {"big", "small-a", "small-b"}
    assert result.total_tokens <= req.budget_tokens


def test_result_token_total_matches_included_estimates() -> None:
    req = RelevanceRequest(
        query="topic",
        assets=(
            _a("a", "topic topic", size_bytes=400),
            _a("b", "topic topic", size_bytes=400),
        ),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert result.total_tokens == sum(c.tokens_est for c in result.included)


# ------------------------------------------------------------------
# Stage 3 — vector recall + RRF fusion (T-41)
# ------------------------------------------------------------------


def test_empty_vector_scores_is_bm25_only() -> None:
    """Default (no vector_scores) keeps the BM25-only path: a zero-BM25 doc
    is still dropped, exactly as before the semantic layer."""
    req = RelevanceRequest(
        query="kernel",
        assets=(_a("unrelated", "cake sugar"), _a("match", "kernel kernel")),
        budget_tokens=10_000,
        now=NOW,
    )
    result = run_relevance_gate(req)
    assert [c.asset.id for c in result.included] == ["match"]


def test_vector_scores_rescue_zero_bm25_doc() -> None:
    """A doc with no lexical overlap (BM25=0) is recalled when its vector
    score is positive — the paraphrase gap the semantic layer closes."""
    req = RelevanceRequest(
        query="kernel",
        assets=(_a("kw", "kernel kernel"), _a("sem", "no shared words here")),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"sem": 0.8, "kw": 0.2},
    )
    result = run_relevance_gate(req)
    ids = [c.asset.id for c in result.included]
    assert "sem" in ids  # rescued despite zero BM25
    assert "kw" in ids


def test_rrf_ranks_dual_signal_doc_first() -> None:
    """RRF rewards agreement: a doc ranked top by BOTH BM25 and vector
    outranks docs that lead only one ranker."""
    req = RelevanceRequest(
        query="alpha",
        assets=(
            _a("both", "alpha alpha"),  # bm25 #1
            _a("kw_only", "alpha"),  # bm25 #2, no vector
            _a("sem_only", "unrelated"),  # bm25 0, vector only
        ),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"both": 0.9, "sem_only": 0.7},  # both #1, sem_only #2
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "both"


def test_vector_weight_can_promote_semantic_match() -> None:
    """Raising the vector weight lets a strong vector-only doc outrank a
    BM25-only doc — the knob the benchmark tunes."""
    heavy_vec = run_relevance_gate(
        RelevanceRequest(
            query="alpha",
            assets=(_a("kw_only", "alpha"), _a("sem_only", "unrelated")),
            budget_tokens=10_000,
            now=NOW,
            vector_scores={"sem_only": 0.9},
            rrf_weight_vector=5.0,
        )
    )
    assert heavy_vec.included[0].asset.id == "sem_only"


def test_bm25_only_default_unaffected_by_fusion_fields() -> None:
    """The fusion fields are inert with empty vector_scores: ranking is
    byte-identical to a request that never sets them."""
    assets = (_a("a", "alpha beta"), _a("b", "beta gamma"), _a("c", "delta"))
    plain = run_relevance_gate(
        RelevanceRequest(query="beta", assets=assets, budget_tokens=10_000, now=NOW)
    )
    with_fields = run_relevance_gate(
        RelevanceRequest(
            query="beta",
            assets=assets,
            budget_tokens=10_000,
            now=NOW,
            rrf_k=10,
            rrf_weight_vector=9.0,
        )
    )
    assert [c.asset.id for c in plain.included] == [
        c.asset.id for c in with_fields.included
    ]
    assert [c.final_score for c in plain.included] == [
        c.final_score for c in with_fields.included
    ]


def test_all_nonpositive_vector_scores_stay_on_bm25_path() -> None:
    """A vector map with no positive entry must not switch the base off BM25:
    a zero-BM25 doc stays dropped, exactly like the default path."""
    req = RelevanceRequest(
        query="kernel",
        assets=(_a("unrelated", "cake sugar"), _a("match", "kernel kernel")),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"unrelated": 0.0, "match": 0.0},
    )
    result = run_relevance_gate(req)
    assert [c.asset.id for c in result.included] == ["match"]


def test_fused_ties_break_by_id_deterministically() -> None:
    """Two docs that fuse to the same score (one BM25-rank-1, one vector-rank-1,
    equal weights) order by id, independent of input order."""
    a_sem = _a("a_sem", "unrelated")  # vector rank 1 only
    z_kw = _a("z_kw", "alpha")  # bm25 rank 1 only
    vs = {"a_sem": 0.9}
    forward = run_relevance_gate(
        RelevanceRequest(
            query="alpha", assets=(z_kw, a_sem), budget_tokens=10_000, now=NOW,
            vector_scores=vs,
        )
    )
    reverse = run_relevance_gate(
        RelevanceRequest(
            query="alpha", assets=(a_sem, z_kw), budget_tokens=10_000, now=NOW,
            vector_scores=vs,
        )
    )
    order = [c.asset.id for c in forward.included]
    assert order == ["a_sem", "z_kw"]  # id-ascending on the tie
    assert order == [c.asset.id for c in reverse.included]  # input-order-independent


def test_nonfinite_vector_score_does_not_crash() -> None:
    """A NaN/inf cosine from a misbehaving embedder must not crash or corrupt:
    NaN is dropped by the positive-score filter; the BM25 doc still ranks."""
    req = RelevanceRequest(
        query="kernel",
        assets=(_a("kw", "kernel kernel"), _a("sem", "unrelated")),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"sem": float("nan"), "kw": float("inf")},
    )
    result = run_relevance_gate(req)
    ids = [c.asset.id for c in result.included]
    assert "kw" in ids
    assert all(math.isfinite(c.final_score) for c in result.included)


def test_fused_relevance_beats_higher_scope_distractor() -> None:
    """Calibration guard: a more-relevant low-scope (org, 0.8) doc must outrank a
    less-relevant high-scope (project, 1.5) distractor in fused mode.

    The step-3 compressed-RRF base let the scope multiplier flip these (measured
    scope MRR 0.33). The harmonic-rank base (1/rank) restores BM25-like spread so
    relevance wins the large gap; scope only breaks near-ties.
    """
    org_hit = _a("org_hit", "alpha alpha", scope="org")  # strongest relevance
    proj_near = _a("proj_near", "alpha beta", scope="project")  # weaker, higher scope
    req = RelevanceRequest(
        query="alpha",
        assets=(org_hit, proj_near),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"org_hit": 0.9, "proj_near": 0.85},
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "org_hit"


def test_fused_temporal_boost_prefers_recent() -> None:
    """In fused mode a temporal query still boosts the recent doc: recency decay
    + the temporal multiplier compose with the harmonic base as in BM25 mode."""
    recent = _a("recent", "deploy topic", updated=NOW - timedelta(days=2))
    old = _a("old", "deploy topic", updated=NOW - timedelta(days=200))
    req = RelevanceRequest(
        query="deploy topic last week",
        assets=(old, recent),
        budget_tokens=10_000,
        now=NOW,
        vector_scores={"recent": 0.8, "old": 0.8},
    )
    result = run_relevance_gate(req)
    assert result.included[0].asset.id == "recent"


def test_fused_equal_relevance_scope_decides_not_id() -> None:
    """Two exactly-equally-relevant docs (same body, same vector score) differing
    only in scope: the higher-scope (project) wins, independent of id spelling —
    not the alphabetically-first id. Locks the step-3 review MEDIUM: competition
    ranking makes their RRF tie, and the fused order settles the tie by scope.
    """
    org = _a("aaa_org", "topic topic", scope="org")  # id sorts first
    proj = _a("zzz_proj", "topic topic", scope="project")  # higher scope
    vs = {"aaa_org": 0.5, "zzz_proj": 0.5}
    forward = run_relevance_gate(
        RelevanceRequest(
            query="topic", assets=(org, proj), budget_tokens=10_000, now=NOW,
            vector_scores=vs,
        )
    )
    reverse = run_relevance_gate(
        RelevanceRequest(
            query="topic", assets=(proj, org), budget_tokens=10_000, now=NOW,
            vector_scores=vs,
        )
    )
    assert forward.included[0].asset.id == "zzz_proj"  # scope, not id, decides
    assert reverse.included[0].asset.id == "zzz_proj"  # input-order-independent
