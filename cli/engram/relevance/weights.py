"""Scope + enforcement weight tables used by the Relevance Gate (T-40).

Extracted from ``engram.commands.memory`` so the Relevance Gate can
import the constants without triggering click's command registration
chain (which imports every subcommand and hits a circular import when
the Gate also wants these numbers).

The ``engram.commands.memory`` module still re-exports these names for
backward compatibility with existing callers and tests written against
``from engram.commands.memory import SCOPE_WEIGHTS``.
"""

from __future__ import annotations

__all__ = [
    "ENFORCEMENT_WEIGHTS",
    "SCOPE_WEIGHTS",
    "apply_scope_weighting",
]


# Scope weighting per DESIGN §5.1 Stage 6. Project is the most specific
# hierarchy level and therefore the most authoritative; org is the
# broadest and therefore the most conservative.
SCOPE_WEIGHTS: dict[str, float] = {
    "project": 1.5,
    "user": 1.2,
    "team": 1.0,
    "org": 0.8,
    "pool": 1.0,  # default baseline when subscribed_at is not resolvable
}

# Enforcement weighting (M3 subset of T-38). The Relevance Gate's
# Stage-1 mandatory bypass supersedes this multiplier at query time;
# ``engram memory search`` still uses the multiplier so every result
# line is in a single sorted ranking.
ENFORCEMENT_WEIGHTS: dict[str, float] = {
    "mandatory": 2.0,
    "default": 1.0,
    "hint": 0.5,
}


def apply_scope_weighting(
    ranked: list[tuple[str, float]],
    meta: dict[str, tuple[str, str, str | None]],
) -> list[tuple[str, float]]:
    """Fold scope + enforcement multipliers into a BM25 ranking.

    See :mod:`engram.commands.memory` for the original docstring — this
    is the canonical implementation; the ``memory`` module re-exports it.
    """
    out: list[tuple[str, float]] = []
    for doc_id, raw in ranked:
        scope, enforcement, subscribed_at = meta.get(doc_id, ("project", "default", None))
        if scope == "pool" and subscribed_at in SCOPE_WEIGHTS:
            scope_weight = SCOPE_WEIGHTS[subscribed_at]
        else:
            scope_weight = SCOPE_WEIGHTS.get(scope, 1.0)
        enf_weight = ENFORCEMENT_WEIGHTS.get(enforcement, 1.0)
        out.append((doc_id, raw * scope_weight * enf_weight))
    out.sort(key=lambda x: x[1], reverse=True)
    return out
