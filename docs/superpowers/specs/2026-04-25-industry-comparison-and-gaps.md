# Industry Comparison + Retrieval/Memory Gaps — engram v0.2

**Status:** draft, 2026-04-25
**Owner:** maintainer
**Source:** session review with the user, 2026-04-25 (web research +
read-through of `SPEC.md` / `DESIGN.md` / `TASKS.md`)
**Related memory:** `project_engram_quality_bar.md`,
`feedback_no_compromise_on_this_project.md`

---

## 0. Why this doc exists

The user asked: "对照业界主流方案,engram 设计是否完善?"
This doc records the answer so it does not get lost in chat history.
It captures (a) what 8 reference systems do, (b) what engram does
uniquely well, (c) what is missing, and (d) which gaps to close in
which milestone. It is written so that a future LLM session can pick
this up cold and start work.

This is **not** a spec change. SPEC.md / DESIGN.md remain authoritative.
Items below that imply a spec amendment are flagged `[SPEC-AMEND]`;
those need a separate PR against SPEC.md before implementation.

---

## 1. Reference systems surveyed (2026-04 snapshot)

| System | Storage | Retrieval | Conflict handling | Compression / forgetting | Multi-tenant | Notable |
|---|---|---|---|---|---|---|
| **mem0** (mem0ai/mem0) | vector + graph + KV (3-store) | hybrid; LLM decides ADD/UPDATE/DELETE/NOOP at write | LLM one-shot at write | selective token pipeline (<7k tokens) | `user_id / agent_id / run_id` 3-level namespace | LOCOMO 91.6, p95 1.44s, 90% token saving claim. arXiv 2504.19413 |
| **Zep / Graphiti** (getzep/graphiti) | temporal knowledge graph; bi-temporal edges (`t_valid` × `t_invalid`) | semantic + BM25 + graph traversal, **no LLM at retrieval time** | edge invalidation via t_invalid | community summaries (Episode → Semantic → Community) | per-user graph | LOCOMO 94.8 claim disputed (replication 58.4) — arXiv 2501.13956 |
| **Letta / MemGPT** (letta-ai/letta) | core (in-context) + recall (full history) + archival (vector/graph) | agent calls page tools to search archival; recall is keyword | agent edits core memory blocks via tools | recall→archival demotion when stale | `.af` file serializes whole agent | virtual-memory metaphor for LLMs |
| **LangMem** (LangChain) | LangGraph store (pluggable backend) | per-namespace fetch | upsert | none built-in | namespace-based | explicit semantic / episodic / procedural typology |
| **A-MEM** (agiresearch/a-mem) | text + auto-linked notes | similarity over generated context+keywords+tags | new note backflows metadata into older linked notes | none | single-store | Zettelkasten dynamic network — arXiv 2502.12110 |
| **Cognee** (topoteretes/cognee) | graph (Kuzu) + vector (LanceDB) + relational (SQLite) | ECL pipeline (Extract-Cognify-Load) replaces RAG | `memify` step prunes / re-weights / derives | `memify` self-refinement | per-user dataset | LLM extracts entities/relations on write |
| **Anthropic Claude memory tool** (`memory_20250818`, 2025-09) | client-side `/memories/` markdown directory | model uses `view` then chooses files | model-driven; no engine | none built-in; relies on session compaction | client-managed | 6 file ops: view/create/str_replace/insert/delete/rename. Storage philosophy aligns with engram |
| **MemMachine v0.2** | 5-layer context stack | BM25 + vector + memory graph + user profile + temporal, RRF fusion | layer-specific | configurable | per-user | Top LOCOMO score on public leaderboard, 2025-12 |

**Industry consensus on retrieval (2025–2026):**

1. **Hybrid > vector-only > BM25-only.** Recall@10 ≈ 91% hybrid vs ≈ 65% BM25 alone on LOCOMO-class workloads.
2. **RRF (Reciprocal Rank Fusion) is the default fusion algorithm.** Score-distribution-agnostic; no tuning.
3. **Cross-encoder rerank (e.g. bge-reranker-v2-m3) on top-K candidates is the single biggest precision win** — 22–37% hallucination reduction reported across multiple studies.
4. **Bi-temporal time models are becoming standard** for any system that promises auditability.
5. **Active compaction** (LLM-summarised packed context) beats passive recency decay for context-budget control.

