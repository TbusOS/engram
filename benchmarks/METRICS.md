# engram benchmarks — the four Wisdom Metrics, operationalized

**Status:** draft, 2026-04-22
**Spec reference:** DESIGN §1.3, SPEC §1.2 principle 5
**Related plan:** `docs/superpowers/specs/2026-04-22-productization-plan.md` §2

---

## 0. Why this document exists

engram's core pitch is *quantifiable self-improvement* — the claim that
a store gets measurably smarter with use, not just larger. Making that
claim real requires numbers. Four metrics get reported; each one has a
formula, a fixture, a baseline, and a direction (higher-is-better or
lower-is-better). Any change that moves a metric the wrong way is a
regression, end of discussion.

This follows the discipline from Karpathy's
[`autoresearch`](https://github.com/karpathy/autoresearch) — a single
clear scalar per concern, a fixed fixture, a ratchet that will not let
a regression hide.

---

## 1. Metric catalog

### M1 — Workflow mastery rate

**What it measures:** how often `spine.*` execution passes all
attached fixtures on the current workflow set.

**Formula:**

```
M1 = Σ(successful_spine_runs) / Σ(total_spine_runs)
```

over the last 90 days of `metrics.yaml` records across every workflow
in `.memory/workflows/`.

**Direction:** higher is better (0.0 → 1.0 range).

**Baseline fixture:** `benchmarks/fixtures/workflow-mastery/` — 5
canonical workflows (commit-message-writer, release-notes, incident-
postmortem, pr-description, test-generator). Each has 3 success-case
fixtures and 1 failure-case fixture.

**Baseline value:** TBD; first run establishes it.

**Regresses if:** any of the 5 workflows drops below its per-workflow
baseline by more than 5 percentage points.

### M2 — Task recurrence efficiency

**What it measures:** median time from "a similar task was seen before"
to "this task completed". Rewards stores whose accumulated memories
actually shorten the *next* run of a recurring task.

**Formula:**

```
M2 = median(
  (task_end_time - task_start_time)
  for task in recurring_tasks
  if task.similarity_to_prior >= 0.6
) / median(
  (task_end_time - task_start_time)
  for task in recurring_tasks
  if task.similarity_to_prior < 0.3
)
```

A value of 1.0 means memory adds no speedup. 0.5 means tasks-with-prior
run in half the wall-clock of tasks-without-prior.

**Direction:** lower is better (closer to zero = more leverage from
existing memory).

**Baseline fixture:** `benchmarks/fixtures/task-recurrence/` — a
stream of 40 synthetic task records over 12 weeks, with ground-truth
similarity labels.

**Baseline value:** TBD.

**Regresses if:** value increases by more than 10 percentage points
across a window of 10 consecutive benchmark runs.

### M3 — Memory curation ratio

**What it measures:** the fraction of memories that carry their weight.
A memory is considered active if it has been referenced (read,
surfaced by search, or loaded into a context pack) in the last 90
days.

**Formula:**

```
M3 = count(memories where last_referenced_at >= now - 90 days)
   / count(all memories)
```

**Direction:** higher is better (approaches 1.0 = no dead weight).

**Baseline fixture:** `benchmarks/fixtures/curation-ratio/` — a store
seeded with 200 memories across mixed scopes; the harness simulates a
90-day reference pattern using a controlled Zipf distribution (a few
memories used heavily, a long tail used rarely).

**Baseline value:** TBD; MemPalace's published benchmark reports ~0.62
on a similar fixture. Our target: ≥ 0.70 after the Consistency Engine
(M4) proposes retirements for the bottom quartile.

**Regresses if:** M3 drops below the baseline by more than 3
percentage points on the same fixture.

### M4 — Context efficiency

**What it measures:** the ratio of "useful tokens packed by the
Relevance Gate" to "tokens that a naive 'load everything' baseline
would emit". Rewards the Relevance Gate for *not* spending budget on
irrelevant content.

**Formula:**

```
M4 = tokens(relevance_gate_output)
   / tokens(naive_full_scope_output)
```

when both are scoped to the same query + same budget limit.

**Direction:** lower is better (efficient packing → small ratio),
bounded below by the mandatory-bypass floor (every mandatory asset
must be included regardless).

**Baseline fixture:** `benchmarks/fixtures/context-efficiency/` — 30
task-prompts × the 200-memory store from M3.

**Baseline value:** TBD; theoretical lower bound ≈ 0.12 given the
typical mandatory-asset density in the fixture.

**Regresses if:** M4 increases by more than 5 percentage points on the
same fixture.

---

## 2. Harness contract

`engram benchmark` (CLI command, delivers as D2-3) runs the four
metrics against the canonical fixtures and writes a TSV record:

```
timestamp   commit_sha   M1     M2     M3     M4     status
2026-04-22  69a2b28      n/a    n/a    n/a    n/a    bootstrap
```

Format follows `autoresearch/results.tsv` conventions: tab-separated,
append-only, committed to the repo on release tags.

### Regression gate

On every PR against `main`:

1. The harness runs the four metrics on the PR head.
2. Results are compared to the HEAD-of-main baseline recorded in
   `benchmarks/results.tsv`.
3. If any metric regresses past its per-metric threshold, CI fails.
4. Otherwise, the new row is appended with `status=accepted`.

A metric that *cannot be measured* on a given PR (e.g. M1 when no
workflows are attached) reports `n/a` and does not gate the build.

### Non-goals

- No "overall score" that combines the four metrics. Each metric
  guards a different invariant; collapsing them hides regressions.
- No leaderboard. The metric exists to protect the store from
  regressions, not to rank engram against hosted services on
  synthetic benchmarks.
- No user-facing dashboard. These numbers live in `benchmarks/`; the
  web UI (M6) shows the store's own per-asset confidence curves,
  which serve a different purpose.

---

## 3. Roadmap

- **M4 end:** fixtures under `benchmarks/fixtures/` landed; first
  baseline recorded in `benchmarks/results.tsv`.
- **M4 + 1 week:** `engram benchmark` CLI + GitHub Actions workflow
  (PR comments showing metric deltas).
- **M5:** M1 populated by live `spine.*` runs from user workflows
  (not just synthetic fixtures).
- **M6:** M3 refined by real reference telemetry from MCP + adapter
  layer, not simulated Zipf.

---

## 4. Credit

The "single scalar + fixed budget + git ratchet" discipline comes from
Karpathy's `autoresearch`. The notion of a benchmarking *discipline*
separate from the code it measures comes from MemPalace's
`BENCHMARKS.md`. See `~/linux-kernel/ai-doc/self-improving-agents/
autoresearch.md` for the full notes that shaped this document.
