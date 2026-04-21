"""SPEC §8.4 conflict-resolution decision tree — pure implementation.

This module encodes the five decision rules from SPEC §8.4 as a single
pure function. ``engram validate`` uses it to surface E-ENF-001 errors
(M4 work); ``engram review`` uses it to surface rule-4 LLM-arbitration
warnings; the M4 Relevance Gate uses it for deterministic ranking when
two assets collide on the same topic.

The function has no side effects — no file IO, no git, no DB — so it is
trivially testable (see ``tests/unit/cli/test_scope_conflict.py``). All
context that could influence the decision is passed in through the
``ConflictCandidate`` dataclass.

Rule ordering (apply in order, stop at the first that decides a winner):

1. **Enforcement absolute priority.** ``mandatory`` > ``default`` > ``hint``.
   When the candidate set contains assets at multiple enforcement
   levels, every asset at a lower level is eliminated before any
   hierarchy comparison runs.
2. **Hierarchy specificity.** ``project > user > team > org``. Pool
   assets use their ``subscribed_at`` value as the effective level.
3. **Native-before-pool tiebreaker.** When a native asset and a pool
   asset tie on both enforcement and effective hierarchy, the native
   asset wins (SPEC §8.4 rule 3).
4. **LLM arbitration.** Two or more remaining candidates with the same
   enforcement and the same effective hierarchy but different sources
   cannot be resolved deterministically. The function returns
   ``winner=None`` with ``rule=4`` and the caller loads both assets
   into context.
5. **Pool internal conflict.** Two candidates from the same pool
   contradict each other. Raise :class:`PoolInternalConflict` — the
   pool maintainer must fix the pool before subscribers can resolve it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "ConflictCandidate",
    "PoolInternalConflict",
    "Resolution",
    "resolve_conflict",
]


_ENFORCEMENT_RANK: dict[str, int] = {"mandatory": 2, "default": 1, "hint": 0}
_HIERARCHY_RANK: dict[str, int] = {"project": 3, "user": 2, "team": 1, "org": 0}


@dataclass(frozen=True, slots=True)
class ConflictCandidate:
    """One side of a conflict, as fed into :func:`resolve_conflict`.

    All fields are required — the caller is responsible for reading them
    from the asset frontmatter (or from the subscriber's ``pools.toml``
    for ``subscribed_at``).

    - ``id``: asset identifier (e.g. ``local/feedback_x``,
      ``team/platform/feedback_x``, ``pools/kernel-work/feedback_y``).
    - ``scope``: one of ``project / user / team / org / pool``.
    - ``enforcement``: one of ``mandatory / default / hint``.
    - ``subscribed_at``: only for ``scope == "pool"``. The effective
      hierarchy level at which the subscriber pulls this pool. When
      missing (malformed subscription), the asset is treated as
      ``org``-level — the least specific — so a misconfigured pool
      can't accidentally outrank native content.
    - ``source``: opaque string used for Rule 4 ("different sources →
      LLM arbitrates"). Two candidates with the same ``source`` are
      treated as coming from the same owner (Rule 5 territory).
    """

    id: str
    scope: str
    enforcement: str
    subscribed_at: str | None
    source: str


@dataclass(frozen=True, slots=True)
class Resolution:
    """Outcome of a conflict check.

    - ``winner``: the id of the asset that should be preferred, or
      ``None`` when Rule 4 fires (LLM arbitrates).
    - ``losers``: every input id that did not win.
    - ``rule``: which §8.4 rule fired (``1`` / ``2`` / ``3`` / ``4``);
      ``0`` means the input had exactly one candidate (no conflict).
    - ``reason``: human-readable one-liner for ``engram review`` /
      validation output.
    """

    winner: str | None
    losers: tuple[str, ...]
    rule: int
    reason: str = field(default="")


class PoolInternalConflict(Exception):
    """Two candidates from the same pool contradict each other (Rule 5)."""

    def __init__(self, pool_source: str, ids: Sequence[str]) -> None:
        super().__init__(
            f"pool {pool_source!r} has internal conflict between: "
            + ", ".join(sorted(ids))
        )
        self.pool_source = pool_source
        self.ids = tuple(ids)


def _effective_level(cand: ConflictCandidate) -> int:
    """Map a candidate's (scope, subscribed_at) to a hierarchy rank."""
    if cand.scope == "pool":
        level = cand.subscribed_at or "org"
        return _HIERARCHY_RANK.get(level, 0)
    return _HIERARCHY_RANK.get(cand.scope, 0)


def resolve_conflict(candidates: Sequence[ConflictCandidate]) -> Resolution:
    """Apply SPEC §8.4 rules 1-5 to a set of conflicting candidates.

    :raises ValueError: when ``candidates`` is empty.
    :raises PoolInternalConflict: when two candidates share a
        pool-valued ``source`` (SPEC §8.4 rule 5).
    """
    if not candidates:
        raise ValueError("resolve_conflict requires at least one candidate")

    cands = list(candidates)

    # Rule 0 — single-candidate short-circuit.
    if len(cands) == 1:
        return Resolution(
            winner=cands[0].id,
            losers=(),
            rule=0,
            reason="single candidate",
        )

    # Rule 5 — same-pool internal conflict. We detect any two candidates
    # whose source starts with "pool/" and matches exactly. This is a
    # maintainer-side bug; subscribers cannot resolve it locally.
    pool_sources: dict[str, list[str]] = {}
    for c in cands:
        if c.source.startswith("pool/"):
            pool_sources.setdefault(c.source, []).append(c.id)
    for src, ids in pool_sources.items():
        if len(ids) > 1:
            raise PoolInternalConflict(src, ids)

    all_ids = tuple(c.id for c in cands)

    # Rule 1 — drop everything below the strongest enforcement.
    top_enf_rank = max(_ENFORCEMENT_RANK.get(c.enforcement, -1) for c in cands)
    stage1 = [c for c in cands if _ENFORCEMENT_RANK.get(c.enforcement, -1) == top_enf_rank]

    if len(stage1) == 1:
        winner = stage1[0]
        return Resolution(
            winner=winner.id,
            losers=tuple(i for i in all_ids if i != winner.id),
            rule=1,
            reason=(
                f"{winner.enforcement} beats lower-enforcement candidates "
                f"(SPEC §8.4 rule 1)"
            ),
        )

    # Rule 2 — within the top enforcement level, most-specific hierarchy wins.
    top_hier_rank = max(_effective_level(c) for c in stage1)
    stage2 = [c for c in stage1 if _effective_level(c) == top_hier_rank]

    if len(stage2) == 1:
        winner = stage2[0]
        return Resolution(
            winner=winner.id,
            losers=tuple(i for i in all_ids if i != winner.id),
            rule=2,
            reason=(
                f"most-specific hierarchy ({winner.scope}) wins at "
                f"{winner.enforcement} level (SPEC §8.4 rule 2)"
            ),
        )

    # Rule 3 — native-before-pool tiebreaker. When the survivors include
    # both native (non-pool) and pool candidates at the same effective
    # level, drop the pool candidates.
    natives = [c for c in stage2 if c.scope != "pool"]
    pools_only = [c for c in stage2 if c.scope == "pool"]
    if natives and pools_only:
        stage3 = natives
        rule_num = 3
        reason_prefix = "native beats pool at the same effective level"
    else:
        stage3 = stage2
        rule_num = 2
        reason_prefix = ""

    if len(stage3) == 1:
        winner = stage3[0]
        return Resolution(
            winner=winner.id,
            losers=tuple(i for i in all_ids if i != winner.id),
            rule=rule_num,
            reason=f"{reason_prefix} (SPEC §8.4 rule 3)" if rule_num == 3 else "",
        )

    # Rule 4 — LLM arbitrates. Two or more survivors with identical
    # enforcement + effective level + all non-pool (or all pool at same
    # level from different pools). No deterministic winner.
    return Resolution(
        winner=None,
        losers=tuple(c.id for c in stage3),
        rule=4,
        reason=(
            f"{len(stage3)} candidates tied at {stage3[0].enforcement} / "
            f"effective hierarchy rank {top_hier_rank} — LLM arbitrates "
            "(SPEC §8.4 rule 4)"
        ),
    )
