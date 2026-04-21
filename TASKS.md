[English](TASKS.md) · [中文](TASKS.zh.md)

# engram Task Board

**Version target**: v0.2.0 (first public release) and beyond
**Status**: active — claim tasks via GitHub Issue + self-assign
**Last updated**: 2026-04-20
**Canonical**: https://github.com/TbusOS/engram/blob/main/TASKS.md

---

## 1. Philosophy + how to use this board

This file is LIVE — edited via PR as tasks are claimed, completed, or split. Do not treat it as a static spec. If a task is underway and no PR exists, the task is not actually being done.

**Statuses**: `todo` / `doing` / `review` / `done` / `abandoned`

**Ownership**: GitHub handle in the Owner column; empty = available to claim.

**Dependencies**: explicit T-ID references. Do not start a task until its blockers are `done`.

**Claiming**: open an Issue titled `Claim T-XX`, self-assign it, then update this file's Owner and status to `doing` in the implementing PR. One owner per task.

**Splits**: any task estimated at >3 days MUST be split before work begins. Add sub-tasks inline with IDs like T-11a, T-11b. The parent row stays; update its Notes to point at sub-tasks.

**Discussion levels**:
- Direction-level debate (milestone ordering, P2 → P1 promotions) → GitHub Discussions
- Task-level clarification (ambiguous requirements, blocked work) → the Issue linked to that T-ID
- PR-level review → the PR itself

**Done criteria**: unit tests pass + integration tests pass (where applicable) + the feature appears in `--help` output or is accessible via MCP tools as documented in DESIGN.md. Status flips to `done` only after merge.

**Abandoned**: if a task is dropped, set status = `abandoned` and explain in Notes. Keep the row — do not delete.

---

## 2. Milestone overview

| Milestone | Goal | Hard blocker to exit |
|-----------|------|----------------------|
| **M1** — SPEC + DESIGN freeze | v0.2 SPEC and DESIGN reviewed and frozen | 5+ external readers + all open review issues resolved |
| **M2** — CLI core | `engram init / status / version / validate / review / memory (CRUD)` usable end-to-end | Empty project → init → add 10 memories → validate green |
| **M3** — Scope + Pool + Migrate | All 4 hierarchy scopes + pool subscription + `migrate --from=v0.1` work end-to-end | Real v0.1 store migrates with zero data loss |
| **M4** — Intelligence Phase 1-2 + Adapters + MCP | Relevance Gate + Consistency Phase 1-2 + Inter-Repo Messenger + Claude Code / Codex / Gemini CLI / Cursor / raw-api adapters + MCP server (read tools) | engram-cli installable via pip; all P0 CLI commands pass E2E |
| **M4.5** — Benchmark infrastructure | `benchmarks/BENCHMARKS.md` + consistency_test + scope_isolation_test + docs/HISTORY.md | Results reproducible from committed scripts |
| **M5** — Workflow + Autolearn | Workflow asset full + Autolearn Darwin ratchet + phase gate | Single workflow autolearns 10 rounds with monotone metric improvement |
| **M6** — KB + Inbox + Consistency Phase 3-4 | Knowledge Base compile + Inbox full + semantic + execution consistency phases | Cross-repo bug-report → acknowledge → resolve cycle works; KB `_compiled.md` auto-stales |
| **M7** — Web UI P0 | engram-web 6 P0 pages (Dashboard, Memory Detail, Workflow Detail, KB Article, Inbox, Context Preview) | `engram web serve` → click through 6 pages → no 500s; WCAG AA checks pass |
| **M8** — Evolve + Team full + TS SDK + remaining Web UI + migrate suite | Evolve Engine, Pool propagation notify+pinned, Wisdom dashboard, TypeScript SDK, remaining 5 Web UI pages, 6 additional migrate sources, Playbook command family | Complete P1 scope from DESIGN §13.2 |

After M8, work shifts to P2 items from DESIGN §13.3: multi-machine sync daemon, local small-model reranker, Obsidian plugin, IDE deep integration, multilingual embeddings. None of these require a SPEC change. They are listed to avoid duplicate design work when contributors propose them, not as scheduled milestones.

---

## 3. Tasks

### M1 — SPEC + DESIGN freeze

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-01 | Write SPEC v0.2 all 14 chapters | done | | | 14 chapters on main |
| T-02 | Write DESIGN v0.2 all 14 chapters | done | | | §0–§13 on main |
| T-03 | Set up docs/glossary.md + docs/superpowers/plans/ | done | | | |
| T-04 | Archive v0.1 to docs/archive/v0.1/ | done | | | |
| T-05 | Build GitHub Pages landing site (EN + ZH) | done | | | docs/index.html live |
| T-06 | Build Web UI mockup 11 pages (EN + ZH) | done | | | docs/design/ static pages |
| T-07 | External review of SPEC + DESIGN — 5+ readers | todo | | T-01, T-02 | Open GitHub Discussion, solicit reviewers; aggregate feedback into issues |
| T-08 | Resolve all open review issues from T-07 | todo | | T-07 | Each issue gets a resolution comment before closing |
| T-09 | Tag v0.2.0-pre after review issues resolved | todo | | T-08 | Triggers M2 implementation work |

