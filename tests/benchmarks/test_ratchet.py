"""Retrieval ratchet — the committed BM25 baseline must not regress.

Frozen floors (BM25, backend=none). A change that drops retrieval below these
fails the suite. The path is deterministic (no model download), so it runs in
normal CI. Semantic backends are scored in a separate model-available job and
tracked in `benchmarks/HISTORY.md`.

Two gold-sets over one 18-doc store:

- **relevance** (`goldset.jsonl`, 10 queries) — lexical + paraphrase recall;
  this is the BM25→semantic headroom set.
- **calibration** (`goldset_calibration.jsonl`, 5 queries) — scope + temporal
  queries that exercise the Stage-5 multiplier composition (DESIGN §5.1 Stage 6).
  Uniform-scope/date docs cannot test this; the calibration docs vary both.

When a real improvement lands, raise the floors here and add a HISTORY.md row —
the ratchet only moves up. Expanding a gold-set is a deliberate re-baseline
(documented in HISTORY.md), not a regression.
"""

from __future__ import annotations

from pathlib import Path

from engram.benchmark.runner import run_retrieval_benchmark

_ROOT = Path(__file__).resolve().parents[2]
_STORE = _ROOT / "benchmarks" / "retrieval" / "store"
_GOLD_RELEVANCE = _ROOT / "benchmarks" / "retrieval" / "goldset.jsonl"
_GOLD_CALIBRATION = _ROOT / "benchmarks" / "retrieval" / "goldset_calibration.jsonl"

# Frozen BM25 (backend = none) floors over the 18-doc store. Only-improve.
# Relevance: re-baselined 2026-06-29 (12->18 docs added 6 calibration distractors;
# MRR 0.675->0.670, nDCG 0.706->0.702). See benchmarks/HISTORY.md.
_FLOOR_REL_RECALL_AT_5 = 0.80
_FLOOR_REL_RECALL_AT_10 = 0.80
_FLOOR_REL_MRR_AT_10 = 0.67
_FLOOR_REL_NDCG_AT_10 = 0.70

# Calibration: BM25 leaves headroom here (scope/temporal need the semantic layer
# + multipliers); the semantic job is expected to lift these.
_FLOOR_CAL_RECALL_AT_5 = 0.60
_FLOOR_CAL_RECALL_AT_10 = 0.60
_FLOOR_CAL_MRR_AT_10 = 0.50
_FLOOR_CAL_NDCG_AT_10 = 0.52


def test_bm25_relevance_does_not_regress() -> None:
    rep = run_retrieval_benchmark(_STORE, _GOLD_RELEVANCE)
    assert rep.n_queries == 10
    assert rep.recall_at_5 >= _FLOOR_REL_RECALL_AT_5
    assert rep.recall_at_10 >= _FLOOR_REL_RECALL_AT_10
    assert rep.mrr_at_10 >= _FLOOR_REL_MRR_AT_10
    assert rep.ndcg_at_10 >= _FLOOR_REL_NDCG_AT_10


def test_bm25_calibration_does_not_regress() -> None:
    rep = run_retrieval_benchmark(_STORE, _GOLD_CALIBRATION)
    assert rep.n_queries == 5
    assert rep.recall_at_5 >= _FLOOR_CAL_RECALL_AT_5
    assert rep.recall_at_10 >= _FLOOR_CAL_RECALL_AT_10
    assert rep.mrr_at_10 >= _FLOOR_CAL_MRR_AT_10
    assert rep.ndcg_at_10 >= _FLOOR_CAL_NDCG_AT_10