---

## 2. engram's unique strengths (defensible vs the field)

These are the bets that should not be diluted while closing gaps.

1. **"Markdown contract is permanent, intelligence layer is throwaway cache."**
   Every other system binds you to a storage engine (mem0 → 3 stores; Zep → Neo4j; Cognee → Kuzu+LanceDB; Letta → `.af`).
   engram is the only system where the on-disk YAML+markdown is the contract and `graph.db` / vector cache can be deleted and rebuilt.
   This aligns with Anthropic's memory tool philosophy but goes further with frontmatter schema.

2. **Two-axis scope model + 3-level enforcement.**
   `org > team > user > project` × pool subscription × `mandatory / default / hint`.
   No surveyed system can express "company-mandated compliance + team default + personal preference + topic-pool subscription" in one query.
   Most systems are flat or have global/user/session only.

3. **Workflow as a first-class asset.**
   Spine + fixtures + metrics.yaml + rev/ history.
   mem0/Zep/Letta/LangMem only manage facts and preferences. LangMem's "procedural" memory is just prompt updates. Agent Factory papers describe "experience as executable code" but do not provide a file format. engram does.

4. **7-class conflict taxonomy in the Consistency Engine.**
   `factual-conflict` / `rule-conflict` / `reference-rot` / `workflow-decay` / `time-expired` / `silent-override` / `topic-divergence`.
   mem0 collapses everything into "LLM decides ADD/UPDATE/DELETE" — fast but unauditable. engram's split is auditable and operator-actionable.

5. **"Never auto-rewrite, never auto-delete" invariant + 6-month archive floor.**
   mem0 LLM can DELETE silently; Cognee `memify` can prune nodes. engram's hard rule that every change must flow through `engram review` is an engineering trust-credibility choice.

6. **Wisdom Metrics — 4 quantified curves, not vibes.**
   workflow mastery / task recurrence efficiency / memory curation ratio / context efficiency. No surveyed system makes "the assistant got smarter" a falsifiable, plottable, CI-alertable claim.

7. **Cross-repo inbox** (`~/.engram/inbox/<repo-id>/`).
   Repo-to-repo structured messaging. Nobody else does this. Useful for "SDK + upstream consumer repo" pairs.

8. **LLM-agnostic + MCP-native + multi-adapter** (Claude Code / Codex / Gemini / Cursor / raw-api).
   Most competitors ship a proprietary SDK first. engram is genuinely tool-agnostic.

These are the moats. **Do not erode them when adding features below.**

---

## 3. Gaps vs the industry (where engram is currently behind)

Each gap below has a severity, a milestone target, and a concrete file/section to touch. Severity follows TASKS.md priorities: P0 = blocks public credibility; P1 = visible competitor advantage; P2 = nice-to-have.

### G-01 Vector retrieval is not a first-class recall path **[P0]**
- **Status today:** DESIGN §5.1 mentions vector + bge-reranker + sqlite-vss, but the offline path falls back to BM25-only. The 7-stage Relevance Gate pipeline does not RRF-fuse vector / BM25 / structural results consistently.
- **Industry baseline:** hybrid recall@10 ≈ 91% vs BM25 ≈ 65%.
- **Touch point:** `cli/engram/relevance/gate.py` Stage 3 fusion — replace `fused_dist = dist * (1.0 - 0.30 * overlap)` with RRF.
- **Why P0:** without this, every reviewer who runs LOCOMO/LongMemEval will discount engram on numbers regardless of design merits.

### G-02 No cross-encoder rerank stage **[P0]**
- **Status today:** Stage 6 applies scope weights; that is not a true rerank.
- **Industry baseline:** RRF + cross-encoder rerank is the standard. Rerank delivers the largest single-stage precision gain.
- **Touch point:** add Stage 7.5 rerank step after candidate set is reduced to top-20. Reuse bge-reranker-v2-m3 already named in DESIGN.
- **Why P0:** complements G-01.

### G-03 No public benchmark numbers **[P0]**
- **Status today:** `benchmarks/` directory exists; LongMemEval / LOCOMO scripts are scheduled in M6.
- **Industry baseline:** mem0 91.6, MemMachine top-of-leaderboard, Zep claims (and disputes). engram has zero public numbers.
- **Touch point:** promote LOCOMO + LongMemEval runs from M6 to M4.5; publish to `benchmarks/BENCHMARKS.md` with reproducible scripts.
- **Why P0:** without numbers, "more rigorous design" is the only defense, and that is qualitative.

