"""Retrieval metrics over a ranked list of asset ids (binary relevance).

recall@k, MRR@k, nDCG@k — pure functions, no engram / numpy dependency, so the
benchmark harness stays stdlib-only and the numbers are reproducible.

Convention: an empty ``relevant`` set scores 0.0 (a query with no labeled
answer contributes nothing rather than dividing by zero).
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant ids that appear in the top ``k`` of ``ranked``."""
    if not relevant:
        return 0.0
    top = set(ranked[:k])
    return len(top & relevant) / len(relevant)


def mrr_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Reciprocal rank of the first relevant id within the top ``k`` (else 0)."""
    for i, doc in enumerate(ranked[:k]):
        if doc in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Normalized discounted cumulative gain at ``k`` with binary relevance."""
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, doc in enumerate(ranked[:k])
        if doc in relevant
    )
    ideal_hits = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0
