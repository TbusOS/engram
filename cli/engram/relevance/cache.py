"""Relevance Gate result cache (T-45, DESIGN §3.3).

Thin LRU + TTL wrapper around :func:`engram.relevance.gate.run_relevance_gate`.
The gate itself stays pure; the cache is a separate object operators
pass in when they want it. This matches DESIGN §3.3 intent:

- **Cache key** includes query, budget, and a fingerprint of the asset
  set (IDs + updated dates). Editing an asset invalidates any cached
  result that used it — no stale hits.
- **TTL** defaults to 300 seconds (5 minutes). The Relevance Gate's
  inputs can change in ways the cache key does not catch (a subscribed
  pool advancing ``rev/current`` under a symlink, for example). A
  short TTL bounds how long a stale hit can live.
- **LRU** bounds memory. Default 128 entries is generous for a
  single-user store; callers can shrink it when embedding a cache into
  a server process.

No locking: the CLI is single-threaded per invocation. If a future
server-mode driver needs thread safety, wrap the cache in an
``asyncio.Lock`` or move to a queue.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from engram.relevance.gate import RelevanceRequest, RelevanceResult

__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "DEFAULT_TTL_SECONDS",
    "RelevanceCache",
    "cache_key",
]


DEFAULT_TTL_SECONDS: float = 300.0
DEFAULT_MAX_ENTRIES: int = 128


def cache_key(request: RelevanceRequest) -> str:
    """Derive a stable cache key from ``request``.

    The key is sensitive to everything that would change the gate's
    output: the query string, the budget, and the *shape* of the asset
    set (IDs + ``updated`` dates + enforcement + scope). The ``body``
    text is NOT mixed into the key directly — we assume a meaningful
    body edit also bumps ``updated``. This is the same invariant the
    SPEC §13 migration logic relies on.
    """
    fp = hashlib.sha256()
    fp.update(request.query.encode("utf-8", errors="replace"))
    fp.update(b"\0")
    fp.update(str(request.budget_tokens).encode("ascii"))
    fp.update(b"\0")
    fp.update(request.now.isoformat().encode("ascii"))
    fp.update(b"\0")
    for a in sorted(request.assets, key=lambda x: x.id):
        fp.update(a.id.encode("utf-8"))
        fp.update(b"|")
        fp.update(a.scope.encode("utf-8"))
        fp.update(b"|")
        fp.update(a.enforcement.encode("utf-8"))
        fp.update(b"|")
        fp.update((a.subscribed_at or "").encode("utf-8"))
        fp.update(b"|")
        fp.update(a.updated.isoformat().encode("ascii"))
        fp.update(b"|")
        fp.update(str(a.size_bytes).encode("ascii"))
        fp.update(b"\n")
    return fp.hexdigest()


class RelevanceCache:
    """LRU + TTL cache for Relevance Gate results.

    Single-process use; no locking. Instantiate once per CLI invocation
    or per long-running server. The cache has no persistence — hits only
    within the process lifetime.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, RelevanceResult]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> RelevanceResult | None:
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1
            return None
        stored_at, result = entry
        if self._ttl > 0 and (time.monotonic() - stored_at) > self._ttl:
            # Expired — evict on read so stats reflect the current state.
            del self._data[key]
            self._misses += 1
            return None
        # LRU touch.
        self._data.move_to_end(key)
        self._hits += 1
        return result

    def put(self, key: str, value: RelevanceResult) -> None:
        now = time.monotonic()
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (now, value)
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)  # drop oldest

    def clear(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._data),
            "max_entries": self._max_entries,
        }