### G-04 No bi-temporal time model **[P1]** `[SPEC-AMEND]`
- **Status today:** SPEC §4.1 has `valid_from / valid_to / expires` — single time axis (event time only).
- **Industry baseline:** Graphiti's bi-temporal `t_valid × t_invalid` is becoming standard for auditable systems. Lets you answer "what did I believe to be true *then*?"
- **Touch point:** SPEC §4.1 — add optional `record_time` (or rename existing pair to `event_time` with backward-compat alias). Migration: existing rows get `record_time = valid_from`.
- **Why P1:** every audit-conscious user will eventually ask the question. Migration is cheap if done before storage hits scale.

### G-05 No first-class entity / relation graph **[P1]**
- **Status today:** `references:` field is a weak link list. No queryable entity index.
- **Industry baseline:** mem0 / Zep / Graphiti / Cognee all extract entities. Multi-hop queries ("Alice's manager + what Alice did in Q1") win there.
- **Touch point:** add lightweight `entities` and `entity_mentions` tables in `graph.db` (do **not** introduce Neo4j or another store). Async LLM extraction with fallback to tag system if the model is offline.
- **Why P1:** preserves the markdown-is-truth invariant. Entities live in the cache only.

### G-06 No active context compaction **[P1]**
- **Status today:** Recency decay (30-day half-life exp) and Evolve's split/merge proposals exist. There is no runtime "summarise loaded but unused memories" pass.
- **Industry baseline:** Anthropic compaction; Letta recall→archival demotion; mem0 selective token pipeline.
- **Touch point:** optional Stage 7.6 in Relevance Gate output: if packed_prompt > budget, emit an LLM-compressed digest written back as a `source: compacted` ephemeral memory (still markdown, still auditable).
- **Why P1:** without it, large stores degrade context efficiency one of the four Wisdom Metrics is supposed to track.

### G-07 No explicit `episodic` memory subtype **[P1]** `[SPEC-AMEND]`
- **Status today:** 6 Memory subtypes (user/feedback/project/agent/reference/architecture). Few-shot "task X solved with approach Y" has no clean home — Workflow demands a spine contract; Memory subtypes do not match.
- **Industry baseline:** LangMem and Letta both treat episodic as a top-level category.
- **Touch point:** SPEC §4.4 — add `episodic` as a 7th Memory subtype. Evolve Engine gains a new rule: "promote episodic cluster (≥3 related episodes) to a Workflow proposal."
- **Why P1:** unblocks a common usage pattern that currently has no good answer.

### G-08 Weak multi-agent isolation **[P2]**
- **Status today:** scope is human-shaped (org/team/user/project). No `agent_id` namespace.
- **Industry baseline:** mem0's `user_id / agent_id / run_id` 3-level namespace.
- **Touch point:** optional `agent_id:` frontmatter field; Relevance Gate filters by current agent_id by default; explicit `--include-other-agents` to cross.
- **Why P2:** matters when more than one assistant writes into the same store. v0.2 most users are single-agent.

### G-09 Recency model is too simplistic **[P2]**
- **Status today:** 30-day half-life exponential — a default heuristic.
- **Industry baseline:** Ebbinghaus-style "access resets the curve"; mem0 selective pipeline with token control.
- **Touch point:** `cli/engram/relevance/gate.py:119` — add per-asset `last_accessed_at` field, decay restarts at access. `[SPEC-AMEND]` if persisted.
- **Why P2:** current heuristic works at small scale.

### G-10 Web UI not yet implemented **[P1, scheduled M7]**
- **Status today:** Mock HTML pages exist in `docs/design/`. Backend skeleton in M7.
- **Industry baseline:** Letta's ADE allows operators to inspect and edit core memory blocks live.
- **Touch point:** existing TASKS T-110…T-115. No new work from this doc.
- **Why P1:** without UI, LLMs cannot "see themselves" — this is observability, not luxury.

### G-11 Consistency Engine Phase 3 (LLM review) is opt-in by default **[P2]**
- **Status today:** Phase 3 LLM review default `false`.
- **Industry observation:** competitive advantage of engram's 7-class taxonomy is wasted if it is opt-in. Competitors enable AI-driven review by default.
- **Touch point:** flip default to `true` in SPEC §11.5, with a 50k-token-per-month local-model budget note.
- **Why P2:** policy / UX choice, not a missing feature.

