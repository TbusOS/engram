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

Metrics are averaged over the gold-set (n=10): 6 hard (paraphrase) + 4 easy
(lexical) queries.

## Results

| Date | Backend | recall@5 | recall@10 | MRR@10 | nDCG@10 | n |
|------|---------|----------|-----------|--------|---------|---|
| 2026-06-27 | none (BM25) | 0.800 | 0.800 | 0.675 | 0.706 | 10 |

Backend legend: `none` = lexical BM25 only (the zero-dependency default).
`local` (fastembed) and `remote` rows land with the semantic layer (spec §5
steps 2–5) and are recorded here + in `HISTORY.md`.

## Reading the baseline

BM25 misses the two zero-overlap paraphrase queries entirely — "throttling
abusive clients" → the rate-limit doc, and "major customer-facing outage" → the
postmortem doc — and ranks the auth doc 4th for "authenticate API requests"
(distractor docs also mention "API" / "request"). That is the headroom the
semantic layer targets: recall on paraphrase + rank precision against lexical
distractors.
