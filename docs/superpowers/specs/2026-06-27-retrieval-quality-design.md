# Retrieval Quality — Design Spec

**Date:** 2026-06-27
**Status:** proposed (brainstormed with user 2026-06-27; awaiting spec review)
**Relates to:** industry-comparison gaps G-01 / G-02 / G-03 (`docs/superpowers/specs/2026-04-25-industry-comparison-and-gaps.md`), TASKS T-150r (RRF), T-151r (rerank), T-187 (LOCOMO/LongMemEval), T-41 (embedder), M4.5 benchmark infra (T-58–T-62).

---

## 1. Problem

engram's value is retrieval: surface the right memory at the right moment into the LLM context. Today that is BM25 (lexical) + scope/enforcement weighting + a crude overlap penalty (`fused_dist = dist * (1 - 0.30 * overlap)`), with the Relevance Gate's Stage 3 vector recall a no-op placeholder. There is **no external benchmark** of retrieval quality. The 1268-test suite proves the code is correct and SPEC-conformant — not that retrieval surfaces the right memory. For a memory product people rely on for years, "does it retrieve well" is the first-order quality question, and it is currently unmeasured.

This spec adds two things:

1. A **benchmark harness** so retrieval quality is measurable and only-improves (a ratchet).
2. A **pluggable semantic layer** (embeddings + cross-encoder reranking) that lifts retrieval beyond lexical matching — without breaking engram's core invariants.

## 2. Invariants preserved

- **Zero required dependency.** Base engram stays pure-stdlib + click / PyYAML / tomli. Semantic is opt-in: a local `engram[ml]` extra (fastembed / ONNX, **no torch**) or remote providers over stdlib urllib. No backend configured → BM25, no error.
- **Local-first + offline.** The default semantic backend is local and runs offline. Remote (hosted APIs) is an explicit opt-in upgrade.
- **Reproducible ratchet.** The benchmark metric must be frozen and reproducible for years. The local model is pinned by id + revision; CI runs the deterministic BM25 path; hosted models (which drift) are never the ratchet's baseline.
- **Graceful degradation, never crash.** Every semantic layer falls back to BM25 on load failure / provider error / missing dependency. The Stage 1 mandatory bypass is untouched.
- **Markdown stays source of truth.** Embeddings are a derived cache (computed on demand, cached, recomputed when stale), never the system of record. No on-disk SPEC format change.

## 3. Non-goals

- No torch / sentence-transformers in the default install (fastembed / ONNX only for the local backend).
- No `SPEC.md` change. Embeddings are a derived index, not a frontmatter field. (A graph.db embedding-cache column, if chosen, is a separate additive migration — not this spec.)
- No auto-deletion or auto-mutation of memories (unchanged).
- Not building a vector database. Embeddings cache in the existing graph.db or a sidecar and are recomputed when an asset changes.

## 4. Architecture

### 4.1 Pluggable semantic layer — `engram/relevance/semantic/`

Two interfaces, mirroring the observer's `Provider` pattern:

- `Embedder`: `embed(texts: list[str]) -> list[list[float]]`
- `Reranker`: `rerank(query: str, docs: list[str]) -> list[float]` (per-doc relevance scores)

Three backends, selected by `config.toml [relevance.semantic] backend`:

- **`none`** (default): no embedder / reranker; the gate runs BM25-only. Zero dependency, zero config.
- **`local`**: fastembed (ONNX). `bge-m3` embeddings + `bge-reranker-v2-m3` cross-encoder, pinned by id + revision. Requires `pip install engram[ml]`; absent → a clear actionable error at config-resolve.
- **`remote`**: HTTP over stdlib urllib, reusing the observer provider discipline (endpoint scheme validation, `$ENV` key expansion, no cross-host auth redirect, error taxonomy). Embeddings via ollama `/api/embeddings` or OpenAI-compatible `/v1/embeddings`; reranking via Cohere / Voyage / Jina rerank APIs.

Lazy: the model / connection initializes on first use, not at import. A runtime failure (model crash, provider unreachable) logs once and falls back to BM25 for that query.

### 4.2 Relevance Gate changes — `gate.py`

- **Stage 3 vector recall (T-41):** when an `Embedder` is active, embed the query + candidate corpus (cached) and produce a semantic ranking. No-op when `backend = none`.
- **Stage 3 fusion → RRF (T-150r):** replace `fused_dist = dist * (1 - 0.30 * overlap)` with Reciprocal Rank Fusion of the BM25 rank and the vector rank: `score(d) = Σ_i 1 / (k + rank_i(d))`, k ≈ 60. With `backend = none` there is only the BM25 channel, so RRF degrades to BM25 order — **no behavior change** for the zero-dependency path.
  - **Implemented (step 3 + calibration):** the gate stays pure — the caller computes `vector_scores` (cosine sims, embedder built once / reused) and passes them in; the gate fuses ranks. Fusion triggers only on a positive vector signal; per-channel weights (`rrf_weight_bm25` / `rrf_weight_vector`) and `rrf_k` are tunable; ties break by id. Measured on the relevance goldset (cached `bge-small-en`): BM25 `0.80/0.675/0.706` → fused `0.90/0.80/0.826`.
  - **Base scaling = harmonic rank (calibration, resolved — see §11):** RRF supplies the combined *order*; the gate then sets `base = 1/rank` so the fused relevance regains a BM25-like dynamic range. DESIGN §5.1 Stage 6 multiplies `base` by scope/enforcement/recency; against raw (compressed ~1.02x) RRF scores those multipliers dominated and flipped rankings (measured scope MRR `0.33`). Harmonic spread restores "multipliers break near-ties, relevance wins large gaps" — scope MRR `1.00`, temporal `1.00`, relevance unchanged.
