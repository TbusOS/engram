"""Retrieval ratchet — the committed BM25 baseline must not regress.

Frozen floors (BM25, backend=none) from `benchmarks/BENCHMARKS.md`, 2026-06-27.
A change that drops retrieval below these fails the suite. The path is
deterministic (no model download), so it runs in normal CI. Semantic backends
are scored in a separate model-available job and tracked in
`benchmarks/HISTORY.md`.

When a real improvement lands, raise the floors here and add a HISTORY.md row —
the ratchet only moves up.
"""

from __future__ import annotations

from pathlib import Path

from engram.benchmark.runner import run_retrieval_benchmark

_ROOT = Path(__file__).resolve().parents[2]
_STORE = _ROOT / "benchmarks" / "retrieval" / "store"
_GOLD = _ROOT / "benchmarks" / "retrieval" / "goldset.jsonl"

# Frozen baseline — BM25 (backend = none). Only-improve.
_FLOOR_RECALL_AT_5 = 0.80
_FLOOR_RECALL_AT_10 = 0.80
_FLOOR_MRR_AT_10 = 0.675
_FLOOR_NDCG_AT_10 = 0.706


def test_bm25_baseline_does_not_regress() -> None:
    rep = run_retrieval_benchmark(_STORE, _GOLD)
    assert rep.n_queries == 10
    assert rep.recall_at_5 >= _FLOOR_RECALL_AT_5
    assert rep.recall_at_10 >= _FLOOR_RECALL_AT_10
    assert rep.mrr_at_10 >= _FLOOR_MRR_AT_10
    assert rep.ndcg_at_10 >= _FLOOR_NDCG_AT_10
