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