### G-12 No Claude memory tool MCP compatibility shim **[P2]**
- **Status today:** Anthropic's memory tool defines 6 file ops (`view / create / str_replace / insert / delete / rename`). Models trained for it do not natively know engram CLI.
- **Touch point:** new MCP adapter that maps these 6 ops onto `.memory/` operations with engram's invariants enforced (no auto-delete; route through review).
- **Why P2:** engram becomes a drop-in stronger backend for Claude users without retraining.

---

## 4. Translation to TASKS.md

The following tasks are added to TASKS.md / TASKS.zh.md (next available IDs). Each one references this doc so that an LLM picking up the task can read the full context.

| ID | Title | Milestone | Maps to |
|---|---|---|---|
| T-150 | Stage 3 fusion → RRF (Reciprocal Rank Fusion) | M4.5 | G-01 |
| T-151 | Stage 7.5 cross-encoder rerank with bge-reranker-v2-m3 | M4.5 | G-02 |
| T-152 | Promote LOCOMO + LongMemEval runs from M6 → M4.5; publish numbers | M4.5 | G-03 |
| T-153 | SPEC-AMEND: bi-temporal frontmatter (`event_time` × `record_time`) | M5 | G-04 |
| T-154 | Lightweight `entities` + `entity_mentions` cache tables in graph.db | M5 | G-05 |
| T-155 | Stage 7.6 active context compaction (optional, opt-in flag) | M5 | G-06 |
| T-156 | SPEC-AMEND: `episodic` as 7th Memory subtype + Evolve promote rule | M5 | G-07 |
| T-157 | Optional `agent_id` namespace for multi-agent isolation | M8 | G-08 |
| T-158 | Recency: per-asset `last_accessed_at` + Ebbinghaus reset | M8 | G-09 |
| T-159 | Default Phase 3 (LLM review) to enabled with documented token budget | M6 | G-11 |
| T-160 | MCP shim: Claude memory tool 6-op compatibility adapter | M8 | G-12 |

T-150…T-152 are the **P0 trio**. They are the difference between "designed seriously" and "demonstrably competitive."

---

## 5. Non-goals of this doc

This doc does not:

- Change SPEC.md or DESIGN.md. Items flagged `[SPEC-AMEND]` are proposals; they need their own PRs.
- Re-litigate frozen decisions (markdown-is-contract; never-auto-delete; SPEC > DESIGN > TASKS authority chain).
- Endorse any new storage engine. graph.db (SQLite) and the existing optional vector cache cover everything proposed here.
- Promise a public benchmark score. The promise is: run the benchmarks and publish the number, whatever it is.

---

## 6. Open questions

These need a user decision before the corresponding task starts.

- **Q1 (G-04):** rename `valid_from / valid_to` to `event_time_start / event_time_end` (clarity, breaking) or keep current names and add `record_time` only (compat)?
- **Q2 (G-06):** when active compaction emits a digest, is that digest a real Memory asset (subject to Consistency review) or a transient cache entry (lives in `~/.engram/cache/compacted/`)?
- **Q3 (G-07):** should `episodic` be a Memory subtype, or a new top-level asset class? Subtype is cheaper; class is cleaner. Current proposal: subtype.
- **Q4 (G-11):** which local model is the assumed Phase 3 reviewer? Token-budget defaults follow from the answer.

---

## 7. References

- mem0 paper: https://arxiv.org/html/2504.19413v1
- Zep / Graphiti paper: https://arxiv.org/abs/2501.13956
- Graphiti: https://github.com/getzep/graphiti
- Letta: https://docs.letta.com/advanced/memory-management/
- LangMem: https://blog.langchain.com/langmem-sdk-launch/
- A-MEM: https://arxiv.org/abs/2502.12110
- Cognee: https://github.com/topoteretes/cognee
- Claude memory tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- MemMachine LOCOMO: https://memmachine.ai/blog/2025/12/memmachine-v0.2-delivers-top-scores-and-efficiency-on-locomo-benchmark/
- Hybrid search guide: https://blog.supermemory.ai/hybrid-search-guide/
- LOCOMO replication issue: https://github.com/getzep/zep-papers/issues/5
