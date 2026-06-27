"""Unit tests for engram.benchmark.metrics — recall@k / MRR@k / nDCG@k."""

from __future__ import annotations

import math

from engram.benchmark.metrics import mrr_at_k, ndcg_at_k, recall_at_k


def test_recall_at_k() -> None:
    ranked = ["a", "b", "c", "d"]
    rel = {"a", "c"}
    assert recall_at_k(ranked, rel, 1) == 0.5  # [a] -> {a}
    assert recall_at_k(ranked, rel, 2) == 0.5  # [a,b] -> {a}
    assert recall_at_k(ranked, rel, 3) == 1.0  # [a,b,c] -> {a,c}


def test_recall_empty_relevant_is_zero() -> None:
    assert recall_at_k(["a"], set(), 1) == 0.0


def test_mrr_at_k() -> None:
    assert mrr_at_k(["b", "a", "c"], {"a", "c"}, 10) == 0.5  # first rel at pos 2
    assert mrr_at_k(["a", "b"], {"a"}, 10) == 1.0
    assert mrr_at_k(["x", "y"], {"a"}, 10) == 0.0
    assert mrr_at_k(["x", "a"], {"a"}, 1) == 0.0  # a is at pos 2, k=1 misses


def test_ndcg_at_k() -> None:
    ranked = ["a", "b", "c"]
    rel = {"a", "c"}
    dcg = 1.0 / math.log2(2) + 0.0 + 1.0 / math.log2(4)
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    assert math.isclose(ndcg_at_k(ranked, rel, 3), dcg / idcg, rel_tol=1e-9)


def test_ndcg_perfect_ranking_is_one() -> None:
    assert ndcg_at_k(["a", "b", "c"], {"a"}, 3) == 1.0


def test_ndcg_empty_relevant_is_zero() -> None:
    assert ndcg_at_k(["a"], set(), 2) == 0.0