---

### M2 — CLI core

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-10 | cli/ scaffold: pyproject.toml + click integration + package skeleton | done | | T-09 | Entry point `engram`; version from pyproject; `pip install -e "cli[dev]"` works. T-09 gate deferred per path B (M1 external review in parallel with M2 scaffold) |
| T-11 | `engram/core/paths.py` — project root detection + ENGRAM_DIR support | done | | T-10 | `find_project_root` walks up from cwd looking for `.memory/`; `ENGRAM_DIR` env var short-circuits; also exposes `user_root`, `memory_dir`, `engram_dir`. 100% unit coverage |
| T-12 | `engram/core/frontmatter.py` — YAML parse + validation per SPEC §4.1 | done | | T-10 | Typed `MemoryFrontmatter` + `Confidence` dataclasses (frozen+slots); 3 enums; strict validation on required / enum / scope-conditional (org/team/pool/subscribed_at) / subtype-specific (feedback→enforcement, workflow_ptr→workflow_ref, agent→source) / confidence block. Unknown fields preserved in `extra` per SPEC §4.1 (not raised on — SPEC wins over the earlier task-note wording). 39 unit tests, 96% line coverage |
| T-13 | `engram/core/fs.py` — atomic writes + locks + symlinks | done | | T-10 | `write_atomic(path, content)` tempfile+fsync+os.replace; `acquire_lock(path)` fcntl.flock context manager with shared/exclusive mode; `atomic_symlink(target, link)` swap via sibling tmp + rename. POSIX only (macOS+Linux). 19 unit tests incl. thread serialization, 93% coverage |
| T-14 | `engram/core/graph_db.py` — SQLite schema from DESIGN §3.2 + WAL mode + migrations | done | | T-10 | `open_graph_db(path)` ctx mgr applies PRAGMA journal_mode=WAL / synchronous=NORMAL / foreign_keys=ON. All 7 DESIGN §3.2 tables (assets, references_, subscriptions, inbox_messages, consistency_proposals, usage_events, schema_version) + 5 indexes created via forward-only migration runner keyed by SCHEMA_VERSION. AssetRow dataclass + insert_asset / get_asset / list_asset_ids helpers (other tables reserved for their consuming tasks). 19 unit tests 98% coverage. Note: original task row said "assets, references, scopes, journal" — that was imprecise wording; DESIGN §3.2 is authoritative, no `scopes` / `journal` tables exist (journal is JSONL on disk per §3.4) |
| T-15 | `engram/core/journal.py` — append-only JSONL helpers | done | | T-10 | `append_event(path, event)` with fcntl.flock (50×20 concurrent writers round-trip without loss or corruption); `read_events(path)` generator that skips blank lines, rejects non-object events, and tags parse errors with line numbers. 16 unit tests, 100% coverage |
| T-16 | `engram/cli.py` — click main dispatcher + global flags | done | | T-10 | Root group wires `--dir PATH` / `--format {text,json}` / `--quiet -q` / `--debug`. Typed `GlobalConfig` (frozen dataclass) stored on `ctx.obj`. `resolve_project_root()` honors DESIGN §9.3 resolution order (--dir > ENGRAM_DIR > cwd walk-up). Logging level set from flags (debug>quiet>info). 21 unit tests, 98% coverage |
| T-17 | `engram init` — interactive + non-interactive modes | done | | T-11, T-13 | `engram init` + pure `init_project()` create `.memory/{local,pools,workflows,kb}/` + `.engram/version=0.2` + SPEC §7.2-structured `MEMORY.md` skeleton + `pools.toml` stub. `--name` overrides directory basename; `--no-adapter` reserved no-op (full adapter wiring in T-55); `--force` re-writes skeleton without touching user content under local/workflows/kb. 19 unit + E2E click tests, 100% coverage on the command. Seeds directory population deferred — seeds/ still just placeholders in repo |
| T-18 | `engram version` + `engram config get/set` | done | | T-16 | `version` prints CLI semver + store schema + Python + platform (text/json). `config get/set/list` operates on `~/.engram/config.toml` via tomli + tomli-w; dotted keys address nested TOML tables; values auto-coerced (true / 42 / 3.14 / str); writes atomic via write_atomic; missing keys raise ConfigKeyError. 40 unit tests, 97% coverage on new code |
| T-19 | `engram memory add / list / read / update / archive / search` | done | | T-11, T-12, T-13, T-14 | All 6 subcommands working. add: flag-driven, enforces SPEC §4.1 subtype-specific fields via frontmatter round-trip; --body accepts `-` for stdin; --force overwrites. list: text table + json. read: file text + json frontmatter/body. update: --description / --body / --enforcement / --lifecycle / --tags; bumps `updated` date. archive: moves file to `~/.engram/archive/YYYY/MM/` and flips lifecycle_state. search: pure-Python BM25 over name+description+body, --limit flag, text + json output. **M2 decision**: graph.db at `<project>/.engram/graph.db` (DESIGN §3.2 specifies `~/.engram/graph.db` but that has a schema gap for cross-project uniqueness; M3 revisits). 45 unit tests, 94% coverage on memory.py |
| T-20 | `engram validate` — runs all SPEC §12 rules; JSON + text output; CI-friendly exit codes | done | | T-12, T-14 | M2 subset of SPEC §12: STR (§12.1), FM (§12.2), MEM (§12.3), IDX (§12.6), REF (§12.9). SCO/ENF/POOL/INBOX/WF/KB/CONS families land with their consuming milestones. Text + JSON output per §12.13; exit codes 0 clean / 1 warnings / 2 errors (note: original task row had the codes flipped — SPEC §12.13 is authoritative). 35 unit tests, 93% coverage on validator |
| T-21 | `engram review` — aggregated health summary | done | | T-14, T-20 | Wraps run_validate + graph.db asset counts. Typed `Review` dataclass (total_assets, by_subtype, by_lifecycle, by_severity, by_category, issues). text: sections Assets + Validation issues grouped by severity + category. json: nested {assets, validation} payload. Always exits 0 (informational, not CI gate). 11 unit tests, 100% coverage |
| T-22 | `engram status` — project + scope summary | done | | T-11, T-14 | Reads `.engram/version` + `.memory/pools.toml` + `.engram/graph.db`. Typed `Status` dataclass (project_root, initialized, store_version, total_assets, by_subtype, by_lifecycle, pool_subscriptions). Handles un-inited project (prints "run `engram init`"); tolerates malformed pools.toml. text + json output; always exit 0. 10 unit tests, 94% coverage |
| T-23 | Unit tests for all core modules (pytest + 80% coverage) | done | | T-11, T-12, T-13, T-14, T-15 | Achieved through TDD-alongside each preceding task: paths 100% / frontmatter 96% / fs 93% / graph_db 98% / journal 100%. Each new module shipped with its full test suite; T-23 flips to done as a milestone checkpoint rather than a separate work item |
| T-24 | E2E test: empty project → init → add 10 memories → review/validate green | done | | T-17, T-19, T-20, T-21 | `tests/e2e/test_m2_smoke.py` exercises the full M2 flow: init → add×10 (5 subtypes: user/feedback/project/reference/agent) → list → search → validate (errors==0) → review (10 assets, 5×2 by subtype) → status + second smoke for update + archive roundtrip. Also subprocess-level `engram --version` smoke. "Green" defined as `errors==0`; W-MEM-002 warnings on agents are expected (confidence flags come in M2 polish or M5) |

