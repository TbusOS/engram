# Productization + Quality Plan — engram v0.2 → public launch

**Status:** draft, 2026-04-22
**Owner:** maintainer
**Related memory:** `project_engram_quality_bar.md`,
`feedback_no_compromise_on_this_project.md`

---

## 0. Why this doc exists

M1 + M2 + M3 are done. The code works. The SPEC + DESIGN are frozen. On
paper we are three milestones into v0.2. In reality, the "become the
default long-term memory system for LLM work" goal needs four additional
things that the task board (T-01 … T-105) does not capture:

1. A **first-look experience** that wins an engineer in 3 minutes and
   gets them to `engram init` in 5.
2. An **evaluation loop** that makes our quality improvements
   measurable, not anecdotal.
3. A **long-running-task harness** for the Consistency Engine and
   Autolearn so they stay honest when the operator isn't watching.
4. A **ratchet** on the store's evolution so regressions never land
   silently.

This doc picks four lessons from reference repos (Karpathy's
`autoresearch`, Anthropic's `harness-design-long-running-apps`,
`darwin-skill`, `evo-memory`) and maps each to concrete engram work.

---

## 1. First-look experience (3-minute win)

The README today opens with "5 layers + 2-axis scope model". That is
the correct taxonomy. It is the wrong landing. An engineer who has
never seen engram needs, in order: the problem, the demo, the install
line, the competitors table.

**Deliverables:**

- **D1-1** `CLAUDE.md` at the root — LLM collaborator onboarding
  guide, bilingual, ≤300 lines. **Shipped 2026-04-22.**
- **D1-2** `docs/QUICKSTART.md` — zero-to-first-memory in 5 minutes.
  **Shipped 2026-04-22.**
- **D1-3** README top rewrite — problem / demo / install / vs table,
  in that order. "5 layers + 2-axis" moves to an "Architecture" section
  that is reached by scrolling, not by landing.
- **D1-4** Landing site hero (docs/en/index.html + docs/zh/index.html)
  — prominent `<img src="assets/demo.gif">` above the fold, with a
  fallback `<pre>` asciinema-style text demo until the GIF is recorded.
  **The repo already hosts the site via GitHub Pages; this is a
  drop-in asset, not a new deploy target.**
- **D1-5** Demo recording — 30-60 second GIF driven by a scripted
  `engram init` → `engram memory add` → `engram memory search` →
  `engram validate` flow. Store at `docs/assets/demo.gif`. Script at
  `docs/assets/record-demo.sh` so we can re-record when the CLI
  surface changes.

**Quality bar:** an engineer who spends three minutes on the landing
page must be able to state (a) what engram is, (b) why it beats their
current setup, (c) the single install command. The bar is verified by
asking two people who have never seen engram to do exactly this,
before we announce anywhere.

---

## 2. Evaluation loop — autoresearch's `val_bpb` for memory

Karpathy's `autoresearch` has exactly one success metric: `val_bpb`.
Every experiment either beats the last one or it doesn't; there is no
ambiguity about whether a change helped. The code is explicitly designed
so a coin-flip-level improvement is visible in the loss curve.

engram today has no such metric. We claim "the memory system
measurably improves over time" in SPEC §1.3 and DESIGN §1.3, but no
number anywhere demonstrates it. That is a credibility gap for a
project whose core pitch is *measurable* self-improvement.

**Deliverables:**

- **D2-1** `benchmarks/METRICS.md` — a single page defining the
  four Wisdom Metrics from DESIGN §1.3 in operational terms:
  - *Workflow mastery*: success rate on workflow fixtures.
  - *Task recurrence efficiency*: median time from "similar task
    seen before" to "task completed this time".
  - *Memory curation ratio*: fraction of memories referenced in the
    last 90 days / total memories.
  - *Context efficiency*: tokens packed by Relevance Gate ÷ tokens
    that would have been packed by a naive "load everything" baseline.
