# Benchmark History

One row per benchmark run: date, metric, before → after, cause. The corrections
log behind the retrieval ratchet (`benchmarks/BENCHMARKS.md`). Newest first.

| Date | Metric (recall@5 / recall@10 / MRR@10 / nDCG@10) | Before | After | Cause |
|------|--------------------------------------------------|--------|-------|-------|
| 2026-06-27 | recall@5 / recall@10 / MRR@10 / nDCG@10 | — | 0.800 / 0.800 / 0.675 / 0.706 | Baseline: BM25 (backend=none) over the new 10-query gold-set. Harness + ratchet established (retrieval-quality spec §5 step 1). |
