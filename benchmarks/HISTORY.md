# Benchmark History

One row per benchmark run: date, metric, before → after, cause. The corrections
log behind the retrieval ratchet (`benchmarks/BENCHMARKS.md`). Newest first.

| Date | Metric (recall@5 / recall@10 / MRR@10 / nDCG@10) | Before | After | Cause |
|------|--------------------------------------------------|--------|-------|-------|
| 2026-06-29 | relevance, BM25 | 0.800 / 0.800 / 0.675 / 0.706 | 0.800 / 0.800 / 0.670 / 0.702 | Re-baseline: store 12→18 docs (added 6 scope/date-varied calibration distractors). Tiny relevance drop is the extra distractors, not a retrieval regression. |
| 2026-06-29 | calibration, BM25 | — | 0.600 / 0.600 / 0.500 / 0.526 | New 5-query calibration gold-set (3 scope + 2 temporal) for the Stage-5 multiplier composition. BM25 floor; the semantic layer lifts it. |
| 2026-06-29 | fused base = harmonic rank (calibration decision) | scope MRR 0.33 (raw RRF) | scope MRR 1.00 | Resolved the step-3 review HIGH: RRF for the order, base = 1/rank so DESIGN §5.1 multipliers compose. Measured on the calibration set; chosen over weighted-score (0.49) and BM25-remap (1.00 but distribution-dependent). |
| 2026-06-29 | relevance + calibration, local (bge-small-en proxy) | BM25 above | rel 0.900/0.900/0.750/0.789 · cal 0.600/0.600/0.600/0.600 | Preview lift with the dev-cached English model (not the production model / official floor; CI sets that). Sizes the headroom: relevance recall +0.10, MRR +0.08. |
| 2026-06-27 | relevance, BM25 (12-doc) | — | 0.800 / 0.800 / 0.675 / 0.706 | Baseline: BM25 (backend=none) over the original 10-query / 12-doc gold-set. Harness + ratchet established (retrieval-quality spec §5 step 1). |