- **D2-2** `benchmarks/baselines/` — scripted harness that runs each
  metric against a fixture store (`tests/fixtures/`) and emits a TSV.
  Same shape as autoresearch's `results.tsv`.
- **D2-3** `engram benchmark` CLI command — runs the harness, prints
  deltas against the previous run, exits non-zero on regression.
  Matches the `keep/reset` ratchet from autoresearch: if a SPEC change
  or Relevance Gate tweak makes any metric worse, CI fails.
- **D2-4** GitHub Actions workflow — runs `engram benchmark` on every
  PR against `main`. Posts the metric delta as a PR comment.

**Task slot:** M4.5 (existing). This doc concretizes what T-58…T-62
should deliver.

---

## 3. Long-running-task harness — Anthropic GAN pattern

`harness-design-long-running-apps.md` shows Anthropic's finding that
generator agents lie to themselves on long tasks. The fix: a separate
evaluator agent with real test tools (Playwright in their case).

engram has two subsystems that will run for hours unattended and are
susceptible to the same failure mode:

- **Consistency Engine** (M4, T-46..T-49): scans the full store,
  proposes remediations. If it rationalizes "this conflict is actually
  not a conflict" incorrectly, the store degrades silently.
- **Autolearn Engine** (M5, T-65..T-68): edits `spine.*` files with
  the claim "this is better." The Darwin skill paper specifically
  warns this drifts toward metric gaming without an independent
  evaluator.

**Deliverables:**

- **D3-1** Split the Consistency Engine into two agents:
  - *Detector* emits structured `ConflictReport` records — already
    planned in T-47/T-48.
  - *Evaluator* (new, T-46.5): a separate LLM invocation with **no
    access to the detector's reasoning** that grades each proposed
    resolution on (a) does it preserve the store's invariants, (b)
    does it match SPEC §8.4. Only resolutions passing the evaluator
    reach `engram review`.
- **D3-2** Autolearn dual-evaluator per Darwin skill §2:
  - *Static* check (structure, spine step count, fixture coverage)
    weighted 60.
  - *Dynamic* check (fixtures pass, metrics improve) weighted 40.
  - `K=5` consecutive passes required before a proposed spine
    change is committed. Below K it stays in `spine.proposed.py`.
- **D3-3** `docs/DESIGN.md` §5.3 + §9.2 update to document both. Tag
  the sections "supersedes previous single-engine design (2026-04-22)".

**Task impact:** T-46 redesign + new T-46.5 evaluator subtask. Net +1
Task, not a re-plan.

---

## 4. Evolution ratchet — Darwin-style keep/revert

Both autoresearch and darwin-skill use the same control flow:

```
propose → evaluate → keep if better, revert if worse
```

SPEC v0.2 is frozen. But v0.3 will come. And `spine.*` files in every
Workflow will evolve via Autolearn. Without a ratchet, there is no
guarantee that today's SPEC improvement doesn't silently degrade a
test we cared about yesterday.

**Deliverables:**

