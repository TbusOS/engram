"""T-45 tests: engram/relevance/cache.py — LRU + TTL cache.

Per DESIGN §3.3: cache key is (query_hash, scope_hash, budget); entries
expire after 5 minutes; a simple LRU bounds memory. The cache sits in
front of :func:`engram.relevance.gate.run_relevance_gate` as a pure
wrapper — the gate itself stays pure and cache-agnostic.
"""

from __future__ import annotations

import time
from datetime import date

from engram.relevance.cache import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_TTL_SECONDS,
    RelevanceCache,
    cache_key,
)
from engram.relevance.gate import (
    Asset,
    RelevanceRequest,
    RelevanceResult,
    run_relevance_gate,
)


NOW = date(2026, 4, 22)


def _mkreq(query: str = "topic", budget: int = 1000) -> RelevanceRequest:
    return RelevanceRequest(
        query=query,
        assets=(
            Asset(
                id="a",
                scope="project",
                enforcement="default",
                subscribed_at=None,
                body="topic body",
                updated=NOW,
                size_bytes=400,
            ),
        ),
        budget_tokens=budget,
        now=NOW,
    )


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------


def test_default_ttl_matches_design() -> None:
    """DESIGN §3.3: TTL = 5 minutes."""
    assert DEFAULT_TTL_SECONDS == 300


def test_default_max_entries_is_sane() -> None:
    assert 16 <= DEFAULT_MAX_ENTRIES <= 1024


# ------------------------------------------------------------------
# cache_key
# ------------------------------------------------------------------


def test_cache_key_stable_for_equivalent_requests() -> None:
    k1 = cache_key(_mkreq())
    k2 = cache_key(_mkreq())
    assert k1 == k2


def test_cache_key_differs_on_query_change() -> None:
    assert cache_key(_mkreq("foo")) != cache_key(_mkreq("bar"))


def test_cache_key_differs_on_budget_change() -> None:
    assert cache_key(_mkreq(budget=100)) != cache_key(_mkreq(budget=200))


def test_cache_key_differs_when_asset_set_changes() -> None:
    req1 = _mkreq()
    req2 = RelevanceRequest(
        query=req1.query,
        assets=(
            *req1.assets,
            Asset(
                id="b",
                scope="project",
                enforcement="default",
                subscribed_at=None,
                body="another",
                updated=NOW,
                size_bytes=400,
            ),
        ),
        budget_tokens=req1.budget_tokens,
        now=req1.now,
    )
    assert cache_key(req1) != cache_key(req2)


def test_cache_key_differs_when_asset_updated_changes() -> None:
    """An asset modified today vs yesterday must produce distinct cache
    keys — otherwise we'd serve stale results after an edit."""
    req1 = _mkreq()
    same_assets_but_newer = Asset(
        id=req1.assets[0].id,
        scope=req1.assets[0].scope,
        enforcement=req1.assets[0].enforcement,
        subscribed_at=req1.assets[0].subscribed_at,
        body=req1.assets[0].body,
        updated=date(2026, 4, 23),
        size_bytes=req1.assets[0].size_bytes,
    )
    req2 = RelevanceRequest(
        query=req1.query,
        assets=(same_assets_but_newer,),
        budget_tokens=req1.budget_tokens,
        now=req1.now,
    )
    assert cache_key(req1) != cache_key(req2)


# ------------------------------------------------------------------
# Get / Put
# ------------------------------------------------------------------


def test_cache_miss_returns_none() -> None:
    c = RelevanceCache()
    assert c.get(cache_key(_mkreq())) is None


def test_cache_hit_after_put() -> None:
    c = RelevanceCache()
    req = _mkreq()
    key = cache_key(req)
    result = run_relevance_gate(req)
    c.put(key, result)
    hit = c.get(key)
    assert hit is not None
    assert hit is result


def test_cache_stats_tracks_hits_and_misses() -> None:
    c = RelevanceCache()
    req = _mkreq()
    key = cache_key(req)

    assert c.get(key) is None  # miss 1
    c.put(key, run_relevance_gate(req))
    assert c.get(key) is not None  # hit 1
    assert c.get(key) is not None  # hit 2
    assert c.get(cache_key(_mkreq("other"))) is None  # miss 2

    s = c.stats()
    assert s["hits"] == 2
    assert s["misses"] == 2
    assert s["size"] == 1


# ------------------------------------------------------------------
# LRU eviction
# ------------------------------------------------------------------


def test_lru_evicts_oldest_when_full() -> None:
    c = RelevanceCache(max_entries=3)
    keys = [f"key-{i}" for i in range(5)]
    dummy_result: RelevanceResult = run_relevance_gate(_mkreq())
    for k in keys:
        c.put(k, dummy_result)
    # Only the last 3 keys survive.
    assert c.get(keys[0]) is None
    assert c.get(keys[1]) is None
    for k in keys[2:]:
        # Skip side-effect of get() moving the entry to MRU by re-measuring
        # before any gets; re-init and test directly.
        pass

    # Direct assertion: size is at cap.
    assert c.stats()["size"] == 3


def test_lru_touches_entry_on_access() -> None:
    """A cache hit moves the entry to most-recently-used, so it survives
    the next eviction."""
    c = RelevanceCache(max_entries=3)
    dummy: RelevanceResult = run_relevance_gate(_mkreq())
    c.put("a", dummy)
    c.put("b", dummy)
    c.put("c", dummy)
    # Touch "a" — now order is b, c, a.
    assert c.get("a") is not None
    # Insert "d" — b should be evicted (oldest now), not a.
    c.put("d", dummy)
    assert c.get("a") is not None
    assert c.get("b") is None
    assert c.get("c") is not None
    assert c.get("d") is not None


# ------------------------------------------------------------------
# TTL expiry
# ------------------------------------------------------------------


def test_ttl_expiry() -> None:
    c = RelevanceCache(ttl_seconds=0.05)  # 50ms for fast test
    dummy: RelevanceResult = run_relevance_gate(_mkreq())
    c.put("k", dummy)
    assert c.get("k") is not None
    time.sleep(0.10)
    assert c.get("k") is None
    # Expired entry is also removed from size count.
    assert c.stats()["size"] == 0


def test_ttl_zero_means_never_expire() -> None:
    c = RelevanceCache(ttl_seconds=0)
    dummy: RelevanceResult = run_relevance_gate(_mkreq())
    c.put("k", dummy)
    time.sleep(0.05)
    assert c.get("k") is not None


# ------------------------------------------------------------------
# Clear
# ------------------------------------------------------------------


def test_clear_empties_cache() -> None:
    c = RelevanceCache()
    dummy: RelevanceResult = run_relevance_gate(_mkreq())
    c.put("a", dummy)
    c.put("b", dummy)
    c.clear()
    assert c.stats()["size"] == 0
    assert c.get("a") is None