- **Stage 5.5 cross-encoder rerank (T-151r):** when a `Reranker` is active, rerank the top `rerank_top_k` (default 20) candidates after Stage 5 scoring, before the Stage 6 budget pack. No-op when absent. (The gate is Stage 0→6; the rerank inserts between scoring and packing — the industry-comparison note's "Stage 7.5" was loose numbering.)
- The Stage 1 mandatory bypass, scope/enforcement weighting, temporal multiplier, and greedy budget pack are unchanged. Every new stage is a pass-through when its backend is inactive.

### 4.3 Benchmark harness + ratchet — `benchmarks/retrieval/`

- A committed, generic-example fixture store (`acme-*` names per the public-docs rule) + `goldset.jsonl`: each line `{"query": "...", "relevant": ["local/<id>", ...], "difficulty": "easy|hard"}`.
- `runner`: init the store, run the Relevance Gate per query at a fixed budget, compute **recall@{5,10}, MRR@10, nDCG@10**, averaged over the goldset.
- `BENCHMARKS.md`: the committed results table (per backend: none / local). `HISTORY.md`: one row per benchmark run — date, metric, before, after, cause — the corrections log.
- **Ratchet:** `tests/benchmarks/test_ratchet.py` runs the harness on the **BM25 (`backend = none`)** path — deterministic, no model download — and fails if any metric drops below the committed baseline minus a small tolerance. Semantic numbers (`backend = local`) are produced by a release / manual job where the model is available and recorded to `HISTORY.md`; a model-cached CI job can run the semantic ratchet later.

## 5. Sequencing (each step = one commit, each measured against §4.3)

1. **Harness + baseline.** Build §4.3 (fixture store, goldset, runner, metrics, `BENCHMARKS.md`, `HISTORY.md`, ratchet) and record the current BM25 baseline. **Zero new dependency.** The foundation — everything after is measured against it.
2. **Semantic interface + local embedder.** §4.1 interfaces + the fastembed local `Embedder` (graceful fallback). `engram[ml]` extra. Unit-tested with a deterministic stub embedder; the real model runs in the benchmark job.
3. **RRF fusion.** §4.2 Stage 3 fusion. Measure recall / MRR / nDCG delta vs the step-1 baseline (`backend = local`).
4. **Cross-encoder rerank.** §4.2 Stage 7.5 + the local `Reranker`. Measure delta (expected the largest lift).
5. **Remote backend.** §4.1 remote embedder / reranker (ollama / OpenAI-compatible / Cohere / Voyage), config-driven.
6. **LOCOMO / LongMemEval adapters.** A download script (data not committed) mapping the external datasets into the harness, for an external-credibility scoreboard in the README.

## 6. Data flow

```
query
  → Stage 1  mandatory bypass            (unchanged)
  → Stage 2  BM25 recall                 (unchanged)
  → Stage 3  vector recall (Embedder, cached) + RRF fuse   [new / changed]
  → Stage 4  temporal multiplier         (unchanged)
  → Stage 5  scope / enforcement weight  (unchanged)
  → Stage 5.5 rerank top-K (Reranker)    [new]
  → Stage 6  greedy budget pack          (unchanged)
```

Embeddings cache keyed by `asset_id + content_hash` (recompute on change), stored in graph.db or a sidecar; never the source of truth.

## 7. Error handling / degradation

- `backend = local` but `fastembed` absent → actionable error at config-resolve ("pip install engram[ml]").
- `backend = remote` misconfigured (no endpoint) → actionable config error.
- Runtime: model load crash / provider unreachable / rate-limited → log once, fall back to BM25 for that query (reuse the observer `ProviderError` taxonomy). Never crash a retrieval.
- `backend = none` → BM25, silent.

## 8. Dependencies

- `engram[ml]` (new optional extra): `fastembed` (pulls onnxruntime; **no torch**), pinned.
- Remote backends: stdlib urllib only.
- Benchmark harness: stdlib only (metrics are pure Python).

## 9. Config schema — `config.toml`

```toml
[relevance.semantic]
backend = "none"                              # none | local | remote
# local backend:
embed_model = "BAAI/bge-m3"
rerank_model = "BAAI/bge-reranker-v2-m3"
model_revision = ""                           # empty = latest; pin to a revision for a reproducible ratchet
rerank_top_k = 20
# remote backend:
embed_endpoint = "http://localhost:11434/api/embeddings"
embed_api_model = "bge-m3"
embed_api_key = "$OLLAMA_API_KEY"             # $ENV expansion, like observer providers
rerank_endpoint = ""
rerank_api_key = ""
```

## 10. Testing

- Metrics unit tests (recall / MRR / nDCG on known fixtures).
- A deterministic stub `Embedder` / `Reranker` for gate tests (RRF fusion order, rerank wiring) — **no real model in the unit suite**.
- Graceful-degradation tests (none / missing dependency / provider error → BM25).
- The ratchet test (BM25 path ≥ committed baseline).
- Dual-review (code-reviewer + security-reviewer) on the semantic layer: it adds a dependency and sends memory content to (optionally remote) models — secret leakage, SSRF on remote endpoints, `$ENV` key handling, model-download integrity.
- TDD + ruff + mypy green at each step.

## 11. Decisions made

- **Semantic signal = local-default (fastembed / ONNX), optional remote, BM25 fallback** (user, 2026-06-27). Rationale: reranking is the biggest quality lever and the canonical strong reranker is a local cross-encoder; a pinned local model keeps the ratchet reproducible; hosted APIs drift and are not local. Remote is an opt-in ceiling-raiser.
  - **Ground-truth correction (verified against installed fastembed 0.8.0):** neither `bge-m3` (embed) nor `bge-reranker-v2-m3` (rerank) is in fastembed's native model list — both need `add_custom_model` + a pinned ONNX export. Native, commercially-licensed, multilingual options are narrow: embed `intfloat/multilingual-e5-large` (MIT, 512 ctx) or `jinaai/jina-embeddings-v2-base-zh` (Apache, zh+en, 8192 ctx); rerank only `BAAI/bge-reranker-base` (MIT). `embeddinggemma-300m` is **not** native (an earlier web-research claim, disproven by inspection). So the embedding pick is now a two-path choice — **native (zero custom-ONNX) vs custom-ONNX (`bge-m3` / `gte-multilingual-base`, higher ceiling)** — decided by benchmark in CI (see §12). Given the "others install and use it" goal, prefer pure-Apache over the Gemma license.
- **First dataset = a committed self-contained gold-set** (CI-runnable, reproducible) before LOCOMO / LongMemEval (external, download-script).
- **Default backend = `none`** (predictable, no surprise model download); explicit opt-in to local / remote.
- **Fused base = harmonic rank, not raw RRF score** (2026-06-29, measured). RRF decides the combined order; `base = 1/rank` gives it BM25-like spread so DESIGN §5.1's multiplicative scope/enforcement/recency compose as intended. Chosen over raw-RRF (scope MRR 0.33), normalized weighted-score (0.49), and a BM25-value remap (1.00 but distribution-dependent); harmonic tied best (1.00) and is the simplest + most deterministic. Calibration goldset: 10 relevance + 3 scope + 2 temporal queries, mixed scope/date.

## 12. Open questions (non-blocking; decided at the step that needs them)

- Embedding cache location: graph.db column vs sidecar file. Decide at step 2 (additive either way, no SPEC change).
- nDCG gain formula and k values — finalize at step 1 with the goldset.
- RRF k constant (60 is standard) — tune at step 3 against the goldset.
- ~~RRF × Stage-5 multiplier composition (found in step-3 review)~~ **RESOLVED 2026-06-29 (§11): harmonic-rank base.** Extended the goldset with a 5-query calibration set (`goldset_calibration.jsonl`: 3 scope + 2 temporal, mixed scope/date), measured five base-scaling options through the real gate, and chose `base = 1/rank` (scope MRR 0.33→1.00, temporal →1.00, relevance unchanged). The fused path is now correct; caller wiring is unblocked.
- **Fused exact-relevance tie at the rank-1/2 boundary (step-3 review MEDIUM, address at caller-wiring):** harmonic's top gap (1.0 vs 0.5 = 2×) exceeds the largest scope ratio (project/org = 1.875), so two *exactly* equally-relevant docs differing only in scope are ordered by the RRF `id` tiebreak, not scope, at the very top pair (scope does break ties at deeper ranks). Low impact (exact top ties are rare; no caller passes `vector_scores` yet). Fix options to decide with the CI model: a scope/enforcement-aware tiebreak inside the fused order, or a gentler harmonic offset `1/(rank+c)` tuned so the top ratio sits under 1.875 without re-introducing scope domination. Pick by measuring on the calibration set with the production model.
- **Embedding model pick — native vs custom-ONNX** (see §11 ground-truth note): benchmark `multilingual-e5-large` / `jina-v2-base-zh` (native) against `bge-m3` / `gte-multilingual-base` (custom-ONNX) on the goldset in CI; pick by recall/MRR/nDCG, breaking ties toward pure-Apache license + smaller footprint. The reranker (`bge-reranker-v2-m3`, custom-ONNX) is already the best-fit; `bge-reranker-base` is the native fallback.
- **`rrf_k` / weight validation at the config boundary** (security review): `rrf_k >= 1`, weights finite and `>= 0` — enforce in the `[relevance.semantic]` config parser, not the gate, when the knobs become user-configurable.