- **D4-1** `tests/conformance/` — already exists as a dir; populate
  with SPEC-level invariant tests that outlive any single
  implementation. One assertion per invariant from SPEC §1.2
  ("never auto-delete", "MEMORY.md required sections", "unknown fields
  preserved", etc.).
- **D4-2** `engram conformance` CLI command — runs the conformance
  suite against any engram store regardless of who implemented it.
  This is the SPEC's own self-test; any third-party implementation
  (a Rust port, a Go port) that passes `engram conformance` is by
  definition spec-compliant.
- **D4-3** Reading: every Relevance Gate / Consistency Engine / Autolearn
  commit must leave `engram benchmark` non-regressing AND `engram
  conformance` green. This is the ratchet — the metric floor never
  lowers.
- **D4-4** Per-workflow `metrics.yaml` with `keep/revert` decision
  recorded. Autolearn's `spine.*` rewrite writes a rev entry regardless
  of outcome; only `keep` advances `rev/current`.

**Task impact:** T-57 (existing P0 CLI parity E2E) expands to cover
conformance; T-65..T-68 use the D4-4 record format.

---

## 5. Synthesize phase — evo-memory's missing third step

DeepMind's evo-memory paper formalized memory work as three phases:
**Search → Synthesize → Evolve**. engram has Search (Relevance Gate)
and Evolve (Consistency Engine). We do not have Synthesize.

In practice, a user today accumulates 200 related memories about
"platform oncall". The Relevance Gate retrieves the right 3 for a given
query. But it does not produce a higher-order view ("these 200
memories distill into 5 rules + 3 patterns"). Without synthesis,
the store's *volume* grows without its *usefulness* growing.

**Deliverables:**

- **D5-1** `engram memory synthesize --topic=<name> --budget=<tokens>`
  CLI command. Loads all memories matching the topic, invokes an LLM
  with a structured prompt to produce a `_synthesis.md` digest,
  writes it under `.memory/index/<topic>.md`. Read-only; never
  modifies the source memories.
- **D5-2** Synthesis is invalidated when any source memory changes —
  stored in `graph.db` as a derivation edge.
- **D5-3** `engram review` surfaces "5 synthesis digests are stale"
  warnings when edges invalidate, so the user knows to re-run.

**Task slot:** M6 (intelligence phase 3+4), specifically a new
subtask T-71.5 before Phase 4 evolve lands.

---

## 6. Sequence + gate (what ships first, what waits)

| Phase | Deliverables | Merge gate |
|---|---|---|
| **Now** (2026-04-22) | D1-1 CLAUDE.md, D1-2 QUICKSTART, D1-3 README rewrite, D1-4 landing hero + placeholder | Reviewed by human; no metrics required |
| **M4 end** (~2 weeks) | D1-5 demo GIF, D2-1 METRICS.md, D2-2 baselines harness | Benchmark harness green on baseline |
| **M4 end + 1 week** | D2-3 engram benchmark CLI, D2-4 CI workflow | PR comments working on a test PR |
| **M4.5** (existing) | D4-1 conformance suite, D4-2 engram conformance CLI | `engram conformance` green against fixture store |
| **M5** | D3-2 Autolearn dual-evaluator, D4-4 per-workflow metrics.yaml | Darwin K=5 gate demonstrated on one workflow |
| **M6** | D3-1 Consistency dual-engine split, D5-1 synthesize CLI | Evaluator catches one intentional bad resolution in a test |

Everything before "M4 end + 1 week" is unblocked by this doc. The rest
is planning work that lands on its own milestone.

---

## 7. Non-goals

- A hosted service. engram is local-first. No SaaS in this plan.
- A chat UI. The web UI (M6) is for *observation* — graph view,
  confidence curves, Consistency proposals — not a "chat with your
  memory" product.
- Multi-tenant access control. The `scope` model + git-based org/team
  repos cover the collaboration cases. No ACL layer, no SSO.
- Anything that requires us to run a registry (federated pools, global
  publish/subscribe). See DESIGN §13.4 for the explicit non-goal list.

---

## 8. Credit

Four reference repos shaped this plan:

- **`karpathy/autoresearch`** — single metric, fixed budget, git
  ratchet, program.md pattern.
- **`anthropic/harness-design-long-running-apps`** — Planner /
  Generator / Evaluator split; evaluator must have real test tooling.
- **`alchaincyf/darwin-skill`** — dual-dimension scoring (static + dynamic),
  K-consecutive-pass gate, human-in-loop checkpoint.
- **DeepMind evo-memory paper** (arXiv:2511.20857) — Search /
  Synthesize / Evolve cycle.

The engram-side notes for each live at
`~/linux-kernel/ai-doc/self-improving-agents/autoresearch.md`,
`~/linux-kernel/ai-doc/agent-patterns/harness-design-long-running-apps.md`,
`~/linux-kernel/ai-doc/self-improving-agents/darwin-skill.md`,
`~/linux-kernel/ai-doc/memory-systems/evo-memory.md`.
