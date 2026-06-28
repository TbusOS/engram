# Retrieval Benchmarks

Retrieval quality of the Relevance Gate over a committed gold-set
(`benchmarks/retrieval/`) — so quality is a number that only improves, not a
vibe. Design: `docs/superpowers/specs/2026-06-27-retrieval-quality-design.md`.

Reproduce with the ratchet test `tests/benchmarks/test_ratchet.py`, or:

```python
from pathlib import Path
from engram.benchmark.runner import run_retrieval_benchmark
print(run_retrieval_benchmark(Path("benchmarks/retrieval/store"),
                              Path("benchmarks/retrieval/goldset.jsonl")))
```

Two gold-sets over one 18-doc store:

- **relevance** (`goldset.jsonl`, n=10): 6 hard (paraphrase) + 4 easy (lexical).
- **calibration** (`goldset_calibration.jsonl`, n=5): 3 scope + 2 temporal
  queries over docs that vary scope (org/user/project) and date — exercises the
  Stage-5 multiplier composition the relevance set's uniform docs cannot.

## Results

| Date | Gold-set | Backend | recall@5 | recall@10 | MRR@10 | nDCG@10 | n |
|------|----------|---------|----------|-----------|--------|---------|---|
| 2026-06-29 | relevance | none (BM25) | 0.800 | 0.800 | 0.670 | 0.702 | 10 |
| 2026-06-29 | relevance | local (proxy) | 0.900 | 0.900 | 0.750 | 0.789 | 10 |
| 2026-06-29 | calibration | none (BM25) | 0.600 | 0.600 | 0.500 | 0.526 | 5 |
| 2026-06-29 | calibration | local (proxy) | 0.600 | 0.600 | 0.600 | 0.600 | 5 |
| 2026-06-27 | relevance | none (BM25, 12-doc) | 0.800 | 0.800 | 0.675 | 0.706 | 10 |

Backend: `none` = lexical BM25 only (zero-dependency default; the ratchet floor).
`local (proxy)` = a preview measured with the cached `bge-small-en-v1.5`
(English, dev only) to size the lift — **not** the production model and **not**
the official semantic floor; the CI model-available job sets that (spec §5). The
2026-06-27 row is the pre-expansion 12-doc baseline, kept for history.

## Reading the baselines

**Relevance** — BM25 misses the two zero-overlap paraphrase queries entirely
("throttling abusive clients" → rate-limit doc; "major customer-facing outage" →
postmortem doc) and ranks the auth doc 4th against lexical distractors. The
semantic layer recovers both (recall 0.80→0.90, MRR 0.67→0.75).

**Calibration** — scope queries check that a more-relevant low-scope (org, 0.8)
doc still beats a less-relevant high-scope (project, 1.5) distractor, and that
project wins genuine near-ties; temporal queries check the recency boost. These
proved the fused-base calibration (harmonic rank: raw-RRF scope MRR 0.33 → 1.00).
BM25 leaves headroom (0.50 MRR) the semantic layer lifts.
