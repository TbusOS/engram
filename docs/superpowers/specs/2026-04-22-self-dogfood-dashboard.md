# Self-dogfood dashboard — frozen design, deferred to M7

**Status:** design-only, **execution deferred** until M7 `engram-web`
lands
**Date:** 2026-04-22
**Related memory:** `project_productization_plan_2026_04_22.md`

---

## 0. Why this doc exists

The idea is tempting: engram's whole pitch is that memory systems
should be observable — so let engram observe *its own development*,
render the observation as a live dashboard on GitHub Pages, and
demonstrate the product by using the product.

The concern is real: engram is a memory system, and the session that
develops engram (Claude Code on the engram repo) already has its own
memory at `~/.claude/projects/-Users-sky-linux-kernel-github-engram/
memory/`. Dropping a second memory system into the same working tree
risks confusion — one record gets filed to the wrong place, one
`CLAUDE.md` points at the wrong store, and the developer loses
confidence in whichever store produced a given fact.

The rule the user set on 2026-04-22:

> "要做就要做到最干净的测试,不然既保证不了测试,还会影响当前的开发"

This doc freezes the *only* isolation scheme that meets that rule, and
defers execution to M7.

---

## 1. Non-goals

- **No engram store at the repo root.** Ever. The file
  `/Users/sky/linux-kernel/github/engram/.memory/` must not exist.
  That's the path Claude Code's project auto-detection picks up; any
  store there would get mixed into the developer's own working
  context.
- **No CLAUDE.md / AGENTS.md / GEMINI.md at the repo root that points
  at a dashboard store.** The only files at the repo root are
  authoritative documentation for the *product* (the one an engineer
  gets when they `git clone engram` and start developing on it).
- **No dashboard write-path.** The dashboard is read-only from the
  user's standpoint. No command ever writes a memory *about the
  project* into a location that Claude Code might read.

If any of these drift, the dashboard is not shipped.

---

## 2. Clean-isolation scheme (the only acceptable one)

### Two completely independent sources, one output

- **Source A — TASKS.md + git log + test counts.** Plain files
  that already exist. Parsed at build time.
- **Source B — (optional) a *demo* engram store** under
  `docs/meta/demo-store/` used purely to prove the M7 web UI works on
  a store it doesn't itself inhabit. The demo store contains synthetic
  memories unrelated to engram's own roadmap; nothing in it ever
  refers to a real T-XX task or a real milestone.

Both sources feed a static-HTML build step. The resulting
`docs/dashboard.html` is served by GitHub Pages; no runtime server,
no JavaScript fetching from external endpoints.

### What the dashboard shows

1. **Milestone progress bar** from TASKS.md — how many Tasks done /
   todo in each M1..M8. Parsed by scanning the `| status |` column.
2. **Recent commits** — parsed from `git log --oneline --since=30days`.
3. **Test count trend** — parsed from CI logs or a committed
   `benchmarks/results.tsv` row on release tags (never on every PR,
   to keep the ratchet honest).
4. **Latest superpower specs** — a card per entry in
   `docs/superpowers/specs/` with title + status.
5. **Demo pane (only if B is active)** — a single iframe rendering
   the M7 engram-web UI pointing at `docs/meta/demo-store/`. The
   iframe is visually framed as "demo" so no-one reads it as live
   project data.

### What the dashboard does NOT show

- Any memory from `~/.claude/...` (the developer's personal memory).
- Any memory from a store that could be confused with the product
  under development.
- Any real-time "what is engram development doing this hour" beyond
  what git log + TASKS.md already expose publicly.

---

## 3. Build pipeline

```
  docs/
  ├── meta/
  │   ├── scripts/
  │   │   └── build-dashboard.py     # reads TASKS.md + git + tests
  │   ├── demo-store/                # optional M7 demo target
  │   │   └── .memory/               # synthetic, self-contained
  │   └── README.md                  # explains "this is not the
  │                                  #  product's memory; hands off"
  └── dashboard.html                 # build output, committed
```

- `build-dashboard.py` runs in CI on every push to main. It writes
  `docs/dashboard.html` and commits the diff as part of the CI job.
- Local preview: `python3 -m http.server --directory docs/` followed
  by `open http://localhost:8000/dashboard.html`.
- No dependency on the engram CLI runtime. The builder is a pure
  text processor.

---

## 4. Kill switches

If at any point during the build pipeline rollout the clean isolation
starts slipping, pull one of these in order:

1. **Remove the iframe to demo-store.** Dashboard becomes source A only.
   Zero risk of cross-contamination because B no longer participates.
2. **Move dashboard out of `docs/`** into a separate repo entirely
   (e.g. `engram-dashboard`). Now the "developing on engram" and
   "tracking engram" code trees cannot share a working directory.
3. **Cancel the initiative.** Public progress tracking via TASKS.md
   on GitHub is already sufficient for the outside world; we lose
   some demo value but zero development clarity.

---

## 5. Ship gate

This initiative does **not** start until every one of the following
is true:

- M4 is closed (T-40…T-57 all done or explicitly deferred).
- M5 Autolearn is at least in progress; Autolearn's own eval rig is
  a useful dashboard signal.
- M7 `engram-web` has shipped in a form stable enough that embedding
  it in an iframe does not create a maintenance anchor.
- The user re-confirms the concern raised on 2026-04-22 has been
  resolved by the isolation scheme above.

Until all four are true, this doc sits in `docs/superpowers/specs/`
as a frozen plan. The value is in having the answer on file, not in
shipping the feature early.

---

## 6. Credit

The dogfood-with-isolation pattern is modelled on
`~/linux-kernel/ai-doc/docs/superpowers/` where the "paper comic"
initiative is explicitly marked **execution paused** while its design
stays shipped. Good design docs are not lost when an initiative is
paused; they become the blueprint when the constraints finally clear.