---

### M3 — Scope + Pool + Migrate

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-30 | `engram/pool/` module — subscribe / unsubscribe / list per SPEC §8 / §9 | done | | T-13, T-14 | `commands/pool.py` with subscribe/unsubscribe/list. Writes `[subscribe.<name>]` to pools.toml per SPEC §9.2 (fixed T-17 init stub which used wrong `[[subscription]]` schema; T-22 status reader updated accordingly). Creates `.memory/pools/<name>` symlink via `atomic_symlink`. Strict: errors if pool not at `~/.engram/pools/<name>/`. --at (org/team/user/project), --mode (auto-sync/notify/pinned), --revision (required with pinned), --force. 15 unit tests, 306 total passing |
| T-31 | `engram/pool/propagation.py` — auto-sync mode only | done | | T-30 | Symlink target resolution in commands/pool.py: auto-sync/notify → `rev/current` (falls back to pool root if no rev/); pinned → `rev/<revision>/` (must exist). `engram pool sync [name | --all]` refreshes `last_synced_rev` and appends `propagation_completed` events to `~/.engram/journal/propagation.jsonl` per SPEC §9.4. Pinned subscriptions skipped. Subscribe now auto-records last_synced_rev from current rev. 13 new unit tests, 319 total passing |
| T-32 | `engram/pool/git_sync.py` — git-based pool sync | done | | T-30 | `engram pool pull [<name> | --all]` runs `git pull --ff-only` via subprocess; reports added/modified/removed file counts from `git diff --name-status` between before/after HEAD. Refactored pool code into `engram/pool/{subscriptions,propagation,git_sync,commands}.py` per DESIGN §4.2 layout. 9 new unit tests (real git repos, skip if git missing), 328 total passing |
| T-33 | `engram/team/` + `engram/org/` — join / sync / publish / status | done | | T-14, T-30 | `engram/core/git.py` extracted (run_git / head_sha / diff_name_status / pull_ff / clone / commit_all / push / status_porcelain) — shared by pool propagation. `engram/scope/{git_ops,factory}.py` factor the identical team/org behaviour; `engram/team/__init__.py` + `engram/org/__init__.py` pick kind and export click group. Commands: join `<name> <url>`, sync `[<name> | --all]`, publish `<name> --message`, status `<name>`, list. 32 parametrized tests (real git), 360 total passing |
| T-34 | `engram/migrate/v0_1.py` — SPEC §13.4 contract; dry-run + live + rollback | done | | T-12, T-13 | `engram/migrate/{__init__, commands, v0_1}.py` multi-file per DESIGN §4.2. `engram migrate --from=v0.1` with --dry-run / --rollback. Creates `.memory.pre-v0.2.backup/` before any write; moves flat `*.md` into `local/`; injects `scope: project`; adds `enforcement: default` on feedback; adds zero-state `confidence` on agent (SPEC §13.4 says `{}` but parser demands sub-fields — zero block per §13.7 "additive default" rule). Unknown fields preserved; MEMORY.md regenerated with migrated assets indexed (Identity / Always-on rules / Topics sections populated by type); migration event journaled to `~/.engram/journal/migration.jsonl`; idempotent re-run. 26 unit tests + CLI smoke, 386 total passing, 94% coverage |
| T-35 | E2E: v0.1 store migration with real 20-memory sample | done | | T-34 | `tests/fixtures/v0.1_store/` — 20 generic-example assets (3 user / 5 feedback / 5 project / 4 reference / 3 agent) + v0.1 `MEMORY.md` + 2 custom fm fields (`priority`, `origin_tool`) + unicode body. `tests/e2e/test_m3_migration_e2e.py` — 14 tests asserting: (a) dry-run is byte-preserving, (b) every body byte-identical post-migration, (c) every v0.1 fm key preserved, (d) `scope: project` / `enforcement: default` / zero-state `confidence` injected where required, (e) backup mirrors original byte-for-byte, (f) migration journal records 20 assets, (g) migrated store validates with 0 errors, (h) rollback restores byte-for-byte, (i) re-run is no-op. Also fixed `plan_migration` to skip `MEMORY.md` (was reporting 21 moves while live migrated 20). 14 new tests, 400 total passing |
| T-36 | Update `engram init` to accept `--subscribe=<pool>` and `--org` / `--team` | done | | T-17, T-30, T-33 | `--subscribe <pool>` (repeatable) writes `[subscribe.<pool>]` to pools.toml + creates `.memory/pools/<pool>` symlink. `--org <name>` / `--team <name>` assert the scope is already joined at `~/.engram/<kind>/<name>/.git` (actionable error pointing at `engram <kind> join` if not). Pre-flight validation fails before the scaffold is written so misuse leaves no half-initialized project. Extracted `engram/pool/actions.py::subscribe_to_pool` as the canonical subscribe function; `engram pool subscribe` now delegates to it so init and the pool subcommand share one code path. 11 new unit tests, 411 total passing |
| T-37 | `pools.toml` schema validation in `engram validate` | done | | T-20, T-30 | New `engram/commands/validate_pool.py` adds POOL-family checks. SPEC §12.10 codes implemented: E-POOL-001 (pinned+no revision), E-POOL-002 (subscribed pool missing at `~/.engram/pools/<name>/`), E-POOL-003 (dangling rev/current for auto-sync/notify), W-POOL-002 (pool missing `.engram-pool.toml`). New codes (deviations documented): E-POOL-000 (malformed pools.toml as Issue, not crash), E-POOL-004 (subscribed_at enum), E-POOL-005 (propagation_mode enum), E-POOL-006 (pinned_revision with non-pinned mode), E-POOL-007 (pinned_revision points at missing rev dir). Deferred: W-POOL-001 (needs propagation engine), W-POOL-003 (needs pool manifest publisher-scope). 14 new tests, 425 total passing |
| T-38 | Scope-aware relevance ranking in `engram memory search` | done | | T-19, T-30, T-33 | `engram/commands/memory.py` exports `SCOPE_WEIGHTS` (project=1.5 / user=1.2 / team=1.0 / org=0.8 / pool=1.0 default) per DESIGN §5.1 Stage 6 and `ENFORCEMENT_WEIGHTS` (mandatory=2.0 / default=1.0 / hint=0.5). `apply_scope_weighting(ranked, meta)` folds both multipliers into the BM25 raw score; `scope=pool` assets project onto their `subscribed_at` level. Unknown enum values degrade to a neutral 1.0 rather than crashing. `engram memory search` now returns a JSON payload with `raw_score`, `score`, `scope`, `enforcement` per hit and text output tags each line `[scope/enforcement]`. Rationale for the M3 multiplier approach (vs M4 Relevance Gate's Stage-1 mandatory bypass) is documented inline. 11 new tests, 436 total passing |
| T-39 | Tests for scope conflict resolution per SPEC §8.4 decision tree | done | | T-30, T-33, T-38 | New `engram/core/scope_conflict.py` exposes pure `resolve_conflict(candidates) -> Resolution` encoding all five §8.4 rules (enforcement absolute → hierarchy specificity → native-before-pool → LLM-arbitrates → same-pool internal = raise). `ConflictCandidate`, `Resolution`, `PoolInternalConflict` public. 20 test scenarios in `tests/unit/cli/test_scope_conflict.py` (exceeds 15+ minimum): edge cases, all four §8.4 worked examples, rule 1 override of rule 2, pool at every level vs native, rule 4 arbitration at each enforcement level, rule 5 same-pool. Function is side-effect-free — M4 Relevance Gate (T-40) and `engram review` (later) both import it. 20 new tests, 456 total passing, ruff + mypy clean |

---

### M4 — Intelligence Phase 1-2 + Adapters + MCP

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-40 | `engram/relevance/gate.py` — DESIGN §5.1 7-stage pipeline | done | | T-14, T-42, T-43 | Pure function `run_relevance_gate(RelevanceRequest) -> RelevanceResult`. Six active stages: mandatory bypass (Stage 1) → BM25 recall (Stage 2/T-42) → vector recall (Stage 3, T-41 placeholder, no-op pass-through) → temporal boost (Stage 4/T-43) → scope + enforcement weighting (Stage 5, reads from `relevance/weights.py`) → greedy budget pack by score-per-token (Stage 6). Zero-match docs are dropped; mandatory assets are kept separate from the ranked list. Recency decay + temporal multiplier both gated on presence of a temporal phrase — old curated rules don't get decayed out when the query has no "yesterday"/"last week" intent. 11 new tests |
| T-41 | `engram/relevance/embedder.py` — bge-reranker-v2-m3 local default + config for cloud providers | todo | | T-40 | Lazy-load model on first use; falls back to BM25-only if model absent |
| T-42 | `engram/relevance/bm25.py` + stop word list | done | | — | New module. `STOP_WORDS` frozenset(32) + `MIN_TOKEN_LENGTH=3` token filter per DESIGN §17. `tokenize()` lowercases, splits non-alnum, drops stop words + short tokens. Okapi-BM25 k1=1.5 b=0.75 (MemPalace baseline); zero-score docs dropped rather than appended with 0. `engram.commands.memory` re-exports `bm25_scores` for backward compat (old tests pass unchanged). 16 new tests |
| T-43 | `engram/relevance/temporal.py` — "N weeks ago" parsing + date boost | done | | — | New module. `parse_temporal_hint(query, now)` recognizes today/yesterday/last week/last month/N {days,weeks,months} ago; returns the earliest-matching reference date or None. `temporal_distance_multiplier(candidate, reference)` in `[0.6, 1.0]`; linear decay across a 30-day window (0 days → 0.6 = 40% distance reduction, ≥30 days → 1.0). Months normalized to 30 days for deterministic arithmetic (calendar-aware is M5+). 18 new tests |
| T-44 | Scope + enforcement weighting + recency decay in Relevance Gate | todo | | T-41, T-42, T-43 | `confidence_score` from DESIGN §9 feeds recency decay |
| T-45 | Relevance cache — LRU per DESIGN §3.3 | todo | | T-40 | Cache key: (query_hash, scope_hash, budget); TTL = 5 min |
| T-46 | `engram/consistency/engine.py` — 4-phase dispatcher | todo | | T-14 | Phase 1+2 implemented here; Phase 3+4 dispatched but stub-returning in M4 |
| T-47 | `engram/consistency/phase1_static.py` — SPEC §12 error detection at write time | todo | | T-12, T-46 | 7 conflict classes; returns structured ConflictReport list |
| T-48 | `engram/consistency/phase2_semantic.py` — DBSCAN clustering + 6 cluster rules | todo | | T-41, T-46 | Clusters by embedding; detects factual-conflict and topic-divergence |
| T-49 | `engram/consistency/resolve.py` — 6 action implementations | todo | | T-47, T-48 | Actions: update / supersede / merge / archive / dismiss / escalate; none auto-executes |
| T-50 | `engram/inbox/messenger.py` — SPEC §10 + dedup + rate limit | todo | | T-14, T-15 | Dedup by code-ref; rate limit 10 messages/repo/day; journal every event |
| T-51 | `engram/mcp/server.py` — stateless MCP server (stdio + SSE transports) | todo | | T-14, T-40 | Implements MCP protocol; no session state; one process per client |
| T-52 | `engram/mcp/tools.py` — pydantic schemas for all read + inbox MCP tools | todo | | T-51 | Tools: `engram_memory_read`, `engram_memory_search`, `engram_context_pack`, `engram_inbox_list`, `engram_inbox_send` |
| T-53 | `adapters/claude-code/` + hooks: `engram_stop.sh` + `engram_precompact.sh` | todo | | T-40 | Hook latency <500ms per DESIGN §20; marker-bounded injection in CLAUDE.md |
| T-54 | `adapters/codex/` + `adapters/gemini-cli/` + `adapters/cursor/` + `adapters/raw-api/` | todo | | T-53 | Each adapter: one template file + install instructions; Cursor uses `.cursor/rules/` |
| T-55 | `engram adapter <tool>` CLI — generate + regenerate with marker-bounded update | todo | | T-53, T-54 | Regenerates only between engram markers; user content outside markers untouched |
| T-56 | `engram context pack` — DESIGN §6.3 output format | todo | | T-40 | `--task`, `--budget`, `--format=prompt|json|markdown`; respects scope hierarchy |
| T-57 | E2E: full P0 CLI parity test | todo | | T-19, T-20, T-22, T-30, T-50, T-51, T-55 | Runs all P0 commands against a fixture store; asserts exit codes + output shapes |

---

### M4.5 — Benchmark infrastructure

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-58 | `benchmarks/BENCHMARKS.md` — template (MemPalace discipline: baseline before change, delta tracked) | todo | | T-57 | Includes reproducibility instructions; CI runs only on release tags |
| T-59 | `benchmarks/consistency_test/` — 50 synthetic samples × 7 conflict classes | todo | | T-47, T-48 | 7–8 samples per class; each is a pair of assets + expected ConflictReport |
| T-60 | `benchmarks/scope_isolation_test/` — 30 scope scenarios | todo | | T-38, T-39 | Covers mandatory/default/hint interactions + pool subscribed_at levels |
| T-61 | `docs/HISTORY.md` — corrections log starter (one entry per benchmark run) | todo | | T-58 | Format: date, metric name, before, after, cause |
| T-62 | CI hook: benchmarks run on release tag only (not every commit) | todo | | T-58, T-59, T-60 | GitHub Actions job triggered by `v*` tag; results appended to HISTORY.md |

---

### M5 — Workflow + Autolearn

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-70 | `engram/workflow/` module + CLI subcommands: add / run / revise / promote / rollback / list / test | todo | | T-13, T-14 | Workflow directory structure per SPEC §6; `add` creates skeleton |
| T-71 | `engram/workflow/runner.py` — spine execution (python / bash / toml) with sandbox | todo | | T-70 | `toml` spine is declarative steps; `python` + `bash` run in subprocess; captures stdout/stderr |
| T-72 | `engram/workflow/fixtures.py` — fixture harness | todo | | T-70, T-71 | Loads `fixtures/`; runs spine; diffs actual vs expected output |
| T-73 | `engram/workflow/rev.py` — rev / current symlink management, git-native | todo | | T-70, T-71 | Each revision is a git commit; `current` symlink points to active rev |
| T-74 | `engram/autolearn/engine.py` — Darwin ratchet loop | todo | | T-71, T-72, T-73 | Ratchet: every round is a commit; metric regress → auto-revert; improve → keep |
| T-75 | `engram/autolearn/proposer.py` — separate LLM subagent for change proposals | todo | | T-74 | Called as subprocess; receives workflow + fixture results; proposes diff only |
| T-76 | `engram/autolearn/judge.py` — separate LLM evaluator | todo | | T-74, T-75 | Independent context from proposer; no self-assessment; grades against dual rubric |
| T-77 | Dual evaluation rubric: static 60 pts (SPEC compliance + fixtures + parseable + no secrets) + performance 40 pts (fixture pass + metric Δ > 0) | todo | | T-75, T-76 | Rubric is a TOML file in `engram/autolearn/rubric.toml`; versioned |
| T-78 | Phase gate: pause after K=5 consecutive autolearn rounds; write diff summary to `engram review` | todo | | T-74, T-76 | K is configurable; human must confirm before next phase begins |
| T-79 | `engram workflow autolearn <name>` CLI | todo | | T-74, T-75, T-76, T-77, T-78 | Flags: `--rounds=N`, `--dry-run`, `--phase-gate=K` |
| T-80 | E2E: release-checklist workflow autolearns 10 rounds with monotone improvement | todo | | T-79 | Fixture workflow in `tests/fixtures/workflows/release-checklist/`; metric must not regress |
| T-81 | `workflows/<name>/journal/evolution.tsv` writer | todo | | T-74, T-77 | Columns: round, score_static, score_perf, total, change_summary, kept |

---

### M6 — KB + Inbox full + Consistency Phase 3-4

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-90 | `engram/kb/` module + CLI subcommands: new-article / compile / list / read | todo | | T-13, T-14 | KB directory structure per SPEC §7; `new-article` creates chapter skeleton |
| T-91 | `engram/kb/compiler.py` — `_compiled.md` generation with `_compile_state.toml` | todo | | T-90 | Calls LLM provider (configurable); writes digest; records chapter hashes |
| T-92 | KB chapter watcher → stale digest detection in `engram review` | todo | | T-90, T-91 | Compares stored chapter hashes vs current; flags stale in review output |
| T-93 | `engram/consistency/phase3_llm.py` — LLM-assisted review (optional, opt-in per config) | todo | | T-46, T-47, T-48 | Disabled by default; provider-agnostic; prompts LLM to review conflict proposals |
| T-94 | `engram/consistency/phase4_execution.py` — fixture verification for workflows | todo | | T-71, T-72, T-93 | Runs workflow fixtures; marks workflow-decay conflicts when fixtures fail |
| T-95 | Pool propagation `notify` + `pinned` modes (beyond M3's auto-sync) | todo | | T-30, T-31 | `notify`: journal entry + `engram review` flag; `pinned`: lock to revision ID in pools.toml |
| T-96 | Inbox reverse notification: sender sees resolution on next session startup | todo | | T-50 | Adds `resolved_at` + `resolution_note` to inbox journal; shown in startup summary |
| T-97 | Full `engram_inbox_*` MCP tools (write tools: send / acknowledge / resolve / reject) | todo | | T-52, T-50 | Extends M4 read-only MCP to include write operations |
| T-98 | Usage outcome journal → confidence update batch pipeline | todo | | T-14, T-15 | Reads outcome events from journal; recomputes `confidence_score` per DESIGN §9 |
| T-99 | E2E: cross-repo inbox roundtrip (send → acknowledge → resolve → reverse-notify) | todo | | T-50, T-96 | Two fixture repos in `tests/fixtures/`; asserts all four states reached |

---

### M7 — Web UI P0

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-110 | `web/backend/` FastAPI scaffold + `engram web serve / open` CLI hook | todo | | T-14 | Python 3.11+; uvicorn; auto-open browser on `open` |
| T-111 | `web/backend/app/sse.py` — Server-Sent Events for live updates | todo | | T-110 | One SSE stream per connected client; sends asset-change events from watcher |
| T-112 | `web/backend/app/watcher.py` — inotify (Linux) / FSEvents (macOS) filesystem watcher | todo | | T-110 | Emits events to SSE; debounces at 200ms; ignores `.git/` and `__pycache__/` |
| T-113 | `web/backend/app/auth.py` — none / basic / token auth modes (config-driven) | todo | | T-110 | Default = none (localhost only); basic and token via `config.toml`; no cloud auth |
| T-114 | `web/frontend/` SvelteKit scaffold | todo | | T-110 | SvelteKit + Vite; served from FastAPI static mount in dev; built to `web/frontend/build/` |
| T-115 | i18n files: `en.json` + `zh.json` | todo | | T-114 | All UI strings externalized from day 1; no hardcoded English in `.svelte` files |
| T-116 | Dashboard page (P0) | todo | | T-114, T-115, T-111 | Asset counts, wisdom sparklines, attention items (validate errors + stale KB + inbox unread) |
| T-117 | Memory Detail page | todo | | T-116 | Frontmatter + body read-only view; inbound/outbound references; blame timeline from journal |
| T-118 | Workflow Detail page (view only — run from CLI) | todo | | T-116 | Shows doc + spine side-by-side; rev list with scores; last autolearn round summary |
| T-119 | KB Article page (read only) | todo | | T-116 | Source chapters + `_compiled.md` side-by-side; stale badge when digest is out of date |
| T-120 | Inbox page | todo | | T-116, T-111 | Lists messages by state (unread / acknowledged / resolved); send form |
| T-121 | Context Preview page (the critical debug page from DESIGN §7.1) | todo | | T-116, T-40 | Task input → simulated context pack → shows each loaded asset with rank + reason |
| T-122 | Playwright smoke tests for all 6 P0 pages | todo | | T-116, T-117, T-118, T-119, T-120, T-121 | No 500s; no broken links; WCAG AA via axe-playwright |
| T-123 | `engram web serve / open` CLI integration | todo | | T-110, T-114 | `serve` starts backend; `open` opens browser; `--port` flag; graceful shutdown |

---

### M8 — Evolve + Team full + TS SDK + remaining Web UI + migrate sources

| ID | Task | Status | Owner | Depends on | Notes |
|----|------|--------|-------|------------|-------|
| T-130 | `engram/evolve/engine.py` — ReMem action-think-refine loop (evo-memory-inspired) | todo | | T-14, T-48 | Monthly cadence by default; proposals only; never auto-executes; writes to review queue |
| T-131 | 4 evolve refinement types: merge / split / promote-to-KB / rewrite | todo | | T-130 | Each type has a proposal schema and a diff preview in `engram review` |
| T-132 | Wisdom Metrics aggregation pipeline | todo | | T-15, T-77, T-98 | Reads journal; computes 4 curves; writes `wisdom_snapshot.json` |
| T-133 | `engram/wisdom/curves.py` — 4 curve calculations per DESIGN §5.6 | todo | | T-132 | Curves: workflow mastery, task recurrence efficiency, memory curation ratio, context efficiency |
| T-134 | Web UI Graph page (D3 force layout — assets + references + subscriptions) | todo | | T-116 | Nodes: Memory / Workflow / KB; edges: references + pool subscriptions; click → detail page |
| T-135 | Web UI Pools page | todo | | T-116, T-95 | Pools × subscribers table; propagate UI; shows propagation mode per subscriber |
| T-136 | Web UI Project Overview page | todo | | T-116, T-132 | All engram projects on the machine; wisdom metric comparison table |
| T-137 | Web UI Wisdom page | todo | | T-116, T-132, T-133 | 4 curve charts with regression annotations; `engram wisdom report` mirrors this as text |
| T-138 | Web UI Autolearn Console page | todo | | T-116, T-81 | Live `evolution.tsv` tail; start / pause controls; past runs with score history |
| T-139 | TypeScript SDK — `@engram/sdk` npm package | todo | | T-51, T-52 | Mirrors Python SDK base; MCP client wrapper; types generated from pydantic schemas |
| T-140 | 6 additional migrate sources: chatgpt / mem0 / obsidian / letta / mempalace / markdown | todo | | T-34 | Each is a standalone module in `engram/migrate/`; one sub-task per source is fine |
| T-141 | `engram playbook` command family: install / publish / list / uninstall | todo | | T-70, T-90 | Playbook = Workflows + KB articles + seed Memory; distributed via GitHub URL |

---

## 4. Parallelization guide

Most M2 core modules are sequential because each builds on the one before (paths → fs → graph_db → frontmatter). After T-14 (graph_db) and T-15 (journal) are done, subsequent tasks branch out.

Parallel opportunities by phase:

- **During M2**: T-10 through T-15 are sequential infrastructure; T-16 through T-22 can overlap once T-10 is done.
- **M3 and M4 overlap**: once M2 is merged, M3 scope tasks (T-30–T-39) and M4 adapter tasks (T-53–T-56) touch different modules and can run in parallel. Relevance Gate (T-40–T-45) and Consistency Engine (T-46–T-49) are independent of each other and of the adapter work.
- **M5 / M6 / M7 are independent features**: after M4 is tagged, all three milestones can run in parallel. Workflow (M5), KB (M6 T-90–T-92), and Web UI backend scaffold (M7 T-110–T-113) have no shared code paths.
- **M4.5 benchmarks** run alongside M5–M6. They require M4's consistency engine (T-47, T-48) and scope engine (T-38, T-39) but nothing from M5 or M6.
- **M8 Web UI pages** (T-134–T-138) can start in parallel with M8 migrate sources (T-140) and TypeScript SDK (T-139) — all are independent.
- **Cross-milestone dependency to watch**: T-98 (confidence update pipeline) is needed by T-132 (Wisdom aggregation). Do not start T-132 until T-98 is done.

---

## 5. Newcomer-friendly tasks

Good first issues — well-scoped, no deep architecture knowledge required:

- **T-07** — Join the external review of SPEC + DESIGN. Read two documents, open issues for anything unclear. No code.
- **T-61** — Write `docs/HISTORY.md` starter. One corrections log entry in the format: date, metric name, before, after, cause. Pure markdown.
- **T-53 / T-54 (any one adapter)** — Each adapter is a single template file. Pick one tool you already use (Cursor, Codex, raw-api). Well-scoped; self-contained; no shared state.
- **T-115** — i18n translation improvements. Add missing strings to `en.json` / `zh.json`. Use terms verbatim from `docs/glossary.md`.
- **T-59 or T-60 (add one fixture)** — Add one synthetic benchmark sample. T-59 = one asset pair + expected ConflictReport. T-60 = one scope conflict scenario. Each is a few files.
- **T-140 (pick one source)** — Each migrate source is a standalone module. Obsidian and markdown are the easiest starting points; they need no API access.

If you are new to the codebase, read `SPEC.md §4` (Memory format) and `DESIGN.md §3` (storage layer) before picking a task. The `docs/glossary.md` is the authoritative term list — use it, don't invent synonyms.

---

## 6. Contentious / deferred items

These are design questions that came up during SPEC + DESIGN review and were deliberately deferred. They are not tasks. If you want to re-open one, start a GitHub Discussion, not an Issue.

- **Cross-machine sync**: v0.2 recommends rsync or git for `~/.engram/user/` across machines. A first-party `engram sync` daemon (possibly CRDT-based) is P2. The sync story is intentionally minimal for v0.2 to avoid building infrastructure that turns engram into a cloud service.
- **LLM-side consistency enforcement**: the Consistency Engine currently works post-hoc (scan → propose → human acts). Runtime intercept of LLM outputs to block enforcement=mandatory violations is P2 and requires a proxy layer that does not exist in v0.2. This is a non-trivial trust and correctness problem.
- **Federated pool registry**: pools are installed by GitHub URL (`engram playbook install github:<owner>/<repo>`). A discoverable community registry is P2. The local-first design makes a centralized registry a significant trust and governance problem that the project is not ready to address.
- **Mobile web support**: the Web UI targets desktop browsers only in v0.2. Read-only browsing from mobile may work but receives no design investment. No native app is planned (see DESIGN §13.4 Non-Goals).
- **CRDT for concurrent Memory edits**: v0.2 uses optimistic concurrency (atomic rename) and escalates real conflicts to the Consistency Engine for human resolution. Full OT or CRDT is in P2; the use case (two people editing the same Memory asset simultaneously) is rare enough that the overhead is not justified.
- **Multilingual embeddings**: the default embedding model (bge-reranker-v2-m3) is trained primarily on English. Non-English retrieval quality is untested. Swapping the model is configurable; first-party non-English support is P2 pending hardware profiling and quality measurement.

---

## 7. Board maintenance rules

- Every PR touching a task MUST update the task's status in this file. The PR description should reference the T-ID.
- New tasks get the next available T-XX number. Do not reuse numbers from abandoned tasks.
- Completed tasks keep their row; set status = `done`. Do not delete rows.
- Split tasks: append sub-IDs inline (T-11a, T-11b). The parent row's Notes column points at the sub-tasks.
- Abandoned tasks: set status = `abandoned` with a short reason in Notes. Keep the row.
- Milestone ordering changes require a PR touching both this file and (if applicable) DESIGN §13. A milestone re-order is a direction decision — use GitHub Discussions first, then PR.
- The `Last updated` date in the header is updated in every PR that touches this file.

---

Board maintained by the engram community. Open a PR to add or update a task. For direction-level discussion (milestone ordering, P2 vs P1 promotions), use GitHub Discussions.
