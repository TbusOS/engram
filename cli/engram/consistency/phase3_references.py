"""Phase 3 — reference-graph health checks.

M4 stub. Full implementation (transitive supersedes, circular overrides,
pool cross-reference graph) lands in a post-M4 refinement.
"""

from __future__ import annotations

from pathlib import Path

from engram.consistency.types import ConflictReport

__all__ = ["detect_phase3"]


def detect_phase3(store_root: Path) -> list[ConflictReport]:
    """Return an empty list for now.

    Phase 1 already catches broken references via ``E-REF-001`` /
    ``E-REF-003``. Phase 3's additional value is *transitive* graph
    analysis — circular supersedes chains, dangling overrides across
    scopes, pool → project reference graphs. That requires the full
    cross-scope reader which M5 lands.
    """
    _ = store_root  # reserved
    return []
