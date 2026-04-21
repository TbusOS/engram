[English](DESIGN.md) · [中文](DESIGN.zh.md)

# engram System Design

**Version**: 0.2 (draft)
**Status**: Design draft, companion to SPEC v0.2
**Last updated**: 2026-04-18
**Canonical**: https://github.com/TbusOS/engram/blob/main/DESIGN.md
**Glossary**: [docs/glossary.md](docs/glossary.md) — all terms here follow that table
**SPEC**: [SPEC.md](SPEC.md) — format contract this design implements

---

## 0. Purpose

`DESIGN.md` specifies the **implementation architecture** of engram v0.2. `SPEC.md` defines the on-disk format; this document defines what code must be built to work with that format, how that code is organized into five layers, and why each layer has the shape it does.

### SPEC vs DESIGN split

The dividing line is: if changing a detail would require every tool that reads the store to update, it belongs in SPEC. If it describes how a particular tool (engram-cli, engram-web, MCP server) implements the spec, it belongs here in DESIGN.

Concrete examples: the YAML frontmatter schema for a Memory asset is SPEC territory. The Python function that validates that frontmatter is DESIGN territory. The `enforcement` field semantics are SPEC. The algorithm the Consistency Engine uses to detect `rule-conflict` violations is DESIGN.

### Scope

DESIGN covers Layer 2 (Control) through Layer 5 (Observation). Layer 1 is entirely SPEC territory; do not redefine anything from SPEC here.

- **Layer 2 — Control**: the `engram` CLI family; all subcommands, flags, error codes, and output formats.
- **Layer 3 — Intelligence**: the Relevance Gate, Consistency Engine, Autolearn Engine, Evolve Engine, Inter-Repo Messenger, and Wisdom Metrics — the optional components that make the store self-improving.
- **Layer 4 — Access**: adapters, MCP server, prompt pack, Python SDK, TypeScript SDK — how LLMs talk to the store.
- **Layer 5 — Observation**: `engram-web`, the first-class human-facing dashboard for viewing the knowledge graph and managing the store.

### Audience

Tool implementers are the primary audience: anyone building an engram-compatible CLI, adapter, web server, or SDK should be able to derive a complete implementation plan from SPEC plus DESIGN together. Design reviewers (evaluating architectural decisions) are the secondary audience. Advanced users who want to understand why the system behaves as it does are the tertiary audience.

### Contract boundary

DESIGN describes concrete technology choices — Python + FastAPI, SQLite for the graph cache, bge-reranker-v2-m3 for local embeddings — that may be revised over time without breaking SPEC compatibility. A tool that stores the graph in LanceDB instead of SQLite is still a conforming engram implementation as long as it satisfies every invariant in this document and every rule in SPEC.

Subsequent chapters cover each layer in detail; §2 provides the five-layer overview.

---

## 1. v0.1 → v0.2 Positioning Change

### 1.1 Change table

| Dimension | v0.1 | v0.2 | Reason for change |
|-----------|------|------|-------------------|
| **Architecture layers** | 3 (data / CLI / adapters) | 5 (data / control / intelligence / access / observation) | Intelligence and observation address genuinely new concerns that could not be folded into CLI or adapters without creating unacceptable coupling. |
| **Memory subtypes** | 4 (`user`, `feedback`, `project`, `reference`) | 6 (adds `workflow_ptr`, `agent`) | Richer epistemic modeling: `workflow_ptr` is a lightweight index entry pointing to a full Workflow asset; `agent` captures LLM-derived meta-heuristics distinct from human-authored `feedback`. |
| **First-class assets** | Memory only | Memory + Workflow + Knowledge Base | Three kinds of knowledge are genuinely different in structure, lifecycle, and loading path; collapsing them into a single type produced oversized, hard-to-load Memory files. |
| **Scope model** | 2 levels (local / shared pool via symlink) | 5 labels across 2 axes: hierarchy (`org` / `team` / `user` / `project`) + orthogonal subscription (`pool` with `subscribed_at`) | Real teams share knowledge in more than one way. Linear hierarchy cannot express "a topic pool subscribed at team level but without team membership" and cannot express org-wide mandatory rules that still allow project overrides at a different enforcement level. |
| **Enforcement** | Implicit (all memories have equal weight) | Explicit (`mandatory` / `default` / `hint`) | Deterministic conflict resolution requires an explicit authority ordering. Without enforcement levels, two contradictory rules are unresolvable. |
| **MEMORY.md capacity** | Hard cap at 200 lines | Unbounded hierarchical landing index | Scales to thousands of assets spread across scopes; the index is structured by hierarchy and type so an LLM can navigate it incrementally rather than loading it all at once. |
| **Capacity maintenance** | User self-manages by manual review | Consistency Engine detects 7 conflict classes and proposes remediation; never auto-mutates | Quality maintenance that scales. Manual review breaks down at 500+ assets; evidence-driven proposals surface what matters without destroying anything. |
| **Cross-project knowledge** | Symlink-based shared pool | Pool propagation (auto-sync / notify / pinned) + Inter-Repo Messenger inbox | Two complementary mechanisms: pool propagation for topic-scoped knowledge that many projects share; inbox for point-to-point messages between specific repos. Each covers cases the other cannot. |
| **LLM access paths** | Adapters only (prompt templates) | Adapters + MCP server + prompt pack + Python SDK + TypeScript SDK | Meet LLMs where they are: IDE integrations use MCP; small/local models use prompt pack; custom agents use the SDKs. Adapters remain for the simplest case. |
| **Web UI** | None | First-class Observation Layer (`engram-web`, FastAPI + Svelte) | Humans need to see the knowledge graph, simulate context loading, and review Consistency Engine proposals. A CLI-only interface cannot provide the spatial overview that catches quality problems early. |
| **Self-improvement** | None | Autolearn Engine (workflow-level) + Evolve Engine (memory-level) + Wisdom Metrics (four quantitative curves) | Measurable evidence that the store gets smarter over time, not just bigger. Wisdom Metrics turn "it feels more useful" into a number that can regress or improve. |
| **Backend abstraction** | None (filesystem only) | `BaseCollection` ABC for the vector/graph store | Swap ChromaDB for LanceDB or PostgreSQL+pgvector without touching any upper layer; the interface is the contract, not the storage engine. |

### 1.2 Why 3 → 5 layers

The v0.1 three-layer architecture (data / CLI / adapters) was adequate for a single-user, single-tool memory system. Adapters were thin prompt templates; the CLI did everything else. When v0.2 added intelligence components — Relevance Gate, Consistency Engine, Autolearn Engine, Evolve Engine — these could not be stuffed into the CLI layer without making CLI commands LLM-dependent and untestable in isolation. Intelligence is optional and must be disableable; it needed its own layer with its own on/off switches.

The Observation Layer is similarly distinct. A web server with a graph renderer is not a CLI command. Forcing it into the CLI layer would mean the CLI has a dependency on FastAPI and Svelte, which is absurd. Layer 5 depends on Layer 4's data-access primitives but adds an entirely different runtime (a long-lived HTTP server, not a one-shot command). Five layers is the minimal count that separates these concerns without creating cross-layer dependencies.

### 1.3 Why 2 → 5 scope labels

The v0.1 scope model — local vs. a shared pool via symlink — expressed two things: "this project only" and "everything in this pool." This worked for a single user working on multiple personal projects. It broke when real teams arrived.

A team uses knowledge at multiple granularities simultaneously: the organization mandates compliance rules, the platform team owns the design system, individual engineers have personal preferences, and specific projects have their own local conventions. A linear four-level hierarchy (`org > team > user > project`) handles membership-based inheritance naturally. But topic pools — shared knowledge about a technology domain like `kernel-work` or `android-bsp` — are not membership-based. A pool about Linux kernel development is relevant to the BSP team and to two individual engineers, but it is not a membership constraint: subscribing to the pool does not make you a team member. The two axes are genuinely orthogonal.

The `subscribed_at` field resolves the authority question without inventing a new axis: a pool subscribed at `org` has the same authority as org-level content for all projects in the org; a pool subscribed at `project` is authoritative only for that one project. The pool's content participates in conflict resolution at the declared hierarchy level, not at a fixed "pool level" that would be either too high or too low for every use case simultaneously.

### 1.4 Why add the Consistency Engine

The Consistency Engine is the single biggest capability bet in v0.2. The premise is that a store which grows without quality maintenance becomes a liability: contradictory rules pile up, stale references remain valid in the index, project-era facts stay active after the project ends. v0.1 relied on users to catch this manually. Manual review works at 20 assets; it fails at 200 and is hopeless at 2000.

The Consistency Engine runs a four-phase scan — structural validation, semantic conflict detection, reference health checks, and staleness scoring — and surfaces proposals without executing them. This is the critical design choice: proposals, not mutations. An auto-correcting engine that modifies assets silently would destroy the trust that makes the store reliable. Users must confirm every change; the engine provides the evidence.

The seven conflict classes (`factual-conflict`, `rule-conflict`, `reference-rot`, `workflow-decay`, `time-expired`, `silent-override`, `topic-divergence`) cover the full taxonomy of quality problems observed in real stores. The `confidence_score` formula (`(validated - 2×contradicted - staleness_penalty) / max(1, total_events)`) distills this into a single number per asset, making prioritization tractable even at large scale.

---

## 2. Five-Layer Architecture

### 2.1 Layer diagram and roles

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Layer 5  Observation         engram-web: Dashboard / Graph / Context    │
│           (FastAPI + Svelte)  Preview / Inbox / Autolearn / ...          │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 4  Access              Adapters | MCP Server | Prompt Pack        │
│           (LLM-facing)        | Python SDK | TypeScript SDK              │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 3  Intelligence        Relevance Gate · Consistency Engine ·      │
│           (optional, gated)   Autolearn · Evolve · Inter-Repo Messenger  │
│                               · Wisdom Metrics                           │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 2  Control             engram CLI: memory / workflow / kb / pool  │
│           (LLM-optional)      / team / org / inbox / consistency /       │
│                               context / mcp / web / playbook / migrate   │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 1  Data                .memory/ directory + ~/.engram/            │
│           (SPEC-defined)      SPEC-compliant markdown; any LLM can read  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Layer 1 — Data** is the on-disk format: the `.memory/` directory tree and the user-global `~/.engram/` hierarchy. It depends on nothing but the filesystem and, optionally, git. Everything above Layer 1 reads and writes these files. Layer 1 is entirely specified in SPEC; DESIGN does not redefine it.

**Layer 2 — Control** is the `engram` CLI family. It depends on Layer 1 (reads and writes SPEC-compliant files), orchestrates Layer 3 components when they are enabled, and exposes the user-facing command surface. It is LLM-optional: every command runs correctly with no LLM present. Layer 3 and Layer 4 depend on Layer 2 for store access primitives. Technology choice: Python 3.10+ with click; §3 (in this document) specifies the full command surface.

**Layer 3 — Intelligence** contains the optional components that make the store self-improving: the Relevance Gate (ranks candidates into context budget), Consistency Engine (detects conflict classes and proposes remediation), Autolearn Engine (workflow-level evolution), Evolve Engine (memory-level evolution), Inter-Repo Messenger (point-to-point cross-repo communication), and Wisdom Metrics (quantitative self-improvement evidence). Layer 3 depends on Layer 2 for store reads and writes. Layer 4 (the MCP server and SDKs) calls Relevance Gate to assemble context. Layer 3 is gated: every component has a configuration flag; the system remains fully correct with all intelligence disabled. §5 (in this document) specifies each component.

**Layer 4 — Access** is the LLM-facing surface: adapters (one-file prompt templates per tool), the MCP server (`engram mcp serve`), the prompt pack (`engram context pack`), the Python SDK, and the TypeScript SDK. It depends on Layer 2 for store access and Layer 3 for the Relevance Gate. Nothing above Layer 4 is part of the reference implementation; adapters are the terminal layer for LLMs. §6 (in this document) specifies each access path.

**Layer 5 — Observation** is `engram-web`: a FastAPI backend + Svelte frontend providing the Dashboard, Graph, Memory Detail, Workflow Detail, Context Preview, Autolearn Console, Pool Manager, and Inbox pages. It depends on Layers 2–4 for data and intelligence. Layer 5 is entirely optional: a system with only Layers 1–4 is fully functional and SPEC-compliant. §7 (in this document) specifies the web UI.

### 2.2 Dependency rules

1. **Layer N depends only on Layer N−1.** Layer 3 may call Layer 2 APIs; it must not directly manipulate Layer 1 files except through Layer 2 primitives.
2. **Layer 1 depends on nothing but the filesystem** and, optionally, git for history. No Python import, no network call, no LLM.
3. **Layer 1 (filesystem shape) is SPEC territory.** DESIGN specifies behavior of Layers 2–5; it does not redefine directory layout, file naming, or frontmatter schema.
4. **Layer 3 components are independently disableable.** Disabling the Relevance Gate, the Consistency Engine, or the Autolearn Engine does not affect SPEC compliance or the correctness of Layers 1, 2, 4, or 5.
5. **Layer 5 is optional.** The CLI alone (Layers 1–4) must produce a fully functional, SPEC-compliant system. The web UI adds observability; it does not gatekeep any store operation.

### 2.3 Invariants

These five invariants apply across all layers. Any implementation of engram MUST satisfy all of them. A conforming implementation that violates any invariant is non-conforming regardless of how well it satisfies other requirements.

1. **Data independence.** Layer 1 never references any tool-specific path or format. A v0.2-compliant store — a directory of markdown files following SPEC — works with zero engram-cli installed. Any LLM can read it. Any text editor can edit it. Any version control system can track it.

2. **No auto-delete.** No layer may delete an asset from the store silently. Deletions always flow through `archive/` with a retention floor of six months before physical removal. The Consistency Engine and Evolve Engine produce proposals; only an explicit human or LLM instruction through `engram memory archive` or `engram workflow archive` moves an asset to `archived` state. Mandatory assets at `enforcement: mandatory` require action at the scope that created them.

3. **Append-only journals.** `~/.engram/journal/*.jsonl` files are never edited in place. New events are appended. Compaction (for storage management) moves complete journal files to `archive/journal/` and starts a new file; it never deletes events or modifies existing rows.

4. **Intelligence is gated.** Every Layer 3 component has a configuration flag (`relevance_gate.enabled`, `consistency_engine.enabled`, `autolearn.enabled`, `evolve.enabled`, `messenger.enabled`, `wisdom_metrics.enabled`) that defaults to a defined value and can be overridden in `.memory/config.toml` or `~/.engram/config.toml`. With all intelligence disabled, the system still validates, reads, writes, and exports correctly.

5. **Deterministic conflict resolution.** Given the same set of assets and the same `pools.toml`, the Relevance Gate's scope/enforcement ranking and the SPEC validator's conflict detection produce the same output across runs, environments, and versions. No random seeds, no implementation-defined tie-breaking, no environment-sensitive behavior.

### 2.4 Technology stack preview

Detailed technology justification is given in the layer-specific chapters. The table below provides the reference implementation choices and the alternatives that third-party implementations may use.

| Layer | Primary technology | Alternative allowed |
|---|---|---|
| L1 — Data | Markdown + YAML frontmatter (filesystem-native) | — (SPEC-defined; not substitutable) |
| L2 — Control | Python 3.10+ / click (`engram-cli` pip package) | Go, Rust, TypeScript (any language that produces a conforming CLI) |
| L3 — Intelligence | Python + SQLite (`graph.db`, embedding cache) + bge-reranker-v2-m3 (local embed) | Per-component: see §5; e.g. LanceDB or pgvector for vector store |
| L4 — Access | Python (MCP server + Python SDK), TypeScript (`@engram/sdk`), plain text (prompt pack) | Any language for custom adapters; MCP transport: stdio or SSE |
| L5 — Observation | FastAPI (HTTP backend) + Svelte (frontend) + Server-Sent Events | — (reference implementation only; web UI is optional) |

"Primary technology" denotes the reference implementation shipped with engram-cli. Third-party tools that implement any subset of the stack — for example, a pure Go CLI that satisfies all Layer 2 behavior — are conforming engram implementations as long as they satisfy every DESIGN invariant and every SPEC rule.

---

---

## 3. Layer 1 Data — Implementation Decisions

### 3.0 Overview

§3 covers how the **reference engram-cli implementation** handles concerns that sit around Layer 1 without being Layer 1 itself. The on-disk format — directory layout, file naming, YAML frontmatter, journal file structure — is entirely SPEC territory and is not repeated here. What §3 specifies are the *systems* the CLI builds to work with that format safely and efficiently:

| Subsection | Concern |
|---|---|
| 3.1 | Filesystem conventions: atomic writes, permissions, symlinks, encoding |
| 3.2 | `graph.db` — SQLite schema for the asset inventory, reference graph, subscriptions, inbox, consistency, and usage tracking |
| 3.3 | `~/.engram/cache/` — embedding, FTS5, relevance, and compiled-KB caches |
| 3.4 | `~/.engram/journal/` — append-only event files and per-workflow journals |
| 3.5 | `~/.engram/archive/` — retention, restore, and physical-deletion policy |
| 3.6 | `~/.engram/workspace/` — isolated per-run sandboxes for autolearn, evolve, and consistency scans |
| 3.7 | Snapshot backup and restore |
| 3.8 | Concurrency protection — WAL mode, file locks, optimistic asset concurrency |
| 3.9 | Cross-machine synchronization strategies |

Third-party implementations are free to replace any subsystem here (e.g., store the graph in LanceDB, skip the embedding cache entirely) as long as they satisfy every SPEC rule and every DESIGN invariant from §2.3.

---

### 3.1 Filesystem Conventions

#### Atomic writes

All writes to asset files, config files, and index files go through a **write-temp-then-rename** pattern:

```python
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(content, encoding="utf-8")
os.replace(tmp, path)   # POSIX: atomic rename; Windows: falls back to shutil.move
```

This guarantees that a process crash or power loss never leaves a partial file at the canonical path. The `.tmp` file is either complete or absent; it is never half-written and mistaken for a valid asset.

#### Permissions

| Path | Mode |
|---|---|
| `~/.engram/` | `0700` — private; owner-only access |
| All directories inside `~/.engram/` | `0755` |
| All text files (`*.md`, `*.jsonl`, `*.toml`, `*.json`, `*.yaml`) | `0644` |
| `graph.db`, `cache/*/index.db`, `cache/embedding/vectors.db` | `0644` |

#### Symlinks

Symlinks are used for two purposes in a SPEC-compliant store:

1. **Pool subscription**: `.memory/pools/<name>` → `~/.engram/pools/<name>/current/`
2. **Workflow revision pointers**: `workflows/<name>/rev/current` → `rev/<timestamp>/`

The tool MUST follow symlinks on read. Writes MUST resolve the symlink target and write atomically to the resolved path; the tool must never write to the symlink path itself (which would replace the symlink with a regular file).

On POSIX, symlink creation/replacement is atomic via `os.symlink` + `os.replace` on a tmp symlink. On Windows, symlinks require Developer Mode or administrator privileges; the tool logs a warning and falls back to junction points.

#### Case sensitivity

All paths are **case-sensitive** per POSIX. On case-insensitive filesystems (macOS HFS+ in default mode, Windows NTFS), the tool maintains a `~/.engram/case-map.json` file mapping canonical lower-case asset IDs to their on-disk cased paths. Reads always go through the map; writes normalize to the canonical casing.

#### Encoding and line endings

- All text files: **UTF-8**; BOM is forbidden.
- Line endings: **LF only**. The tool normalizes CRLF → LF on read and on write.
- Every text file ends with a single **`\n`** (newline at EOF). The tool appends `\n` if missing on write.

---

### 3.2 graph.db Schema

`graph.db` is a **SQLite database at `~/.engram/graph.db`**. It is the central index for fast queries across all scopes. It is not authoritative — the filesystem (plus journal files) is authoritative — and can be deleted and rebuilt at any time via `engram graph rebuild`.

**SQLite configuration**: WAL mode enabled; `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;`

```sql
-- Core asset inventory
CREATE TABLE assets (
    id          TEXT PRIMARY KEY,       -- scope-qualified: "local/feedback_push_confirm"
    scope       TEXT NOT NULL,          -- org | team | user | project | pool
    scope_name  TEXT,                   -- for org/team/pool: the name; NULL for local/user
    subtype     TEXT NOT NULL,          -- user | feedback | project | reference | workflow_ptr | agent
    kind        TEXT NOT NULL,          -- memory | workflow | kb
    path        TEXT NOT NULL UNIQUE,   -- path relative to scope root
    lifecycle_state TEXT NOT NULL,      -- draft | active | stable | deprecated | archived | tombstoned
    created     TEXT,                   -- ISO-8601
    updated     TEXT,                   -- ISO-8601
    enforcement TEXT,                   -- mandatory | default | hint | NULL (for workflow/kb)
    confidence_score REAL DEFAULT 0.0,  -- computed from confidence fields in frontmatter
    size_bytes  INTEGER,
    sha256      TEXT                    -- content hash for change detection
);
CREATE INDEX idx_assets_scope     ON assets(scope, scope_name);
CREATE INDEX idx_assets_kind      ON assets(kind);
CREATE INDEX idx_assets_lifecycle ON assets(lifecycle_state);

-- Reference graph (edges between assets)
CREATE TABLE references_ (
    from_id TEXT NOT NULL,
    to_id   TEXT NOT NULL,
    kind    TEXT NOT NULL,   -- references | requires | supersedes | overrides | reply_to
    created TEXT,
    PRIMARY KEY (from_id, to_id, kind),
    FOREIGN KEY (from_id) REFERENCES assets(id)
);

-- Pool subscriptions
CREATE TABLE subscriptions (
    subscriber_scope  TEXT NOT NULL,   -- project path | user | team:<name> | org:<name>
    pool_name         TEXT NOT NULL,
    subscribed_at     TEXT NOT NULL,   -- org | team | user | project
    propagation_mode  TEXT NOT NULL,   -- auto-sync | notify | pinned
    pinned_revision   TEXT,            -- set only when propagation_mode = pinned
    last_synced_rev   TEXT,
    PRIMARY KEY (subscriber_scope, pool_name)
);

-- Inbox index (for fast "pending messages for repo X" queries)
CREATE TABLE inbox_messages (
    message_id  TEXT PRIMARY KEY,
    from_repo   TEXT NOT NULL,
    to_repo     TEXT NOT NULL,
    intent      TEXT NOT NULL,   -- bug-report | api-change | question | update-notify | task
    status      TEXT NOT NULL,   -- pending | acknowledged | resolved | rejected
    severity    TEXT,
    created     TEXT NOT NULL,
    path        TEXT NOT NULL,   -- full path to the .md file on disk
    dedup_key   TEXT
);
CREATE INDEX idx_inbox_to_status ON inbox_messages(to_repo, status);

-- Consistency proposals
CREATE TABLE consistency_proposals (
    proposal_id     TEXT PRIMARY KEY,
    class           TEXT NOT NULL,          -- factual-conflict | rule-conflict | reference-rot |
                                            -- workflow-decay | time-expired | silent-override | topic-divergence
    severity        TEXT NOT NULL,          -- critical | high | medium | low
    involved_assets TEXT,                   -- JSON array of asset ids
    status          TEXT NOT NULL,          -- open | in_review | resolved | dismissed | expired
    detected_at     TEXT NOT NULL,
    resolved_at     TEXT
);

-- Usage tracking (feeds confidence updates and Relevance Gate utilization signal)
CREATE TABLE usage_events (
    event_id   TEXT PRIMARY KEY,
    asset_id   TEXT NOT NULL,
    event_type TEXT NOT NULL,   -- loaded | validated | contradicted
    task_hash  TEXT,            -- SHA-256 of the LLM task context this was loaded into
    outcome    TEXT,            -- success | failure | ambiguous
    timestamp  TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);
CREATE INDEX idx_usage_asset ON usage_events(asset_id, timestamp);

-- Schema version tracking
CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

#### Rebuild rule

`graph.db` is a **cache derived from the filesystem and journal files**. If it is deleted or corrupted, `engram graph rebuild` regenerates it from scratch by:

1. Scanning all asset files in all scopes, parsing frontmatter, populating `assets`.
2. Parsing `references:` frontmatter fields to populate `references_`.
3. Replaying `~/.engram/journal/propagation.jsonl` to populate `subscriptions`.
4. Replaying `~/.engram/journal/inter_repo.jsonl` to populate `inbox_messages`.
5. Replaying `~/.engram/journal/consistency.jsonl` to populate `consistency_proposals`.
6. Replaying `~/.engram/journal/usage.jsonl` (if enabled) to populate `usage_events`.

Rebuild is idempotent. Running it on an already-consistent database is safe.

---

### 3.3 Cache Directory

```
~/.engram/cache/
├── embedding/
│   ├── version            # embedding model identifier, e.g. "bge-reranker-v2-m3@2025-11"
│   ├── vectors.db         # sqlite-vss; one row per asset: (id TEXT, vector BLOB)
│   └── asset_hash.json    # { asset_id: sha256_at_index_time }; triggers per-asset rebuild on mismatch
├── fts5/
│   └── index.db           # SQLite FTS5 full-text index; one row per asset
├── relevance/
│   ├── manifest.json      # LRU order + per-entry TTL timestamps
│   └── <task_hash>.json   # ranked asset-id list for that task context hash
└── compiled_kb/
    └── manifest.json      # { kb_id: { path, sha256, compiled_at } }; staleness check on KB read
```

#### Embedding cache

- On each asset write, the tool re-embeds **only the changed assets** (identified by sha256 diff against `asset_hash.json`).
- On embedding model version change (detected by comparing `embedding/version` against the configured model), the tool performs a **full rebuild** of `vectors.db` and `asset_hash.json`.
- `vectors.db` uses the sqlite-vss extension. If the extension is absent, the Relevance Gate falls back to BM25 (FTS5) only.

#### FTS5 index

Updated **incrementally** on every asset write. If `index.db` is absent or its `schema_version` row does not match the current schema, the tool rebuilds it from scratch. Rebuild takes O(n) time proportional to total asset count.

#### Relevance cache

- Default TTL: **1 hour** per task-hash entry.
- On any write to an asset with `enforcement: mandatory`, the entire relevance cache is **invalidated** immediately. Mandatory assets always enter context; a change to any mandatory asset could alter which other assets are within budget.
- The manifest caps the cache at 1,000 entries (LRU eviction).

#### Cache is disposable

`engram cache rebuild` regenerates all four subdirectories from the filesystem and `graph.db`. No data is lost; the cache is always reconstructible.

---

### 3.4 Journal Directory

```
~/.engram/journal/
├── propagation.jsonl    # pool propagation events (SPEC §9)
├── inter_repo.jsonl     # cross-repo inbox events (SPEC §10)
├── consistency.jsonl    # consistency proposal lifecycle events (SPEC §11)
├── migration.jsonl      # v0.1→v0.2 (and future) migration events (SPEC §13)
└── usage.jsonl          # (optional; default off) detailed per-load LLM usage events
```

All files are **append-only**. The tool never edits an existing line. Each line is a self-contained JSON object with at minimum `{ "event_type": "...", "sender_id": "...", "seq": N, "timestamp": "ISO-8601", ... }`. The `sender_id` + `seq` pair provides a monotonic ordering that tolerates concurrent appenders (rare in practice; see §3.8).

#### Compaction

When a journal file exceeds `journal.max_size_mb` (default: 100 MB):

1. Copy the current file to `~/.engram/archive/journal/<name>.<ISO-timestamp>.jsonl`.
2. Write a new active file containing only events newer than `journal.hot_window_days` (default: 30 days), prefixed with a compaction-record line: `{ "event_type": "compaction", "archived_to": "<path>", "timestamp": "..." }`.
3. The archived copy is never modified after step 1.

#### Per-workflow journals

Each workflow at `<scope-root>/workflows/<name>/journal/` maintains:

- `evolution.tsv` — one TSV row per autolearn round (SPEC §5 columns)
- `runs.jsonl` — one JSON object per workflow invocation

These use the same append-only + compaction pattern as the global journals, with `journal.hot_window_days` applied independently.

---

### 3.5 Archive Directory

```
~/.engram/archive/
├── assets/
│   ├── memory/
│   │   └── <asset-id>/
│   │       ├── content.md       # the archived asset file
│   │       └── metadata.json    # { archived_at, archived_by, original_path, tombstone_date }
│   ├── workflows/
│   │   └── <workflow-name>/     # same structure: content.md + metadata.json
│   └── kb/
│       └── <topic>/             # same structure
├── journal/                     # compacted journal files (from §3.4 compaction)
└── rev/                         # archived workflow revision snapshots
```

#### Retention policy

| Event | Action |
|---|---|
| `engram memory archive <id>` | Asset moved here; `tombstone_date` = `archived_at` + 6 months |
| Before `tombstone_date` | `engram archive restore <id>` moves it back to active location |
| After `tombstone_date` | Eligible for physical deletion; **not deleted automatically** |
| `engram archive gc --past-retention` | Operator command; removes only assets past their `tombstone_date` |

`engram archive list` displays all archived items, their `archived_at`, and days remaining before `tombstone_date`. No routine tool operation ever removes files from `~/.engram/archive/` without explicit operator invocation of `gc`.

---

### 3.6 Workspace Directory

```
~/.engram/workspace/
├── autolearn-<run-id>/
│   ├── input/        # snapshot of the workflow at the start of the run
│   ├── output/       # spine modifications and fixture outputs proposed by the run
│   └── run.log       # structured log of the run
├── consistency-<run-id>/
│   ├── input/        # snapshot of involved assets
│   ├── proposals/    # candidate proposal JSON files
│   └── run.log
└── evolve-<run-id>/
    ├── input/
    ├── output/
    └── run.log
```

Each workspace is an **isolated sandbox**. Operations inside a workspace cannot touch the active store directly. On success, the workspace's `output/` is applied to the store via atomic commits (write-temp-then-rename for each file). On failure, the workspace is retained so the operator can inspect why the run failed; `engram workspace clean [<run-id>]` discards it.

Run IDs are `<type>-<ISO-timestamp>-<6-char-random>`, e.g. `autolearn-20260418T103045Z-a3f9b2`. The workspace directory is created before the run begins and its existence acts as a run-in-progress lock (a second invocation of the same run type checks for a non-stale workspace and refuses to start, preventing parallel mutations to the same workflow).

---

### 3.7 Backup and Restore

`engram snapshot` creates tarball backups of the full `~/.engram/` tree.

```bash
engram snapshot create                       # ~/.engram-backup/snapshot-YYYY-MM-DD.tar.gz
engram snapshot create --dir=/path/to/dir    # custom output directory
engram snapshot create --include-projects    # also includes .memory/ dirs in known projects
engram snapshot list                         # list snapshots with size, date, and sha256 status
engram snapshot restore <snapshot-name>      # restore to ~/.engram/; prompts before overwriting
engram snapshot diff <snapshot-a> <snapshot-b>  # compare two snapshots (asset-level diff)
```

#### Integrity

Each snapshot tarball is accompanied by a `<name>.sha256` file. `snapshot restore` verifies the sha256 before extracting. If verification fails, restore aborts with an error.

#### Contents

| Included by default | Optional |
|---|---|
| `~/.engram/graph.db` | `.memory/` directories in each known project (`--include-projects`) |
| `~/.engram/journal/` | |
| `~/.engram/archive/` | |
| `~/.engram/cache/` | |
| `~/.engram/user/`, `~/.engram/team/`, `~/.engram/org/`, `~/.engram/pools/` | |

The cache directories are included in the default snapshot so that restore is immediately operational without requiring a rebuild. A `--no-cache` flag omits them for smaller snapshots.

---

### 3.8 Concurrency Protection

engram-cli is a local-first tool. Concurrent invocations from multiple terminals or background processes are possible; the following mechanisms ensure correctness.

| Mechanism | Where applied | Guarantee |
|---|---|---|
| **SQLite WAL mode** | `graph.db`, `cache/fts5/index.db`, `cache/embedding/vectors.db` | Multiple concurrent readers; single writer; readers never block writers |
| **`fcntl.flock` exclusive lock** | `~/.engram/.lock` | Exclusive lock held during migrate, cache rebuild, graph rebuild, and snapshot restore — operations that must not interleave |
| **Atomic file writes** | All asset files, config files, index files | Write-to-tmp + `os.replace`; no partial files at canonical path (see §3.1) |
| **Atomic symlink replacement** | Pool and rev symlinks | `os.symlink(target, tmp_link)` + `os.replace(tmp_link, link_path)` — atomic on POSIX |
| **Optimistic asset concurrency** | Before any asset write | Tool checks current on-disk sha256 against the sha256 cached at last read; mismatch → reload + retry (max 3 retries, then error) |
| **Append-only journals** | All `*.jsonl` files | Each line is a self-contained record; concurrent appenders cannot corrupt existing lines; `sender_id` + `seq` provides post-hoc ordering |

#### Windows note

`fcntl.flock` is not available on Windows. The tool uses `msvcrt.locking` as a fallback for the `.lock` file. SQLite WAL mode works on Windows with the standard SQLite distribution.

---

### 3.9 Cross-Machine Synchronization Strategies

engram is local-first. The reference implementation does not provide a built-in sync protocol for v0.2. Users who work across multiple machines have four supported strategies:

#### Option 1 — git (for team, org, pool scopes)

`~/.engram/team/<name>/`, `~/.engram/org/<name>/`, and `~/.engram/pools/<name>/` are designed to be git repositories. The reference implementation initializes them as git repos on creation. Sync is manual git operations or wrapped by:

```bash
engram team sync <name>    # git pull + push for the named team scope
engram pool sync <name>    # git pull + push for the named pool
```

Merge conflicts are resolved via standard git tooling. Journal files are append-only, so concurrent appends on different machines produce a merge with both sets of events preserved.

#### Option 2 — rsync (for user scope)

`~/.engram/user/` is not a git repo by default. For multi-machine user content:

```bash
# One-way pull from a trusted primary machine:
rsync -avz --delete user@primary:~/.engram/user/ ~/.engram/user/
```

For bi-directional sync, Unison or similar tools that handle conflicts explicitly are recommended over bare rsync.

#### Option 3 — cloud storage symlink

`~/.engram/user/` can be a symlink to a cloud-synced directory (e.g. `~/Dropbox/engram-user/`). The tool follows symlinks correctly. **Caveat:** simultaneous writes from two machines can corrupt `graph.db` because cloud storage lacks atomic rename. Use this approach only if the machines are used at non-overlapping times, or if `graph.db` is excluded from cloud sync and rebuilt locally.

#### Option 4 — custom sync hook

```bash
engram config set sync.post_write_hook="your-sync-command"
```

The hook runs after every write. The user is responsible for making the command safe and idempotent. The tool does not validate or wrap the hook's behavior.

#### Not in scope for v0.2

engram v0.2 does not provide its own sync protocol. A post-v0.2 roadmap item is `engram sync` using a CRDT-based replication model that handles concurrent edits to the same asset across machines without requiring a central server.

---

## 4. Layer 2 Control — CLI Command Family

### 4.0 Command Family Principles

The `engram` CLI is the control plane for the store. Five principles govern every command in the family:

1. **Noun-verb structure.** Commands follow `engram <noun> <verb>` (e.g., `engram memory add`, `engram pool sync`). Top-level verbs — `init`, `status`, `version`, `review`, `validate`, `migrate`, `export`, `snapshot` — operate on the store as a whole and do not need a noun prefix. Every other subcommand belongs to exactly one noun group: `memory`, `workflow`, `kb`, `pool`, `team`, `org`, `inbox`, `consistency`, `context`, `mcp`, `web`, `playbook`, `graph`, `cache`, `archive`, `workspace`, `config`.

2. **Idempotent by default.** Running the same command twice produces the same result. Commands that are inherently non-idempotent — `workflow run` (side effects), `pool publish` (creates a new revision), `inbox send` (creates a new message) — say so in their description and in `--help` output.

3. **Pipeable output.** Every command supports `--json` for machine-readable output. Default output is human-readable, column-aligned, and designed for terminals of 80+ columns. Scripts and CI pipelines always use `--json`. When combined with `--quiet`, only structured JSON is emitted to stdout; warnings go to stderr.

4. **No LLM dependency.** Every CLI command MUST work correctly with no LLM, no API key, and no network access. Commands that optionally invoke intelligence-layer features (e.g., `consistency scan --phase=llm`, `workflow autolearn`) degrade gracefully to their offline equivalent when the LLM is unavailable. No command exits with code 2 solely because a model is unreachable.

5. **Predictable exit codes.** Four codes, nothing else: `0` = clean; `1` = warnings present, operator should review; `2` = operation failed; `3` = operation blocked by precondition failure. See §4.3 for the full contract.

---

### 4.1 Complete Command Inventory

Commands are grouped by noun. Each entry shows the command signature and its purpose. Full `--help` text is in the CLI source; this section is the reference for "which command does X?".

#### Top-level operations

| Command | Purpose |
|---|---|
| `engram init [--scope=...] [--subscribe=...] [--adapter=...] [--org=...] [--team=...]` | Initialize `.memory/` in the current directory |
| `engram status` | Show project engram state: asset counts, scope memberships, pool subscriptions, pending inbox, open consistency proposals |
| `engram version` | Tool version and spec version |
| `engram config <get\|set\|list> <key> [value]` | Read/write `~/.engram/config.toml` |
| `engram review` | Aggregate health check: consistency proposals + pool notifications + inbox pending + stale KB digests |
| `engram validate [--category=...] [--json]` | Run all validation rules from SPEC §12 |
| `engram migrate --from=<source> [--dry-run] [--target=...]` | Migrate from v0.1, claude-code, chatgpt, mem0, obsidian, letta, mempalace, or markdown |
| `engram snapshot <create\|list\|restore\|diff>` | Backup and restore (per §3.7) |
| `engram export --format=<markdown\|prompt\|json> [--output=...]` | Export store contents |

#### Memory operations

| Command | Purpose |
|---|---|
| `engram memory add --type=<subtype> --scope=<scope> [--enforcement=...]` | Create a new Memory asset; interactive prompts when flags are omitted |
| `engram memory list [--type=...] [--scope=...] [--limit=...]` | List memories matching filters |
| `engram memory read <id>` | Print an asset's full content (LLM spine access per SPEC §3.3 MUST 2) |
| `engram memory update <id> [flags]` | Edit frontmatter, body, or move scope |
| `engram memory archive <id> [--reason=...]` | Move to archive (retention policy applies) |
| `engram memory search <query> [--limit=...] [--scope=...]` | Full-text and semantic search |
| `engram memory validate-use <id> --outcome=<success\|failure>` | Record outcome for confidence update (§11 consistency contract) |

#### Workflow operations

| Command | Purpose |
|---|---|
| `engram workflow add <name> --scope=<scope> [--spine-lang=...]` | Scaffold a new Workflow directory |
| `engram workflow run <name> --inputs='<json>'` | Invoke the spine (non-idempotent) |
| `engram workflow revise <name>` | Start a manual revision, creating `rev/rN/` |
| `engram workflow promote <name> --to=<rev>` | Move `current` symlink to a specific revision |
| `engram workflow rollback <name> [--to=<rev>]` | Roll back to a prior revision |
| `engram workflow autolearn <name> [--rounds=...] [--budget=...]` | Start an autolearn loop (Intelligence Layer) |
| `engram workflow list` | List all workflows across scopes |
| `engram workflow test <name>` | Run fixtures against the current revision |

#### Knowledge Base operations

| Command | Purpose |
|---|---|
| `engram kb new-article <topic> --scope=<scope>` | Scaffold a new KB article directory |
| `engram kb compile [<topic>] [--check]` | Regenerate `_compiled.md`; `--check` validates staleness without regenerating |
| `engram kb list` | List all KB articles |
| `engram kb read <topic>[/<chapter>]` | Print an article or a specific chapter |

#### Pool operations

| Command | Purpose |
|---|---|
| `engram pool create <name> [--scope=<initial-scope>]` | Create a new pool at `~/.engram/pools/<name>/` |
| `engram pool list` | List all local pools and subscription status |
| `engram pool subscribe <source> [--at=<hierarchy-level>] [--mode=<auto-sync\|notify\|pinned>]` | Subscribe this project (or user/team/org) to a pool |
| `engram pool unsubscribe <name>` | Remove a subscription |
| `engram pool publish <name> [--message=...]` | Create a new revision, git commit, and push (non-idempotent) |
| `engram pool propagate <name>` | Manual trigger: notify subscribers of the latest revision |
| `engram pool sync [<name>]` | Pull updates from the pool's git remote |
| `engram pool diff <name> --from=<rev> --to=<rev>` | Show changes between revisions |
| `engram pool update <name> --to=<rev>` | Move a pinned subscription to a new revision |

#### Team and Org operations

| Command | Purpose |
|---|---|
| `engram team join <git-url>` | Clone the team repo to `~/.engram/team/<name>/` |
| `engram team sync [<name>]` | Pull updates from the team remote |
| `engram team publish [<name>] [--message=...]` | Commit and push team memories (non-idempotent) |
| `engram team status` | Show team memberships and pending sync |
| `engram org join <git-url>` | Same pattern for org (single-org constraint applies) |
| `engram org sync` | Pull updates from org remote |
| `engram org publish` | Commit and push org memories (non-idempotent) |
| `engram org status` | Show org membership and pending sync |

#### Inbox operations

| Command | Purpose |
|---|---|
| `engram inbox list [--status=<pending\|acknowledged\|resolved\|rejected>] [--to=<repo-id>]` | List messages |
| `engram inbox send --to=<repo-id> --intent=<type> --severity=<level> --message='...' [--code-ref=...] [--deadline=...]` | Send a message (non-idempotent) |
| `engram inbox read <message-id>` | Read a full message |
| `engram inbox acknowledge <message-id>` | Transition pending → acknowledged |
| `engram inbox resolve <message-id> --note='...' [--commit=<sha>]` | Transition → resolved |
| `engram inbox reject <message-id> --reason='...'` | Transition → rejected |
| `engram inbox list-repos` | Show known repo-ids |

#### Consistency operations

| Command | Purpose |
|---|---|
| `engram consistency scan [--classes=...]` | Run a detection scan; creates proposals |
| `engram consistency report [--since=...] [--status=...]` | Show open or recent proposals |
| `engram consistency resolve <proposal-id> --action=<update\|supersede\|merge\|archive\|dismiss\|escalate> [flags]` | Apply a resolution |

#### Context operations (for LLM integrations)

| Command | Purpose |
|---|---|
| `engram context pack --task='...' --budget=<tokens> [--model=...]` | Generate a compact LLM system prompt |
| `engram context preview --task='...' --budget=<tokens>` | Show what would be packed, with diagnostics |

#### Server operations

| Command | Purpose |
|---|---|
| `engram mcp serve [--transport=stdio\|sse] [--port=...]` | Start the MCP server |
| `engram web serve [--port=8787] [--auth=<user:pass>]` | Start the Web UI backend |
| `engram web open` | Open a browser to the local Web UI |

#### Playbook operations

| Command | Purpose |
|---|---|
| `engram playbook install github:<owner>/<repo>[@<ref>]` | Install a playbook from GitHub |
| `engram playbook publish [--remote=...]` | Publish the current playbook |
| `engram playbook list` | Show installed playbooks and source URLs |
| `engram playbook uninstall <name>` | Remove symlinks (files stay in `~/.engram/playbooks/`) |

#### Maintenance operations

| Command | Purpose |
|---|---|
| `engram graph rebuild` | Rebuild `~/.engram/graph.db` from the filesystem (per §3.2) |
| `engram cache rebuild [--embedding\|--fts5\|--relevance]` | Rebuild caches, selectively or all |
| `engram archive list` | Show archived items with retention dates |
| `engram archive restore <id>` | Restore an archived asset to its active location |
| `engram archive gc --past-retention` | Physically delete assets past the 6-month retention floor (requires confirmation) |
| `engram workspace list` | Show active and recent workspaces |
| `engram workspace clean [<id>]` | Remove a workspace or all inactive workspaces |

---

### 4.2 Global Flags

These flags are accepted by every command. Command-specific flags are documented in `--help`.

| Flag | Effect |
|---|---|
| `--json` | Machine-readable output; structured JSON to stdout |
| `--verbose` | Debug-level logging to stderr |
| `--dry-run` | For mutating commands: show what would happen without making changes |
| `--engram-dir=<path>` | Override `~/.engram/`; useful for testing or multi-user setups |
| `--config=<path>` | Use an alternate config file instead of `~/.engram/config.toml` |
| `--scope=<scope>` | Override the inferred scope; rarely needed; mainly for scripts |
| `--quiet` | Suppress all output except errors and JSON (when `--json` is also set) |
| `--help` / `-h` | Print command help and exit |
| `--version` | Print tool version and spec version |

**Config resolution order:** command-line flags > environment variables (e.g., `ENGRAM_DIR`) > `~/.engram/config.toml` > built-in defaults.

---

### 4.3 Exit Code Contract

| Code | Meaning |
|---|---|
| `0` | Operation completed cleanly |
| `1` | Operation completed with warnings; operator should review |
| `2` | Operation failed with errors (SPEC violation, I/O failure, enforcement conflict) |
| `3` | Operation blocked: precondition not met; operation was not attempted |
| `130` | Interrupted by user (SIGINT) |

Concrete examples:

- `engram validate` finds 5 warnings, 0 errors → exit `1`
- `engram validate` finds 2 errors → exit `2`
- `engram migrate --from=v0.1` on an already-v0.2 store → exit `0` (idempotent)
- `engram pool subscribe` with an unreachable remote URL → exit `3`
- `engram memory archive <id>` where `<id>` does not exist → exit `2`
- `engram review` with pending inbox items but no errors → exit `1`
- `engram status` when the store is healthy → exit `0`

Exit code `1` from `validate`, `review`, or `consistency scan` does not indicate a broken store — it indicates that there is something for the operator to look at. CI pipelines that treat exit `1` as a build failure should use `--json` and parse the output to distinguish warning categories.

---

### 4.4 `~/.engram/config.toml` Schema

```toml
[general]
spec_version = "0.2"
user_scope_name = "alice"           # maps to ~/.engram/user/

[embedding]
model = "bge-reranker-v2-m3"        # local model, default
provider = "local"                  # local | openai | cohere | anthropic
api_key_env = "ENGRAM_EMBED_KEY"    # env var holding the API key (if provider != local)
vectors_db = "~/.engram/cache/embedding/vectors.db"

[relevance_gate]
enabled = true
budget_default_tokens = 900
top_k_default = 30
weights_scope = { project = 1.5, user = 1.2, team = 1.0, org = 1.5 }
weights_recency_halflife_days = 30

[consistency]
enabled = true
scan_schedule = "daily"                         # daily | weekly | manual
llm_review_enabled = false                      # phase 3 scan uses LLM; off by default
llm_review_budget_tokens_per_scan = 50000

[autolearn]
default_budget_seconds = 300                    # per round
default_rounds = 10
phase_gate_rounds = 5                           # pause every 5 rounds for human review
complexity_budget_factor = 1.5

[evolve]
enabled = true
cadence = "monthly"
proposals_per_cadence_max = 20

[inbox]
rate_limit_24h = 50
rate_limit_pending = 20
auto_archive_resolved_days = 180
auto_archive_rejected_days = 30

[web]
bind_addr = "127.0.0.1"
port = 8787
auth_mode = "none"                              # none | basic | token
# auth_user = "..."
# auth_pass_hash = "..."

[mcp]
transport = "stdio"
# port = 3000                                   # for sse transport

[git]
auto_commit = false                             # auto-commit on change; off by default
# signing_key = "..."
```

**Config resolution order:** command-line > environment variables > `~/.engram/config.toml` > built-in defaults.

All keys are optional; the tool starts with built-in defaults when the file is absent. `engram config set <key> <value>` writes to this file. `engram config get <key>` reads the resolved value after applying the full resolution order.

---

### 4.5 Command Detail — Key Subset

#### `engram init`

```
engram init [--scope=project] [--org=<name>] [--team=<name>]
            [--subscribe=<pool-source>] [--adapter=<tool>]
```

Creates `.memory/` in the current directory with the full initial scaffold: `local/`, `pools/`, `workflows/`, `kb/`, `pools.toml`, `MEMORY.md`, and `.engram/version`. Interactive prompts cover org/team membership, pool subscriptions, and adapter selection when flags are omitted. `--adapter` writes the appropriate adapter file (e.g., `adapters/claude-code.md`). Running `init` on a directory that already has `.memory/` is a no-op if the store is already at the current spec version; it upgrades gracefully if it finds a v0.1 store.

#### `engram review`

```
engram review [--json]
```

Single command to see everything requiring attention, grouped into five categories:

1. **Consistency proposals** — open proposals by severity
2. **Pool notifications** — pools with pending subscriber notifications
3. **Inbox pending** — messages awaiting acknowledgment
4. **Stale KB articles** — `_compiled.md` older than its source chapters
5. **Stale workflows** — workflows with decaying metrics or past their review date

Returns exit `1` if any category is non-empty; exit `0` if everything is clean. Designed as a morning check or CI gate. With `--json`, the output is structured by category for downstream parsing.

#### `engram validate`

```
engram validate [--category=<class>] [--json]
```

Runs every SPEC §12 validator in sequence. Categories match the SPEC §12 rule classes (e.g., `memory-schema`, `workflow-rev`, `pool-config`, `inbox-format`). Output format is specified in SPEC §12.13. CI-friendly: exit `0` = no issues; exit `1` = warnings only; exit `2` = one or more errors. With `--json`, each issue is a structured object with `rule`, `severity`, `asset_id`, `message`, and `suggestion`.

#### `engram migrate --from=<source>`

```
engram migrate --from=<source> [--dry-run] [--target=<path>]
```

Sources: `v0.1`, `claude-code`, `chatgpt`, `mem0`, `obsidian`, `letta`, `mempalace`, `markdown`. Migration follows SPEC §13.4. `--dry-run` produces a full migration report as JSON to stdout without writing any files. On an already-migrated store, the command is a no-op and exits `0`. Each migration appends an event to `~/.engram/journal/migration.jsonl` for auditability.

#### `engram context pack`

```
engram context pack --task='<description>' --budget=<tokens> [--model=<id>]
```

Invokes the Relevance Gate (Layer 3) to select and rank assets within the token budget, then formats them into a compact system prompt. Fully offline by default — the Relevance Gate uses BM25 + embedding cache; no network call is made unless `--model` is a hosted provider. Adapts token counting to the specified model's tokenizer if one is available; otherwise uses character-based estimation. Output is written to stdout and can be piped directly into an LLM invocation.

#### `engram consistency scan`

```
engram consistency scan [--classes=<comma-list>] [--phase=<1|2|3|4>]
```

Runs the phased consistency scan from SPEC §11. Phases: 1 = structural validation (always offline), 2 = semantic clustering (requires embedding cache), 3 = LLM review (requires `consistency.llm_review_enabled = true`), 4 = fixture execution (requires workflows with fixtures). Each phase is skippable with `--phase`. Proposals are written to `graph.db` and appended to `journal/consistency.jsonl`. Returns exit `1` if new proposals were created; exit `0` if the scan found nothing.

#### `engram pool subscribe`

```
engram pool subscribe <source> [--at=<org|team|user|project>]
                                [--mode=<auto-sync|notify|pinned>]
                                [--pin-rev=<revision>]
```

Subscribes the current project (or the scope named by `--at`) to a pool. `<source>` is a git URL, a `~/.engram/pools/<name>` path, or a playbook reference. The `--at` flag sets the `subscribed_at` level, which controls authority in conflict resolution. On first subscribe, the pool is cloned to `~/.engram/pools/<name>/`; subsequent subscribes reuse the existing clone. Exits `3` if the source URL is unreachable.

---

### 4.6 Evolution Path (P0–P3)

Commands ship in phases aligned to the milestone plan. Later phases depend on infrastructure from earlier phases; P0 ships a complete, working CLI for the most important daily workflows.

**P0 — v0.2 first release (M4 milestone):**

- `init`, `status`, `version`, `config`, `review`, `validate`, `migrate --from=v0.1`
- `memory add/list/read/update/archive/search`
- `pool create/list/subscribe/unsubscribe/publish/sync`
- `team join/sync/publish/status`, `org join/sync/publish/status`
- `inbox list/send/read/acknowledge/resolve/reject`
- `context pack/preview`
- `graph rebuild`, `cache rebuild`
- `archive list/restore`
- `snapshot create/list/restore`
- `export`

**P1 — M5–M6:**

- `workflow add/run/revise/promote/rollback/autolearn/list/test`
- `kb new-article/compile/list/read`
- `consistency scan/report/resolve`
- `migrate --from={claude-code,chatgpt,mem0,obsidian,letta,mempalace,markdown}`
- `inbox list-repos`
- `web serve/open`

**P2 — M7:**

- `mcp serve`
- `pool propagate/diff/update`
- `archive gc`, `workspace list/clean`
- `snapshot diff`

**P3 — post-M8:**

- `playbook install/publish/list/uninstall`
- Enhanced `consistency` features (cross-scope proposals)
- `engram sync` (cross-machine, CRDT-based; see §3.9)

---

## 5. Layer 3 — Intelligence Layer

### 5.0 Overview

The Intelligence Layer is a set of six optional components that add reasoning and self-improvement capabilities on top of the raw data store. Every component is independently disableable; the system operates correctly (albeit without smarts) when all are off. No component is required for SPEC conformance.

#### 5.0.1 Component relationship

```
                    ┌─────────────────────────────────┐
                    │     Layer 4 Access (prompts)    │
                    └───────────────┬─────────────────┘
                                    │ request context
                                    ▼
┌──────────────────────┐    ┌───────────────────┐    ┌──────────────────────┐
│ Consistency Engine   │◄──►│ Relevance Gate    │◄──►│  Wisdom Metrics      │
│ (detects 7 classes;  │    │ (ranks + packs    │    │ (4 curves; analytics)│
│  proposes)           │    │  candidates)      │    │                      │
└────┬─────────────────┘    └───────────────────┘    └──────────┬───────────┘
     │ proposals                   ▲                             │ metrics
     ▼                             │                             ▼
┌──────────────────────┐    ┌──────┴────────────┐    ┌──────────────────────┐
│  Inter-Repo          │    │ Autolearn Engine  │    │  Evolve Engine       │
│  Messenger           │    │ (workflow evolve) │    │  (memory evolve)     │
│  (inbox delivery)    │    │                   │    │  ReMem loop          │
└──────┬───────────────┘    └───────────────────┘    └──────────────────────┘
       │ messages
       ▼
   Layer 1 (Data)
```

#### 5.0.2 Six components

| Component | Purpose | Writes |
|---|---|---|
| **Relevance Gate** | Ranks candidates + packs into context budget | None (read-only query layer) |
| **Consistency Engine** | Detects 7 conflict classes; proposes remediations | `consistency.jsonl` proposals |
| **Autolearn Engine** | Workflow autolearn (Darwin-style ratchet + dual eval) | New workflow `rev/rN/`; `evolution.tsv` |
| **Evolve Engine** | Memory evolution (ReMem action-think-refine) | Proposal records (not mutations) |
| **Inter-Repo Messenger** | Watches + routes inbox messages | `inter_repo.jsonl` events |
| **Wisdom Metrics** | Tracks 4 self-improvement curves | time-series tables in graph.db |

#### 5.0.3 Shared design principles

1. **Suggest, don't mutate** — only Relevance Gate and Inter-Repo Messenger modify state; they modify **transient context**, not assets. Consistency Engine, Autolearn Engine, and Evolve Engine propose; a human or LLM explicitly accepts.

2. **Journal everything** — every intelligence action writes to a journal (`*.jsonl` in `~/.engram/journal/`) for full audit and replay.

3. **Independently disableable** — each component has `[<component>].enabled = false` in `config.toml`; the system remains correct with all components off.

4. **Workspace isolation** — components that run long operations (Autolearn Engine, Evolve Engine, Consistency Engine Phase 3) run in `~/.engram/workspace/<component>-<run-id>/` sandboxes, never touching the live store mid-run.

5. **No LLM dependency on the core path** — Relevance Gate MUST work with local embeddings only. Optional LLM rerank is available but off by default, keeping the wake-up path airgappable.

---

### 5.1 Relevance Gate

**Purpose:** Given a task context and a token budget, select which assets enter the LLM's system prompt. Called on every `engram context pack` invocation and every MCP `engram_context_pack` tool call.

**Inputs:**

```python
{
  "task": str,                      # free-form description of what the LLM needs to do
  "budget_tokens": int,             # context budget (default: 900 for wake-up)
  "model_profile": str | None,      # optional: hint about model context length
  "project_root": str,              # engram project path
}
```

**Outputs:**

```python
{
  "ranked_assets": [
    {
      "asset_id": str,
      "scope": str,
      "score": float,
      "tokens_est": int,
      "inclusion_reason": str,      # "mandatory" | "ranked" | "recency" | "pinned"
    }
  ],
  "packed_prompt": str,             # final system prompt (fits budget)
  "tokens_used": int,
  "tokens_remaining": int,
  "excluded_due_to_budget": [str],  # asset ids dropped for budget
}
```

#### 5.1.1 Pipeline (7 stages)

The pipeline is linear; each stage passes its output to the next.

```
task                                          packed_prompt
  │                                              ▲
  ▼                                              │
(1) Include MANDATORY (bypasses ranking) ──────► [context]
  │
  ▼
(2) Candidate retrieval
    a. Semantic search (vector / cache/embedding/) → top-50
    b. BM25 full-text (cache/fts5/)               → top-50
    c. Structural (subscription + scope)           → all visible
  │
  ▼
(3) Hybrid score fusion
    fused_dist = dist * (1.0 - 0.30 * keyword_overlap)
  │
  ▼
(4) Temporal date boost (if task has "N weeks ago", "last month", etc.)
    fused_dist *= (1.0 - min(0.40 * proximity_factor, 0.40))
  │
  ▼
(5) Two-pass retrieval (if task is "assistant-reference")
    first pass: user-turn-only; second pass: full text on top candidates
  │
  ▼
(6) Scope / enforcement weighting
    score *= scope_weight (project=1.5, user=1.2, team=1.0, org=0.8)
    Recency decay: score *= exp(-days_since_updated / 30)
  │
  ▼
(7) Budget-aware truncation
    Greedy fit by score-per-token; assemble packed_prompt in scope order
  │
  ▼
packed_prompt
```

#### 5.1.2 Stage details

**Stage 1: Mandatory inclusion (bypasses ranking)**

Every asset with `enforcement: mandatory` is unconditionally included before any scoring occurs. Mandatory assets are inserted into `packed_prompt` first, consuming their token budget before ranked candidates are considered.

If mandatory assets alone exceed the available budget, the Relevance Gate emits a hard error:
```
budget insufficient for mandatory rules (N tokens required, M tokens available)
```

Inclusion order within mandatory assets is deterministic: scope-specificity ordering (project first, then user, then team, then org — most specific to least specific) with asset-id alphabetical tiebreak within each scope level. This ensures reproducible output across identical calls.

**Stage 2: Candidate retrieval (three sources, fan-out)**

Three retrieval sources run in parallel and their results are merged:

- **Semantic:** the task string is embedded using the configured embedder; the top K=50 nearest assets (by cosine distance) are fetched from `cache/embedding/vectors.db`. If the embedding cache is absent or the embedder is unavailable, this source is skipped (offline mode).
- **BM25:** the task query is tokenized, stop-words from the 32-term list (glossary §17) are stripped, and keywords ≥3 characters are scored against each candidate asset's body via Okapi-BM25 using `cache/fts5/index.db`. Top-50 results are retained.
- **Structural:** all assets in subscribed pools + all assets whose `tags:` frontmatter field shares at least one tag with any extracted task keyword. This set is unbounded but typically small.

Results from all three sources are unioned and deduplicated by `asset_id`.

**Stage 3: Hybrid score fusion (MemPalace Hybrid v2)**

The hybrid fusion formula is adopted directly from MemPalace's Hybrid v2 pattern, which achieves 98.4% R@5 on LongMemEval:

```
dist    = embedding cosine distance   # lower = more similar
overlap = len(set(task_keywords) & set(asset_keywords)) / max(1, len(task_keywords))
fused_dist = dist * (1.0 - 0.30 * overlap)
```

Lower `fused_dist` means a better match. The 0.30 weight is tuned by MemPalace's published benchmarks; do not change it without re-running the LongMemEval harness (see §5.1.8).

When semantic scores are unavailable (offline mode), `dist` is set to a uniform value of `0.5` for all candidates, and scoring degrades to BM25-only. Quality degrades gracefully; the system does not fail.

**Stage 4: Temporal date boost**

Detect temporal anchors in the task string: "N weeks ago", "last month", "yesterday", "Q1 2026", "last Tuesday", etc. If a temporal anchor is detected:

1. Compute `target_date = query_date - time_offset` (e.g., "3 weeks ago" → subtract 21 days).
2. For each candidate, compute days difference from its `updated` date to `target_date`.
3. Apply boost if within window:

```python
window = days_offset * 1.5    # e.g., "4 weeks ago" → ±42 day window
days_diff = abs((asset.updated_date - target_date).days)
if days_diff < window:
    boost = max(0.0, 0.40 * (1.0 - days_diff / window))
    fused_dist *= (1.0 - boost)   # up to 40% distance reduction
```

Maximum boost is capped at 40% distance reduction (`temporal_max_boost = 0.40`). If no temporal anchor is detected, Stage 4 is a no-op.

**Stage 5: Two-pass retrieval (for assistant-reference queries)**

Detect if the task references what the assistant previously said or suggested: phrases like "you said X", "as you recommended", "your earlier suggestion", "you mentioned", etc.

If detected:
- **First pass:** retrieve top-5 sessions by task keywords against a user-turn-only index (assistant turns are excluded from this index to avoid polluting the global embedding space).
- **Second pass:** re-query those 5 sessions' full text (including assistant turns) with the original task string.

This avoids contaminating the global index with assistant-generated content while still allowing retrieval of assistant-referenced items when explicitly requested.

If the task is not an assistant-reference query, Stage 5 is a no-op and all retrieved candidates pass through unchanged.

**Stage 6: Scope and enforcement weighting**

Apply scope-based multipliers to convert `fused_dist` into a `score` (higher = better):

```python
# Convert distance to score: lower dist → higher score
base_score = 1.0 - fused_dist

weights = {
    "project": 1.5,   # most specific → highest weight
    "user":    1.2,
    "team":    1.0,
    "org":     0.8,   # least specific (but mandatory bypass in Stage 1 is separate)
    "pool":    # inherits the subscribed_at level's weight
}
score = base_score * weights[asset.scope]
```

Then apply recency decay as the final adjustment:

```python
days = (now - asset.updated).days
score *= exp(-days / 30.0)   # 30-day half-life; tunable via weights_recency_halflife_days
```

The recency half-life is 30 days by default. An asset last updated 30 days ago retains ~50% of its scope-weighted score; an asset updated 90 days ago retains ~5%.

**Stage 7: Budget-aware truncation**

1. Sort all scored candidates by `score / tokens_est` descending (value-per-token).
2. Greedily accept items until the remaining token budget is exhausted.
3. Assemble `packed_prompt` in scope order: mandatory first, then project → user → team → org → pool. Within each scope level, order by score descending.
4. Any asset that scored but did not fit is added to `excluded_due_to_budget`.

The greedy sort by score-per-token (not raw score) ensures short, high-relevance assets are preferred over long, marginally-relevant ones, making the most of the available budget.

#### 5.1.3 Token estimation

Token counts are estimated per asset at write time and cached in `graph.db` (`size_bytes` field). The estimation formula:

```
tokens_est = len(body_bytes) * 0.25
```

This is a conservative ratio for English prose (4 bytes per token on average). For code-heavy assets the ratio is slightly lower; for emoji-heavy or CJK assets it is slightly higher. The estimate is not recalculated at query time — it uses the cached value.

**Model-specific adjustments:**

- **Short-context models (≤8k tokens):** budget is shaved by 25% (`budget_short_context_shave = 0.25`) to leave headroom for the user's task-specific prompt.
- **Long-context models (≥100k tokens):** budget can expand up to 9,000 tokens for wake-up context (`budget_long_context_expand_to = 9000`), still a small fraction of total window but enough for a rich context pack.

Token estimates are re-computed on every asset write (to catch major body changes) but the cached value is used during all query-time operations.

#### 5.1.4 Caching

The Relevance Gate uses three levels of caching, all described in §3.3:

**Embedding cache (`cache/embedding/vectors.db`):**
- One vector row per asset; indexed by `asset_id`.
- Invalidated per-asset on write: re-embed only the changed asset (using `asset_hash.json` sha256 diff).
- Full rebuild triggered when `cache/embedding/version` differs from the configured model identifier.
- Cache miss → re-embed and write before proceeding; never fail the query.

**FTS5 cache (`cache/fts5/index.db`):**
- Incrementally updated on every asset write.
- No external dependency: SQLite FTS5 is built into the sqlite3 standard library.
- Full rebuild on schema version mismatch.

**Relevance cache (`cache/relevance/`):**
- Key: `sha256(task + str(budget_tokens) + active_assets_hash)` — captures the full query context.
- Value: serialized `ranked_assets` list + `packed_prompt` string.
- TTL: 1 hour (default; `cache_ttl_seconds = 3600`).
- Invalidated entirely on any write to a mandatory-enforcement asset (since mandatory inclusion affects the entire budget calculation).
- LRU eviction at 1,000 entries (from §3.3).

**Cache hit rate target:** ≥65% for session-start wake-up in steady-state usage, where the same project and similar task patterns repeat daily.

#### 5.1.5 Tuning parameters (`config.toml`)

The `[relevance_gate]` section exposes all tunable parameters:

```toml
[relevance_gate]
enabled = true

# Stage 2: retrieval breadth
candidate_top_k_semantic = 50
candidate_top_k_bm25 = 50
candidate_include_all_subscribed = true

# Stage 3: hybrid fusion
hybrid_keyword_weight = 0.30      # MemPalace-tuned; do not change without benchmarking

# Stage 4: temporal boost
temporal_max_boost = 0.40
temporal_window_multiplier = 1.5

# Stage 5: two-pass
two_pass_enabled = true
two_pass_first_k = 5

# Stage 6: scope weights and recency
weights_scope = { project = 1.5, user = 1.2, team = 1.0, org = 0.8 }
weights_recency_halflife_days = 30

# Stage 7: budget
budget_default_tokens = 900
budget_short_context_shave = 0.25
budget_long_context_expand_to = 9000

# Caching
cache_ttl_seconds = 3600
cache_hit_rate_target = 0.65
```

**Validation rule:** `engram validate` emits warning `W-RG-001` if `hybrid_keyword_weight` is set outside the range [0.15, 0.45] — the range backed by MemPalace's published benchmarks. Values outside this range are allowed but flagged.

#### 5.1.6 Defense against metric gaming

The Relevance Gate optimizes for "most relevant assets fit the budget." Two classes of gaming risk exist:

**Broad-description gaming:** An asset with an extremely broad `description` field will hit the top-K semantic results for almost every query, crowding out genuinely relevant assets.

**Keyword stuffing:** Padding an asset's `body` with task-matching keywords artificially inflates its BM25 score.

Defenses (passive, surfaced to operator rather than auto-penalized):

- `description` field length > 150 characters → `W-FM-002` validation warning (from SPEC §12).
- Asset hit-rate across all relevance queries > 3× the store's per-asset average → flagged as "suspiciously broad" in `engram review` output.
- BM25 score anomaly: if an asset's BM25 score is unusually high relative to its semantic distance (suggesting term-frequency inflation) → "possible keyword stuffing" flag in `engram review`.

All three are **warnings surfaced to the operator, never auto-penalties at query time.** Legitimately broad assets (e.g., user identity, org-wide security policy) should not be penalized for genuine breadth.

#### 5.1.7 Fallback modes

The Relevance Gate operates in three modes, selected automatically:

| Mode | Trigger | Behavior |
|---|---|---|
| **Full** | Default; embedding cache present and embedder reachable | All 7 stages run; semantic + BM25 + structural retrieval |
| **Offline** | No embedding provider or no cache (first run, airgapped) | Stage 2a (semantic) skipped; BM25 + structural only. Quality degrades; system does not fail |
| **Emergency** | Available budget too small for mandatory assets alone | Error emitted; packed_prompt contains only user identity + top-3 mandatory assets by scope-specificity |

Operator can force a mode explicitly:

```bash
engram context pack --task='...' --mode=offline
```

Mode selection is logged to `journal/usage.jsonl` (when usage logging is enabled) so operators can detect when degraded modes are triggering frequently.

#### 5.1.8 Benchmarking

Target metrics for the Relevance Gate:

| Metric | Target | Notes |
|---|---|---|
| LongMemEval R@5 (raw BM25 baseline) | ≥95% | Matching MemPalace's reported raw mode |
| LongMemEval R@5 (hybrid v2) | ≥98% | MemPalace Hybrid v2 result; engram adopts the same algorithm |
| Pack latency (warm cache) | <200ms | For 900-token budget from ≤10k asset store |
| Pack latency (cold cache) | <1s | Full pipeline including embedding lookup |
| Cache hit rate (steady state) | ≥65% | Session-start wake-up, same project, similar task patterns |

**Benchmarking harness:** `benchmarks/longmemeval_relevance_gate.py` — reproduces LongMemEval evaluation on the local asset store. Runs as part of milestone M6 validation per the implementation plan (Amendment B, Section B.3). The harness follows MemPalace's `benchmarks/BENCHMARKS.md` discipline: fixed random seed, public test split only, no hyperparameter tuning against the test set.

To run:

```bash
python benchmarks/longmemeval_relevance_gate.py --store=~/.engram --split=test
```

---

---

### 5.2 Consistency Engine

#### 5.2.0 Role recap

The Consistency Engine detects 7 classes of inconsistency in the engram store (SPEC §11.1), proposes remediation, and **never mutates assets**. Its sole outputs are:

- `~/.engram/journal/consistency.jsonl` — append-only proposal log
- `graph.db consistency_proposals` table — queryable index of proposals (rebuilt from the journal on demand)

The engine does not resolve proposals on its own. Every resolution action requires explicit human or LLM confirmation via `engram consistency resolve`. This upholds the "suggest, never mutate" invariant stated in §5.0.3 principle 1 and SPEC §11.

The 7 classes detected (SPEC §11.1): `factual-conflict`, `rule-conflict`, `reference-rot`, `workflow-decay`, `time-expired`, `silent-override`, `topic-divergence`.

---

#### 5.2.1 Four-phase scan architecture

The engine is organized as four independently-scheduled phases. Each phase can be enabled/disabled individually in `config.toml` under the `[consistency]` section.

```
trigger (scheduled or engram consistency scan)
  │
  ▼
Phase 1: Static checks  (fast, every write, <20 ms/asset)
  ├─ SPEC structural validation
  ├─ frontmatter well-formed
  ├─ references resolve
  └─ lifecycle state transitions legal
  │
  ▼
Phase 2: Semantic clustering  (daily, background)
  ├─ embed all assets  (reuse cache/embedding/)
  ├─ DBSCAN cluster
  ├─ per-cluster: find contradictions via static rules
  └─ emit candidate proposals
  │
  ▼
Phase 3: LLM review  (weekly or on-demand, optional)
  ├─ sample clusters with suspect pairs
  ├─ LLM generates structured proposal JSON
  └─ append to consistency.jsonl
  │
  ▼
Phase 4: Execution verification  (weekly or on-demand)
  ├─ run each workflow's fixtures/
  ├─ emit workflow-decay proposals for failures
  └─ update confidence fields for passing workflows
  │
  ▼
consistency.jsonl proposals
```

**Default schedule summary:**

| Phase | Default trigger | Config key |
|---|---|---|
| Phase 1 | Every asset write | always-on, no config key |
| Phase 2 | Daily at 02:00 local | `[consistency].scan_schedule` |
| Phase 3 | Disabled by default | `[consistency].llm_review_enabled` |
| Phase 4 | Weekly, Saturday 03:00 | `[consistency].phase_4_schedule` |

Each phase is independently configurable (on/off, schedule). Sections 5.2.2–5.2.5 detail each.

---

#### 5.2.2 Phase 1 — Static checks

**Trigger:** Every asset write — `engram memory add`, `engram memory update`, `engram workflow revise`, and any adapter/spine that writes assets.

**Checks (all MUST complete in <20 ms per asset):**

- SPEC §12 structural error codes: `STR-*` (structure), `FM-*` (frontmatter), `MEM-*` (memory-specific), `WF-*` (workflow-specific), `KB-*` (knowledge-base), `IDX-*` (index)
- Reference graph integrity (`REF-*`): all `references:` targets exist; no circular `supersedes:` chains
- Enforcement legality (`ENF-*`): no mandatory override applied without a declaration in `overrides:`
- Scope consistency (`SCO-*`): `scope:` label matches filesystem location; `org/team/pool` names resolve against directory hierarchy

**Implementation:** Runs in-process (not workspace-isolated — it is fast and synchronous). Results are written to the `validation_results` table in `graph.db`:

```sql
CREATE TABLE validation_results (
    asset_id    TEXT NOT NULL,
    code        TEXT NOT NULL,       -- e.g. 'E-FM-003'
    severity    TEXT NOT NULL,       -- error | warning | info
    message     TEXT,
    detected_at TEXT NOT NULL,
    resolved_at TEXT,
    PRIMARY KEY (asset_id, code)
);
```

**Output distinction:** Phase 1 does **not** write to `consistency.jsonl`. Its findings go to the validation table and surface in `engram review` / `engram validate`. The separation exists because Phase 1 results are **write-time structural errors** (should be fixed immediately by the author) rather than **semantic inconsistencies** (which need review and may be intentional).

---

#### 5.2.3 Phase 2 — Semantic clustering

**Trigger:** Scheduled (default: daily at 02:00 local, configurable via `[consistency].scan_schedule`), or invoked directly with `engram consistency scan --phase=2`.

**Algorithm:**

```python
def phase_2():
    # Re-use embedding cache to avoid re-embedding unchanged assets
    vectors = load_embeddings_from_cache()

    # DBSCAN clustering — no need to specify k up front
    clusters = DBSCAN(
        eps=compute_adaptive_eps(vectors),  # 75th-percentile of k-NN distances (k=5)
        min_samples=3,                      # minimum cluster size
        metric='cosine'
    ).fit_predict(vectors)

    proposals = []
    for cluster_id, asset_ids in group_by_cluster(clusters):
        # Apply static rule patterns within each cluster
        for rule_id, matcher in CLUSTER_RULES:
            for match in matcher(asset_ids):
                proposals.append(make_proposal(rule_id, match, cluster_id))

    return proposals
```

**Cluster rules (detect specific inter-asset patterns):**

| Rule | Pattern detected | Proposal class |
|---|---|---|
| CR-1 | Two assets with opposite keyword pairs (e.g., "prefer rebase" vs. "never rebase") | `rule-conflict` |
| CR-2 | Two assets sharing `tags:` but differing on numeric fields or enum choices | `factual-conflict` |
| CR-3 | Newer asset without `supersedes:` pointing to an older same-topic asset in cluster | `silent-override` |
| CR-4 | ≥3 assets discussing the same subject with divergent conclusions | `topic-divergence` |
| CR-5 | Asset referencing a URL/path → spawn HEAD check; 404 returned | `reference-rot` |
| CR-6 | Asset with `valid_to` in the past + ≥1 active asset still referencing it | `time-expired` |

**Adaptive `eps`:** Computed per-run from the k-nearest-neighbor distance distribution (k=5). The elbow point of the sorted distance curve is used, preventing under- or over-clustering as the store grows.

**Performance target:** 10k assets processed in <10 minutes on a single-CPU consumer laptop (no GPU required).

**Workspace isolation:** Phase 2 runs in `~/.engram/workspace/consistency-<run-id>/` for intermediate storage. Proposals are committed to `consistency.jsonl` atomically at the end of the phase.

---

#### 5.2.4 Phase 3 — LLM review (optional)

**Trigger:** `[consistency].llm_review_enabled = true` (default: `false`). Runs weekly when enabled, or on demand via `engram consistency scan --phase=3`.

**Algorithm:**

```python
def phase_3(candidate_proposals):
    # One proposal per cluster, prioritized by severity (critical > high > medium > low)
    sampled = prioritized_sample(candidate_proposals, budget=LLM_REVIEW_BUDGET)

    for proposal in sampled:
        ctx = assemble_context(proposal.involved_assets)
        llm_resp = llm.complete(
            system=CONSISTENCY_REVIEW_SYSTEM_PROMPT,
            user=ctx,
            response_format=ConsistencyReviewSchema,
        )
        if llm_resp.verdict == 'false-positive':
            proposal.status = 'auto-dismissed'
        elif llm_resp.verdict == 'genuine':
            proposal.llm_analysis = llm_resp.analysis
            proposal.suggested_resolutions += llm_resp.additional_resolutions

    return sampled
```

**LLM provider:** Configurable under `[consistency].llm_provider`. Supported options:

- `ollama` / `llama.cpp` — default; runs locally, air-gapped, full privacy
- `anthropic` / `openai` / `google` — explicit opt-in; operator must set API key

**Budget:** `[consistency].llm_review_budget_tokens_per_scan` (default: 50 000 tokens). Scans that would exceed the budget are skipped; a warning is logged.

**Workspace isolation:** Same `~/.engram/workspace/consistency-<run-id>/` workspace as Phase 2. LLM request/response pairs are written to the workspace for audit before the run is committed.

**False-positive defense:** Target false-positive rate ≤5%. If the observed FP rate exceeds 10% over the last 100 LLM reviews (measured by proposals subsequently dismissed by humans), Phase 3 is automatically suspended and the operator is notified via `engram review` and the metrics dashboard.

---

#### 5.2.5 Phase 4 — Execution verification

**Trigger:** Scheduled weekly (default: Saturday 03:00 local, configurable via `[consistency].phase_4_schedule`), or `engram consistency scan --phase=4`.

**Algorithm:**

```python
def phase_4():
    proposals = []
    for workflow in list_all_workflows():
        results = run_fixtures(workflow)   # executes workflow's fixtures/ suite
        for fixture_result in results:
            if fixture_result.failed:
                proposals.append(make_proposal(
                    class_='workflow-decay',
                    involved=[workflow.id],
                    evidence=fixture_result.diff,
                    severity='error' if fixture_result.regression else 'warning',
                ))
            else:
                # Positive confidence signal — workflow still valid
                update_confidence(workflow.id, event='validated')
    return proposals
```

**Budget:** `[consistency].phase_4_time_budget_seconds` (default: 600 seconds total). Individual fixtures that exceed their per-fixture timeout are killed; a `workflow-decay` proposal with `severity=error` is emitted for each.

**Workspace:** Each workflow's fixtures run in their own workspace (`workflows/<name>/rev/current/`), reusing the workflow-specific sandbox rather than a shared engine workspace.

---

#### 5.2.6 Confidence update engine

**Per SPEC §4.8 and §11.4.** This section specifies the update pipeline that feeds those formulas.

**Event sources:**

1. **LLM self-report** — `engram memory validate-use <id> --outcome=success|failure|ambiguous` (called by spines and adapters after using an asset)
2. **Human review** — thumbs-up / thumbs-down in `engram review` TUI and the Web UI
3. **Phase 4 positive signal** — a passing fixture run calls `update_confidence(workflow.id, event='validated')`
4. **Inbox resolution signal** — when a `bug-report` inbox message is resolved, the referenced assets receive a `validated` event

**Pipeline:**

```
event sources
      │
      ▼ append
usage.jsonl  (append-only, never mutated)
      │
      ▼ batch aggregation (every 1 hour or every 100 events, whichever comes first)
      │
      ▼
graph.db  assets.confidence_score  (updated in place)
      │
      ▼ emit if score < threshold
      │
      ▼
consistency.jsonl  (low-confidence proposal)
```

**Confidence formula (SPEC §4.8):**

```python
def recompute_confidence(asset):
    v = asset.validated_count
    c = asset.contradicted_count
    total = max(v + c, 1)

    age_days = (now() - asset.last_validated).days
    staleness = 0.0 if age_days < 90 else 0.3 if age_days < 365 else 0.7

    score = (v - 2 * c - staleness) / total
    return clamp(score, -1.0, 1.0)
```

The formula penalizes contradictions twice as heavily as validations reward, and applies a staleness penalty for assets not validated within the last 90 days.

**Low-confidence threshold:** `[consistency].low_confidence_threshold` (default: −0.2). Assets whose `confidence_score` falls below this threshold trigger a `time-expired` or `topic-divergence` proposal depending on whether the primary signal is staleness or cluster-level divergence.

---

#### 5.2.7 Resolve command application

SPEC §11.5 defines 6 resolution actions. This section specifies the concrete filesystem operations for each.

**`update` — rewrite asset content or frontmatter:**

```python
def apply_update(proposal, target_id, new_content):
    asset = load(target_id)
    updated = {**asset, 'body': new_content, 'updated': now()}
    save_atomic(updated)
    journal.append('proposal_resolved', proposal.id, action='update')
```

**`supersede` — mark older asset as deprecated, link from newer:**

```python
def apply_supersede(proposal, older_id, newer_id):
    newer = load(newer_id)
    updated_newer = {**newer, 'frontmatter': {**newer.frontmatter, 'supersedes': older_id}}
    save_atomic(updated_newer)

    older = load(older_id)
    updated_older = {**older, 'lifecycle_state': 'deprecated'}
    save_atomic(updated_older)

    graph_insert_reference(newer_id, older_id, rel='supersedes')
    journal.append('proposal_resolved', proposal.id, action='supersede',
                   older=older_id, newer=newer_id)
```

**`merge` — consolidate multiple assets into one:**

```python
def apply_merge(proposal, source_ids, target_id, merged_content):
    if not exists(target_id):
        create(target_id, merged_content)
    else:
        apply_update(proposal, target_id, merged_content)
    for src_id in source_ids:
        apply_supersede(proposal, older_id=src_id, newer_id=target_id)
    journal.append('proposal_resolved', proposal.id, action='merge',
                   sources=source_ids, target=target_id)
```

**`archive` — move asset to archive directory:**

```python
def apply_archive(proposal, asset_id, reason):
    asset = load(asset_id)
    dest = f'~/.engram/archive/assets/{asset.kind}/{asset_id}/content.md'
    mv(asset.path, dest)
    write_metadata(f'~/.engram/archive/assets/{asset.kind}/{asset_id}/metadata.json',
                   archived_at=now(), reason=reason)
    graph_update_lifecycle(asset_id, 'archived')
    journal.append('proposal_resolved', proposal.id, action='archive')
```

**`dismiss` — mark proposal as false positive:**

```python
def apply_dismiss(proposal, reason):
    updated_proposal = {**proposal, 'status': 'dismissed', 'dismiss_reason': reason}
    save_proposal(updated_proposal)
    journal.append('proposal_resolved', proposal.id, action='dismiss', reason=reason)
    # Auto-dismiss future identical proposals (same involved_assets + class) for 90 days
    register_dismiss_suppression(proposal.involved_assets, proposal.class_, ttl_days=90)
```

**`escalate` — route to scope maintainer:**

```python
def apply_escalate(proposal):
    updated_proposal = {**proposal, 'status': 'escalated'}
    save_proposal(updated_proposal)
    if is_mandatory_asset(proposal):
        notify_scope_maintainer(proposal)
    journal.append('proposal_resolved', proposal.id, action='escalate')
```

All six `apply_*` functions use `save_atomic` (write to `.tmp` then `rename`) to prevent partial writes. All journal entries follow the SPEC §10 append-only event format.

---

#### 5.2.8 CLI surface recap

`engram consistency` subcommands (from the §4 CLI inventory, with operational detail added):

| Command | Description |
|---|---|
| `engram consistency scan [--phase=1\|2\|3\|4] [--classes=...]` | Trigger scan; default runs Phase 1 + 2; Phase 3 and 4 require explicit `--phase` flag |
| `engram consistency report [--status=...] [--severity=...] [--since=...]` | List proposals matching filters |
| `engram consistency resolve <proposal-id> --action=<action>` | Apply one resolution action |
| `engram consistency dismiss-all --criteria='<jq-expr>'` | Bulk dismiss matching proposals; requires `--yes` confirm (admin, irreversible) |

The `--classes` filter on `scan` accepts a comma-separated subset of the 7 class names, e.g. `--classes=rule-conflict,silent-override`.

---

#### 5.2.9 Observability metrics

Metrics are emitted to a `metrics_consistency` table in `graph.db` and consumed by the Wisdom Metrics component (§5.5):

```sql
CREATE TABLE metrics_consistency (
    run_id          TEXT NOT NULL,
    phase           INTEGER NOT NULL,       -- 1 | 2 | 3 | 4
    run_at          TEXT NOT NULL,
    asset_count     INTEGER,
    proposals_emitted INTEGER,
    proposals_dismissed INTEGER,
    duration_ms     INTEGER,
    PRIMARY KEY (run_id, phase)
);
```

**Key signals:**

| Metric | Purpose |
|---|---|
| Proposal generation rate (per day) | Spike indicates store churn or ingestion issue |
| Detection latency (Phase 1 p50/p95) | Time from asset write to validation result |
| Phase 2 scan duration | Time, asset count, proposals emitted |
| False-positive rate | Proportion of proposals dismissed via `action=dismiss` |
| Resolve throughput | Proposals resolved per day, broken down by action |

These metrics feed the Wisdom Metrics "Memory Curation Ratio" curve (§5.5).

---

### 5.3 Autolearn Engine

#### 5.3.0 Role

Autolearn evolves a specific Workflow asset. Given a workflow with a `spine.*` file, `fixtures/` directory, and `metrics.yaml`, it generates candidate modifications to the spine, runs the fixture suite, and keeps modifications that improve the primary metric — then loops. Losing rounds are archived for audit; winning rounds advance the `current` symlink.

Triggered explicitly by `engram workflow autolearn <name>`. Runs in a workspace-isolated sandbox under `~/.engram/workspace/autolearn-<run-id>/`. On success, writes a new `rev/rN/` directory and moves `current` to point at it. On regression, the symlink stays on the prior rev; the failed rev is committed to history for traceability.

The engine stops after `--rounds=N` (default unlimited within budget) or when a phase gate is reached (§5.3.5). It never modifies `workflow.md`, `fixtures/`, or `metrics.yaml` — those are read-only inputs.

---

#### 5.3.1 The 8 disciplines

Autolearn is disciplined after Karpathy's `autoresearch` 8-discipline agentic loop. Each discipline maps to a concrete mechanism:

**Discipline 1 — Fixed budget per round.**
`[autolearn].default_budget_seconds = 300` (5 min). A round that exceeds this wall-clock budget is killed and treated as a crash failure. The time budget ensures each round is resource-bounded and comparable.

**Discipline 2 — Single-file boundary.**
Only `spine.*` is mutated per round. `workflow.md`, `fixtures/`, and `metrics.yaml` are opened read-only. This constraint keeps the search space tractable and ensures fixture evaluation is always against a known-good harness.

**Discipline 3 — Never stop (within budget).**
If a round fails (non-improvement, rejection, or crash), the engine starts the next round immediately — no pause, no prompt. The `--rounds=N` flag caps total rounds; within that cap, the engine is autonomous. This mirrors autoresearch's "NEVER STOP" instruction: the engine is expected to run unattended until the human interrupts it or the round budget is exhausted.

**Discipline 4 — Append-only results.**
`rev/<N>/outcome.tsv` (per-rev) and `journal/evolution.tsv` (cross-rev) are append-only. Rows are never modified; a new round appends a new row. This creates a tamper-evident audit trail of all autolearn activity.

**Discipline 5 — Keep-or-reset.**
After each round: if the metric improved AND evaluation threshold met → keep new rev (move `current` symlink, git commit). Otherwise → reset (symlink unchanged; failed rev committed for audit). There is no "in-between"; every outcome is either a clean advance or a documented revert.

**Discipline 6 — Simplicity criterion.**
Reject diffs where `new_spine_lines > complexity_budget_factor × old_spine_lines` (default 1.5×). This prevents metric-gaming through complexity explosion — a pattern where an LLM pads the spine with redundant steps to pass fixture checks without genuine improvement. Configurable per-workflow via `metrics.yaml` `complexity_budget_factor`.

**Discipline 7 — Complexity floor.**
The workflow must retain a minimum number of steps/checkpoints after each round. Configurable per-workflow in `metrics.yaml` as `min_steps` (default: current count). Prevents optimization collapse where the LLM "improves" the primary metric by hollowing out the spine to a stub.

**Discipline 8 — Human-reviewable.**
Every K rounds (default `phase_gate_rounds = 5`) autolearn pauses and writes a diff summary to `engram review` as a pending autolearn checkpoint. A human must confirm via `engram workflow autolearn --continue <name>` before the next phase begins. This gives operators visibility into what the engine is doing and ensures no long-running autolearn session escapes human review entirely. The `--unattended` flag disables the gate (§5.3.5).

---

#### 5.3.2 Per-round algorithm

```python
def autolearn_round(workflow, context):
    workspace = create_workspace(f'autolearn-{run_id}-round-{N}')

    # Step 1: load current rev
    current = load_rev(workflow, 'current')
    copy_to_workspace(current, workspace)

    # Step 2: propose (LLM)
    proposer_context = build_context(workflow, recent_outcomes=last_10)
    proposed_diff = proposer_llm.complete(
        system=AUTOLEARN_PROPOSER_PROMPT,
        user=proposer_context,
    )
    apply_diff(workspace, proposed_diff)

    # Step 3: simplicity check (discipline 6)
    if lines(workspace.spine) > complexity_budget_factor * lines(current.spine):
        return RoundResult(status='rejected', reason='complexity_budget_exceeded')

    # Step 4: complexity floor check (discipline 7)
    if count_steps(workspace.spine) < workflow.min_steps:
        return RoundResult(status='rejected', reason='complexity_floor_violated')

    # Step 5: run fixtures (with time budget, discipline 1)
    with time_budget(default_budget_seconds):
        fixture_results = run_fixtures(workspace)

    # Step 6: compute metrics
    new_metrics = aggregate_metrics(fixture_results, workflow.metrics_yaml)

    # Step 7: static eval (60 points)
    static_score = score_static(workspace)   # SPEC validators + schema + no secrets

    # Step 8: performance eval (40 points)
    performance_score = score_performance(
        new_metrics, current.metrics, workflow.ratchet_rule
    )

    total_score = static_score + performance_score  # 0..100

    # Step 9: independent judge (separate LLM session — discipline from Darwin G3)
    judge_ctx = build_judge_context(current, workspace, fixture_results)
    judge_verdict = judge_llm.complete(
        system=AUTOLEARN_JUDGE_PROMPT,
        user=judge_ctx,
    )

    # Step 10: decision (discipline 5)
    if total_score >= threshold and judge_verdict.endorse:
        commit_new_rev(workflow, workspace)
        return RoundResult(
            status='kept', new_rev=f'r{N+1}', metrics=new_metrics
        )
    else:
        archive_failed_rev(workspace)   # for audit (discipline 4)
        return RoundResult(
            status='reverted',
            reason=build_reason(total_score, judge_verdict)
        )
```

**Proposer/Judge separation (Darwin G3):** two distinct LLM sessions with no shared context. The Proposer sees the current workflow, metric history, and fixture descriptions; the Judge sees only the diff and the measured fixture outcomes. This prevents the Proposer from gaming its own evaluation — a known failure mode of single-session self-improvement loops.

The `AUTOLEARN_PROPOSER_PROMPT` instructs the Proposer to reason about *why* the current spine underperforms and produce a minimal targeted diff. The `AUTOLEARN_JUDGE_PROMPT` instructs the Judge to evaluate whether the measured outcomes actually support the claimed improvement, independent of the Proposer's reasoning.

---

#### 5.3.3 Git-native ratchet (Darwin G1)

Each autolearn round is persisted as a real git commit in the workflow's revision history:

```
<scope>/workflows/<name>/
├── workflow.md
├── fixtures/
│   ├── success_case_01.yaml
│   └── failure_case_01.yaml
├── metrics.yaml
├── journal/
│   └── evolution.tsv
└── rev/
    ├── r1/
    │   ├── spine.py
    │   └── outcome.tsv
    ├── r2/
    │   ├── spine.py
    │   └── outcome.tsv
    ├── r3/
    │   ├── spine.py
    │   └── outcome.tsv
    └── current -> r3/      # symlink; only moves forward on accept
```

**Accept path:** `ln -sf r{N+1} current && git add rev/r{N+1}/ && git commit -am "autolearn r{N+1} accepted, primary_metric +X%"`. The commit message includes the metric delta so `git log --oneline` is a human-readable improvement log.

**Reject path:** `git add rev/r{N+1}/; git commit -m "autolearn r{N+1} rejected — reason"`. The symlink does not move. The failed rev is committed for audit purposes (discipline 4) but is not the live version.

**Git history invariant:** every commit on the workflow's branch is either a monotone-improving accept or an explicitly-labelled audit-reject. There are no silent reverts. An operator can reconstruct the full autolearn history from `git log` alone.

**Operational benefits:**
- Full revert via `git reset` (for operator override of any accepted round).
- `git blame spine.py` traces each line in the current spine to the autolearn round that introduced it.
- Distribution: `engram workflow sync` pushes new revs to team or pool remotes, enabling cross-machine autolearn collaboration.

---

#### 5.3.4 Dual evaluation rubric (Darwin G2)

Every round is scored on a 100-point scale combining static compliance and performance improvement.

**Static score (60 points):**

| Criterion | Points |
|---|---|
| SPEC §12 `E-WF-*` validators pass | 20 |
| All fixtures syntactically valid YAML | 10 |
| `spine.*` parses under its declared `spine_lang` | 10 |
| No new secrets or credentials introduced (regex scan) | 10 |
| `metrics.yaml` references all resolve | 5 |
| `inputs_schema` / `outputs_schema` still conform | 5 |
| **Total static** | **60** |

**Performance score (40 points):**

| Criterion | Points |
|---|---|
| All success-case fixtures pass | 15 |
| No failure-case fixture regresses (previously-passing failure cases still pass) | 10 |
| Primary metric Δ improves in the ratchet direction | 10 |
| All additional metrics non-regressing | 5 |
| **Total performance** | **40** |

**Threshold:** default `70/100`. Rounds scoring below threshold are automatically rejected regardless of judge verdict. Configurable per-workflow via `metrics.yaml` field `autolearn_threshold` (range 50–95).

**Judge override:** even if `total_score >= threshold`, a judge `endorse=false` blocks the accept. The judge's written rationale is recorded in `outcome.tsv` for operator review.

---

#### 5.3.5 Phase gate (Darwin G4)

After every K consecutive rounds (default `phase_gate_rounds = 5`), autolearn pauses:

1. Generate phase summary: rounds run, rounds accepted, primary metric Δ since last gate, top-3 spine diffs by line count.
2. Write summary to `engram review` as a pending autolearn checkpoint (same queue as Consistency Engine proposals).
3. Block until the operator runs one of:
   - `engram workflow autolearn --continue <name>` — continue to next phase.
   - `engram workflow autolearn --abort <name>` — stop; archive the run; keep current rev.

**`--unattended` flag:** disables the phase gate entirely. Intended for CI/cron automation. Requires two explicit opt-ins:
- `[autolearn].allow_unattended = true` in `config.toml`.
- A signed commit (maintainer-level GPG key) enabling unattended mode for the specific workflow.

Both conditions prevent accidental or rogue unattended runs. A misconfigured CI job that omits `allow_unattended` will halt at the first gate rather than running indefinitely.

---

#### 5.3.6 CLI surface

| Command | Description |
|---|---|
| `engram workflow autolearn <name> [--rounds=N] [--budget=Ns] [--unattended]` | Start autolearn; rounds and budget default to config values |
| `engram workflow autolearn-status <name>` | Show progress: rounds completed, current rev, pending phase gate, acceptance rate |
| `engram workflow autolearn --continue <name>` | Unblock after phase gate; begin next phase |
| `engram workflow autolearn --abort <name>` | Cancel; preserve audit trail; keep current rev |
| `engram workflow rollback <name> [--to=<rev>]` | Manual rollback to a prior rev (operator override; from §4 CLI inventory) |

All commands exit non-zero and write structured JSON to stderr on error, following the §4 error format convention.

---

#### 5.3.7 Observability

Per-workflow `journal/evolution.tsv` contains one row per round (append-only):

```
rev	ts	proposer_tokens	judge_endorse	static	performance	total	primary_metric	accepted	reason
r1	2026-04-18T10:30:00Z	1248	true	58	35	93	4.2s	true	initial
r2	2026-04-18T10:38:00Z	1440	false	55	28	83	4.5s	false	metric_regress
r3	2026-04-18T10:44:00Z	1320	true	60	38	98	3.9s	true	improvement
```

Fields: `rev` (revision tag), `ts` (ISO 8601), `proposer_tokens` (LLM tokens consumed by proposer), `judge_endorse` (boolean), `static` / `performance` / `total` (scores), `primary_metric` (raw value), `accepted` (boolean), `reason` (free-text from judge or rejection rule).

**Metrics fed to Wisdom Metrics "Workflow Mastery Curve" (§5.6):**

| Signal | Purpose |
|---|---|
| Rounds accepted / total rounds | Acceptance rate; low rate indicates weak proposer or over-tight threshold |
| Primary metric time-series | Improvement trajectory; plateau detection |
| Complexity trend (spine line count over revs) | Catches creeping complexity despite Discipline 6 |
| Time-to-first-improvement | Rounds elapsed before first accept; proxy for workflow difficulty |

---

### 5.4 Evolve Engine

#### 5.4.0 Role

Evolve evolves Memory (and Knowledge Base article) assets. Unlike Autolearn — which directly mutates workflow spines after passing a ratchet check — Evolve **only proposes** refinements. All proposals enter the Consistency Engine's proposal stream and require explicit operator acceptance before any asset is modified.

The design is inspired by evo-memory's **ReMem** loop: action → think → refine. The engine acts on recent usage data (coloading patterns, embedding drift, contradiction events), thinks about what structural changes would improve clarity or coverage, and emits concrete refinement proposals.

Triggered monthly by default (`[evolve].cadence = "monthly"`) or on-demand via `engram evolve scan`. The monthly cadence is deliberately conservative: Memory assets accumulate slowly, and aggressive scanning floods the review queue with proposals faster than an operator can action them.

---

#### 5.4.1 Refinement types

Evolve emits four kinds of proposals. Each maps to one or more `suggested_resolutions` in the Consistency Engine proposal format (§5.2.3).

**Type 1 — Merge (2+ memories → 1)**

- *Trigger:* a cluster of memories with co-load rate > 60% (they appear together in ≥ 60% of Relevance Gate output sets) AND average pairwise cosine distance < 0.20 (high semantic overlap).
- *Proposal action:* merge bodies into a single memory, retain best frontmatter fields, add `supersedes:` on source memories pointing to the merged target.
- *Rationale:* two memories consistently loaded together and semantically nearly identical impose double the token cost with negligible information gain.

**Type 2 — Split (1 memory → N)**

- *Trigger:* a single memory at or above the 95th percentile length for its type AND sentence-level DBSCAN clustering of its body reveals ≥ 2 distinct sub-topic clusters.
- *Proposal action:* create N new memories (one per sub-cluster), each with a focused title and body; mark the original as deprecated with `supersedes:` chain pointing to all N successors.
- *Rationale:* dense memories increase the risk of partial relevance — the Relevance Gate retrieves the whole memory when only one sub-topic is needed, inflating context cost.

**Type 3 — Promote to KB article**

- *Trigger:* 3 or more related memories that are all at high length percentile, frequently co-loaded (>60%), AND topic-coherent (tight semantic cluster with centroid clearly nameable).
- *Proposal action:* draft a new Knowledge Base article (auto-generated `README.md` skeleton plus proposed chapter structure); rewrite source memories as `reference`-typed pointers to the new KB article's sections.
- *Rationale:* when multiple large memories orbit the same topic, they are candidates for promotion to a structured KB article that supports partial loading by chapter.

**Type 4 — Rewrite for clarity**

- *Trigger:* a memory with `confidence_score < -0.2` AND ≥ 2 recent contradiction events (from Consistency Engine history) AND stable usage (not trending toward deprecation — still being loaded regularly).
- *Proposal action:* LLM-generated rewrite preserving all key claims but clarifying ambiguous language; new body text appears in the proposal record; operator reviews side-by-side before accepting.
- *Rationale:* a memory that keeps triggering contradictions is probably under-specified, not factually wrong. Rewriting for precision resolves the contradiction detection at the source.

---

#### 5.4.2 Algorithm

```python
def evolve_scan():
    # Phase 1: gather candidates

    candidates = []

    # Merge candidates
    for cluster in dbscan_cluster_memories(eps=0.15, min_samples=2):
        if coloading_rate(cluster) > 0.60 and avg_cosine_dist(cluster) < 0.20:
            candidates.append(MergeCandidate(cluster))

    # Split candidates
    for mem in memories_at_p95_length():
        sub_clusters = sentence_level_cluster(mem.body)
        if len(sub_clusters) >= 2:
            candidates.append(SplitCandidate(mem, sub_clusters))

    # Promote candidates
    for cluster in high_length_coloaded_clusters():
        if len(cluster) >= 3 and topic_coherent(cluster):
            candidates.append(PromoteCandidate(cluster))

    # Rewrite candidates
    for mem in memories_below_confidence(-0.2):
        if contradiction_count(mem, window_days=90) >= 2:
            if not trending_to_deprecation(mem):
                candidates.append(RewriteCandidate(mem))

    # Phase 2: budget + prioritization
    prioritized = prioritize_by_impact(
        candidates,
        budget=config.proposals_per_cadence_max   # default 20
    )

    # Phase 3: propose (LLM generates concrete proposal bodies)
    for candidate in prioritized:
        llm_proposal = generator_llm.complete(
            system=EVOLVE_GENERATOR_PROMPT[candidate.type],
            user=candidate.context(),
        )
        emit_consistency_proposal(
            class_='evolve-refinement',
            sub_class=candidate.type,           # merge | split | promote | rewrite
            involved_assets=candidate.assets,
            llm_analysis=llm_proposal.analysis,
            suggested_resolutions=[llm_proposal.resolution],
        )

    # Phase 4: metrics
    update_evolve_metrics(
        cadence_run_at=now(),
        proposals_emitted=len(prioritized),
        candidates_found=len(candidates),
    )
```

**Key design choice:** Evolve writes nothing to assets directly. Its sole output is proposal records appended to `consistency.jsonl`, the same channel as Consistency Engine proposals. This means the operator's `engram review` queue is a single unified surface for all proposed changes — no separate "evolve review" UI required.

**Prioritization logic (`prioritize_by_impact`):** candidates are scored by estimated token savings (for merge/split/promote) or estimated contradiction resolution probability (for rewrite), then sorted descending. The top `proposals_per_cadence_max` are retained; the rest are discarded for this cadence and re-evaluated next time.

---

#### 5.4.3 Workspace and sandbox

Evolve runs in `~/.engram/workspace/evolve-<run-id>/`. Sandbox contents:
- Read-only copy of `graph.db` (snapshotted at scan start; not updated during scan).
- Scratch area for embedding recomputations and clustering intermediate results.
- LLM request/response logs (for reproducibility and debugging).

On completion, only serialized proposal records leave the sandbox; they are appended to `consistency.jsonl`. Intermediate data (embeddings, cluster matrices) is discarded. The sandbox directory is retained for `[evolve].workspace_retention_days` (default 7) then deleted.

---

#### 5.4.4 Integration with Consistency Engine

Proposals emitted by Evolve use a distinct `class` prefix: `evolve-refinement-merge`, `evolve-refinement-split`, `evolve-refinement-promote`, `evolve-refinement-rewrite`. They are stored in the same `consistency_proposals` table and appear in the same `engram review` queue as Consistency Engine proposals.

The `class` prefix enables fine-grained filtering:

```bash
engram consistency report --classes=evolve-refinement-merge,evolve-refinement-split
engram consistency report --classes=rule-conflict,factual-conflict
```

**Resolution path:** Evolve proposals accept the same six resolution actions as Consistency Engine proposals (§5.2.5): `update`, `supersede`, `merge`, `archive`, `dismiss`, `escalate`. The most common resolution for a merge proposal is `merge`; for a split proposal it is `supersede` (deprecated original) + `update` (create successors).

**Analytics separation:** Wisdom Metrics (§5.6) counts Evolve proposals separately under the "Memory Curation Ratio" curve (tagged `source=evolve`) to distinguish intentional structural evolution from passive conflict detection. This allows operators to answer: "Is my store evolving intelligently, or just accumulating conflicts?"

---

#### 5.4.5 CLI surface

| Command | Description |
|---|---|
| `engram evolve scan [--types=merge,split,promote,rewrite]` | Run scan; default runs all four types |
| `engram evolve status` | Show stats for most recent scan: candidates found, proposals emitted, acceptance rate from prior scans |
| `engram evolve enable [--types=...]` | Enable specific refinement types (all enabled by default) |
| `engram evolve disable [--types=...]` | Disable specific refinement types without disabling the engine |

Proposals generated by Evolve are reviewed and resolved via the standard `engram review` and `engram consistency resolve` interfaces — no separate evolve-specific resolve command.

---

#### 5.4.6 Safety

Evolve has four hard safety constraints:

1. **Write-nothing invariant.** Evolve never modifies assets or the live graph directly. Its only side effect is appending records to `consistency.jsonl`. If `consistency.jsonl` is read-only (e.g., in a CI environment), the scan aborts rather than writing to an alternate location.

2. **No unilateral reduction.** Evolve never proposes actions that reduce total memory count without a corresponding supersession chain. Every merge or split proposal must include complete `supersedes:` linkage so no knowledge is silently lost.

3. **Cadence warning.** If `[evolve].cadence` is set to an interval shorter than monthly (`< 30d`), engram emits a startup warning: `"evolve cadence <X> is aggressive; review queue may exceed operator capacity"`. This is a warning, not an error — the operator can acknowledge and proceed.

4. **Review queue cap.** `[evolve].proposals_per_cadence_max` (default 20) caps proposals per scan run. If more than 20 candidates pass all filters, only the top 20 by impact score are emitted. This prevents a single scan from flooding the queue with proposals faster than an operator can review them.

---

### 5.5 Inter-Repo Messenger

#### 5.5.0 Role

The Inter-Repo Messenger implements the cross-repo inbox contract defined in SPEC §10. Its job is point-to-point message delivery between repositories on the same developer machine: one repo's LLM agent sends a structured message; the recipient repo's LLM reads it at next session start; both parties track lifecycle transitions. This section specifies the daemon, the fs operations behind every state transition, dedup and rate-limit enforcement, and the MCP tool surface. All wire formats (message frontmatter, event schema, intent semantics) are authoritative in SPEC §10; this section describes the implementation that satisfies that contract.

---

#### 5.5.1 Architecture

```
┌──────────────────────────┐       ┌──────────────────────────┐
│  Repo A session          │       │  Repo B session          │
│  ┌────────────────────┐  │       │  ┌────────────────────┐  │
│  │ LLM calls          │  │       │  │ LLM reads inbox on │  │
│  │ engram inbox send  │  │       │  │ session start      │  │
│  └──────┬─────────────┘  │       │  └──────┬─────────────┘  │
└─────────┼────────────────┘       └─────────┼────────────────┘
          │                                  ▲
          ▼                                  │
     ~/.engram/inbox/<repo-b-id>/pending/    │
          │                                  │
          ▼                                  │
   watcher daemon (fs watch inotify/kqueue) ─┘
          │
          ▼
   inter_repo.jsonl events + graph.db inbox_messages updates
```

**Components:**

| Component | Responsibility |
|---|---|
| `engram inbox send` CLI / MCP tool | Validates input, enforces dedup + rate limit, writes message file atomically, appends to `inter_repo.jsonl`, inserts row into `graph.db inbox_messages` |
| Watcher daemon | Watches `~/.engram/inbox/*/pending/` with `inotify` (Linux) or `kqueue` (macOS); on `IN_CREATE` / `NOTE_WRITE`, updates `graph.db` and notifies any active Web UI session via SSE |
| `engram context pack` | At session start, reads `pending/` for the current repo and injects messages into the context under `## Pending Cross-Repo Messages` |
| `graph.db inbox_messages` | Indexed view of all messages; powers Web UI `/inbox` page and fast queries by status/intent/severity/deadline |
| `inter_repo.jsonl` | Append-only global event journal (SPEC §10.7); the canonical record for reverse-notification and audit |

**Daemon startup.** The watcher daemon starts automatically under `engram daemon start` or as a background thread inside `engram web serve`. One daemon instance per user (not per repo). On Linux, it uses `inotify_add_watch`; on macOS, it uses `kqueue` / `FSEvents`. The daemon pid is written to `~/.engram/run/daemon.pid`.

---

#### 5.5.2 Message lifecycle implementation

State transitions are implemented as atomic filesystem moves between subdirectories under `~/.engram/inbox/<repo-id>/`. Atomicity is achieved via `os.rename()` on the same filesystem (POSIX atomic). Frontmatter is rewritten in place before the move; the graph.db row is updated after the move commits.

```python
def send(from_repo, to_repo, intent, severity, message, **kwargs):
    # 1. Dedup check (§5.5.3)
    dedup_key = compute_dedup_key(from_repo, to_repo, intent, **kwargs)
    existing = find_pending(to_repo, dedup_key)
    if existing:
        existing.duplicate_count += 1
        existing.body.append(f"\n\n<!-- duplicate received {now} -->\n{message}")
        save_atomic(existing)
        log_event('message_duplicated', existing.message_id, duplicate_count=existing.duplicate_count)
        return existing.message_id

    # 2. Rate limit check (§5.5.4)
    check_rate_limit(from_repo, to_repo)  # raises RateLimitError if exceeded

    # 3. Create message file
    msg_id = generate_message_id(from_repo)   # "<repo-id>:<YYYYMMDD-HHmmss>:<4-char-nonce>"
    filename = f"{utcnow_compact()}-from-{slug(from_repo)}-{slug(intent)}-{nonce4()}.md"
    msg_file = Path.home() / f".engram/inbox/{slug(to_repo)}/pending/{filename}"
    write_atomic(msg_file, render_frontmatter(msg_id, from_repo, to_repo, intent, severity, **kwargs) + "\n\n" + message)

    # 4. Update graph.db inbox_messages index
    insert_inbox_row(msg_id, from_repo, to_repo, intent, severity, 'pending',
                     deadline=kwargs.get('deadline'),
                     related_code_refs=kwargs.get('related_code_refs'),
                     dedup_key=dedup_key)

    # 5. Journal event (SPEC §10.7)
    log_event('message_sent', msg_id, from_repo=from_repo, to_repo=to_repo,
              intent=intent, severity=severity)

    return msg_id


def transition(msg_id, new_status, note=None, commit_sha=None, reason=None):
    msg = load_inbox_message(msg_id)          # reads file + frontmatter

    # Move file between state subdirectories (atomic rename)
    old_path = msg.path
    new_path = old_path.parent.parent / new_status / old_path.name
    new_path.parent.mkdir(parents=True, exist_ok=True)

    # Update frontmatter before move
    msg.status = new_status
    now = utcnow_iso()
    if new_status == 'acknowledged':
        msg.acknowledged_at = now
    elif new_status == 'resolved':
        msg.resolved_at = now
        if note:          msg.resolution_note   = note
        if commit_sha:    msg.resolution_commit = commit_sha
    elif new_status == 'rejected':
        msg.rejected_at = now
        if reason:        msg.rejection_reason  = reason
    overwrite_frontmatter(old_path, msg)      # rewrite in place before rename

    atomic_move(old_path, new_path)           # os.rename()

    # Update graph.db
    update_inbox_row(msg_id, new_status, resolved_at=msg.resolved_at,
                     resolution_note=note, commit_sha=commit_sha)

    # Journal event
    log_event(f'message_{new_status}', msg_id,
              resolution_note=note, commit_sha=commit_sha, rejection_reason=reason)
```

**Auto-archive** runs inside `engram review` and `engram daemon start`. Resolved messages older than 180 days and rejected messages older than 30 days are moved to `~/.engram/archive/inbox/<repo-id>/<state>/` via the same `transition()` path with `new_status='archived'`.

---

#### 5.5.3 Dedup implementation

```python
def compute_dedup_key(from_repo, to_repo, intent, related_code_refs=None, **kwargs):
    """
    Priority order (matches SPEC §10.5):
    1. Explicit dedup_key from caller — exact control over batching.
    2. Sorted hash of related_code_refs — merges all messages about the same
       code location regardless of body wording. Most common case: two sessions
       both discover the same bug while reading the same file.
    3. Body-prefix fallback — prevents pure duplicates when no code refs exist.
    """
    if kwargs.get('dedup_key'):
        raw = ('explicit', kwargs['dedup_key'])
        return ('explicit', sha256(f"{to_repo}:{intent}:{kwargs['dedup_key']}"))

    if related_code_refs:
        sorted_refs = sorted(related_code_refs)
        return ('coderef', sha256(f"{to_repo}:{intent}:{':'.join(sorted_refs)}"))

    # Fallback: first 200 chars of body + intent (SPEC §10.5 rule 3)
    body_prefix = kwargs.get('message', '')[:200]
    return ('body_prefix', sha256(f"{from_repo}:{intent}:{body_prefix}"))
```

`find_pending(to_repo, dedup_key)` scans the `inbox_messages` table with `WHERE to_repo=? AND status='pending' AND dedup_hash=?`; the `dedup_hash` column stores the second element of the tuple returned above. The table index on `(to_repo, status, dedup_hash)` makes this O(1).

**Merge semantics.** When a duplicate is detected, the new message body is appended to the existing file as a new paragraph (with `<!-- duplicate received <timestamp> -->` comment per SPEC §10.5). The `duplicate_count` frontmatter field is incremented. The existing `message_id` is returned to the caller. No new row is inserted into `inbox_messages`.

---

#### 5.5.4 Rate limiting

Token bucket enforced per `(from_repo, to_repo)` pair. Two independent limits apply simultaneously:

```python
RATE_LIMIT_DEFAULTS = {
    'pending_max':      20,   # max concurrent pending messages A → B
    '24h_window_max':   50,   # max total sends (including merged duplicates) A → B in any 24h UTC window
}

def check_rate_limit(from_repo, to_repo):
    """Raises RateLimitError with a user-readable message if either limit is exceeded."""
    pending = db.scalar(
        "SELECT COUNT(*) FROM inbox_messages WHERE from_repo=? AND to_repo=? AND status='pending'",
        from_repo, to_repo
    )
    if pending >= cfg('inbox.max_pending_per_sender', RATE_LIMIT_DEFAULTS['pending_max']):
        log_event('rate_limit_hit', from_repo=from_repo, to_repo=to_repo,
                  limit_type='pending_cap', current=pending)
        raise RateLimitError(
            f"Pending cap: {pending}/{RATE_LIMIT_DEFAULTS['pending_max']} messages from {from_repo} → {to_repo}.\n"
            f"Wait for recipient to process, or review with: engram inbox list --to={to_repo}"
        )

    window_start = utcnow() - timedelta(hours=24)
    sent_24h = db.scalar(
        "SELECT COUNT(*) FROM inter_repo_events WHERE from_repo=? AND to_repo=? AND ts >= ? "
        "AND event IN ('message_sent','message_duplicated')",
        from_repo, to_repo, window_start.isoformat()
    )
    if sent_24h >= cfg('inbox.max_per_sender_per_day', RATE_LIMIT_DEFAULTS['24h_window_max']):
        log_event('rate_limit_hit', from_repo=from_repo, to_repo=to_repo,
                  limit_type='daily_window', current=sent_24h)
        raise RateLimitError(
            f"Daily window: {sent_24h}/{RATE_LIMIT_DEFAULTS['24h_window_max']} messages sent in last 24h from {from_repo} → {to_repo}."
        )
```

Both limits are configurable per-user in `~/.engram/config.toml` under `[inbox]` (§4.4 config reference). The `rate_limit_hit` event is appended to `inter_repo.jsonl` regardless of which limit triggered, enabling operators to monitor for runaway agents.

---

#### 5.5.5 LLM session integration

At session start, `engram context pack` injects pending inbox messages into the packed prompt:

1. **Read phase.** Scan `~/.engram/inbox/<this_repo>/pending/` (sorted by severity desc, deadline asc, created asc — matching SPEC §10.3 priority order).
2. **Budget allocation.** Messages share a sub-budget capped at `min(20% of total context budget, config inbox.context_budget_pct)`. If more messages exist than fit the budget, they are truncated by the same priority order; a summary line is appended: `"[N more pending messages not shown — run 'engram inbox list' to view all]"`.
3. **Prompt injection.** Messages appear under a dedicated heading:

```markdown
## Pending Cross-Repo Messages

From `acme/service-a` (2026-04-18, bug-report, warning, deadline 2026-04-25):
> GET /api/users returns empty array instead of 404 for missing IDs
>
> **What:** When calling `GET /api/users?id=nonexistent-id`, the endpoint returns
> `200 OK` with an empty array...

→ To acknowledge: `engram inbox acknowledge acme/service-a:20260418-103000:7f3a`
→ To resolve after fix: `engram inbox resolve acme/service-a:20260418-103000:7f3a --note='...' --commit=<sha>`
→ To reject: `engram inbox reject acme/service-a:20260418-103000:7f3a --reason='...'`
```

4. **Mid-session actions.** The LLM may call `engram_inbox_acknowledge`, `engram_inbox_resolve`, or `engram_inbox_reject` at any point during the session via MCP tools (§5.5.6) or CLI.
5. **Session-end sweep.** `engram context pack --close` emits reverse-notification events for any messages that transitioned during the session, so the sender sees updates on their next `engram review`.

**Inbox in `engram status`.** `engram status` always shows a one-line summary: `Inbox: 2 pending (1 warning, 1 info)`. No messages are embedded in the status output; the full list is via `engram inbox list`.

---

#### 5.5.6 MCP tool surface

```python
@mcp.tool()
def engram_inbox_list(
    status: str = 'pending',
    to_repo: str | None = None,
    from_repo: str | None = None,
    intent: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    List inbox messages. Read-only. Returns structured dicts suitable for LLM consumption.
    Filters: status (pending/acknowledged/resolved/rejected/all), to_repo, from_repo, intent.
    Ordered by: severity desc, deadline asc, created asc.
    """

@mcp.tool()
def engram_inbox_send(
    to_repo: str,
    intent: str,
    severity: str = 'info',
    message: str = '',
    deadline: str | None = None,
    related_code_refs: list[str] | None = None,
    dedup_key: str | None = None,
    reply_to: str | None = None,
) -> str:
    """
    Send a cross-repo inbox message. Returns message_id.
    Enforces dedup (§5.5.3) and rate limit (§5.5.4).
    intent: bug-report | api-change | question | update-notify | task
    severity: info | warning | critical
    """

@mcp.tool()
def engram_inbox_acknowledge(message_id: str) -> None:
    """Transition pending → acknowledged. Records acknowledged_at timestamp."""

@mcp.tool()
def engram_inbox_resolve(
    message_id: str,
    note: str,
    commit_sha: str | None = None,
) -> None:
    """
    Transition → resolved. Records resolved_at, resolution_note, optional commit_sha.
    Emits message_resolved event to inter_repo.jsonl; sender sees it on next engram review.
    """

@mcp.tool()
def engram_inbox_reject(
    message_id: str,
    reason: str,
) -> None:
    """Transition → rejected. Records rejected_at and rejection_reason."""
```

All tools are registered in the MCP server startup sequence (§4 tool registration) and are available to any LLM session that has engram's MCP server active.

---

#### 5.5.7 Web UI data source

The Web UI `/inbox` page reads exclusively from `graph.db inbox_messages`. This is a denormalized view of the filesystem state, maintained synchronously by every `send()` / `transition()` call and asynchronously by the watcher daemon.

**Real-time updates.** The watcher daemon emits an SSE event on every inbox state change; the Web UI `/inbox` page subscribes and re-fetches the affected rows without a full page reload.

**Filtering and sort.** The UI supports filter by: status, intent, severity, from_repo, to_repo, deadline range. Default sort: severity desc → deadline asc → created asc (matches SPEC §10.3 priority order).

**graph.db schema:**

```sql
CREATE TABLE inbox_messages (
    message_id      TEXT PRIMARY KEY,
    from_repo       TEXT NOT NULL,
    to_repo         TEXT NOT NULL,
    intent          TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info',
    status          TEXT NOT NULL DEFAULT 'pending',
    created         TEXT NOT NULL,
    deadline        TEXT,
    dedup_hash      TEXT,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    acknowledged_at TEXT,
    resolved_at     TEXT,
    resolution_note TEXT,
    resolution_commit TEXT,
    rejected_at     TEXT,
    rejection_reason TEXT,
    file_path       TEXT NOT NULL
);

CREATE INDEX idx_inbox_to_status     ON inbox_messages(to_repo, status);
CREATE INDEX idx_inbox_from_status   ON inbox_messages(from_repo, status);
CREATE INDEX idx_inbox_dedup         ON inbox_messages(to_repo, status, dedup_hash);
```

---

### 5.6 Wisdom Metrics

#### 5.6.0 Role

Wisdom Metrics tracks four quantitative time-series curves that measure whether engram makes an LLM measurably smarter over time. This is engram's fifth pillar (per the README): not just "I store memories" but "I can prove I'm improving." Each curve is a time-series stored in `graph.db metrics_wisdom`; the Web UI visualizes them as sparklines on the dashboard and as full charts on the `/wisdom` page; the CLI exposes them via `engram wisdom report`.

The four curves are:

| Curve | What it measures | Health signal |
|---|---|---|
| **Workflow Mastery** | Per-workflow improvement across autolearn rounds | Monotone up = system learning; flat/low = workflow stuck |
| **Task Recurrence Efficiency** | Cost ratio for similar tasks over time | Trending <1.0 = faster recalls; >1.0 = regression |
| **Memory Curation Ratio** | Fraction of memories that are active vs. deprecated/archived | ~85–95% active is healthy; >20% deprecated = review backlog |
| **Context Efficiency** | Budget utilization × task success rate per session | Trending up = Relevance Gate improving; trending down = regression |

Wisdom Metrics makes the 5th pillar falsifiable: if the curves are not trending in the healthy direction, the system is not getting smarter and the operator should investigate.

---

#### 5.6.1 Four curves

**Curve 1: Workflow Mastery**

- **Definition.** For each workflow `W`, the value at autolearn round `r` is: `success_rate(W, r) × 0.5 + normalize(primary_metric_Δ(W, r)) × 0.5`. The two components are weighted equally so that a workflow can score well either by producing consistently passing runs or by showing measurable primary-metric improvement.
- **Data source.** `workflows/<name>/journal/evolution.tsv` (per-round rows) + `workflows/<name>/runs.jsonl` (per-run pass/fail).
- **Units.** 0–100 index; time axis = autolearn round number (not calendar time).
- **Health signals:**

  | Signal | Interpretation |
  |---|---|
  | Monotone up over 5+ rounds | System is learning this workflow. Normal and desirable. |
  | Flat with value < 50 | Workflow stuck. Likely: fixtures too strict, proposer budget too low, or workflow scope too broad. Investigate. |
  | Oscillating ±10+ points | Noisy fixtures or non-deterministic primary metric. Review fixture design. |
  | Single sharp drop | Potential regression from a bad accept. Check if the accepted rev introduced a scope change. |

**Curve 2: Task Recurrence Efficiency**

- **Definition.** For each pair of sessions `(s_new, s_old)` where the task texts have cosine similarity ≥ 0.85, compute `ratio = cost(s_new) / cost(s_old)` where `cost = tokens_used × session_duration_seconds`. Weekly bin = median ratio across all such pairs in that week.
- **Data source.** `~/.engram/journal/usage.jsonl` (token counts per session) + session metadata (task text, duration). Similarity computed with the same embedding model used by the Relevance Gate (§5.1).
- **Units.** Ratio (dimensionless); 1.0 = no change; < 1.0 = cheaper now (improvement); > 1.0 = more expensive (regression). Time axis = ISO week (Monday–Sunday UTC bins).
- **Minimum sample size.** A week's bin is only plotted if ≥ 5 recurring task pairs were found. Bins with fewer pairs show a hollow marker on the chart to indicate low confidence.
- **Health signals:**

  | Signal | Interpretation |
  |---|---|
  | Trending toward 0.8–0.9 over months | System retaining context; LLM doing less rework. Healthy. |
  | Flat at 1.0 | No recurrence benefit; either no recurring tasks or memory not being loaded. Check Relevance Gate scores. |
  | Ratio > 1.0 for 3+ consecutive weeks | Regression. Memory may have grown so large it degrades context quality. Run `engram wisdom report --curve=task_recurrence` for detail. |

**Curve 3: Memory Curation Ratio**

- **Definition.** `active_ratio = count(lifecycle_state='active') / count(*)` across all memory assets in `graph.db assets`. Complementary ratios: `deprecated_ratio`, `archived_ratio`. Plotted as a stacked area chart (active + deprecated + archived = 100%).
- **Data source.** `graph.db assets` table, `lifecycle_state` column. Snapshot taken at the end of each `aggregate_hourly()` run and stored as a weekly bin (ISO week boundary).
- **Units.** Percentage; time axis = calendar week.
- **Healthy target range:**

  | State | Healthy | Warning | Critical |
  |---|---|---|---|
  | active | 85–95% | 70–84% | < 70% |
  | deprecated | 3–10% | 11–20% | > 20% |
  | archived | 2–5% | 6–10% | > 10% |

- **Health signals:** deprecated > 20% means the review backlog has grown faster than operators resolve it — run `engram review` to process pending consistency proposals. Active < 70% may indicate over-aggressive Evolve scanning; check `[evolve].proposals_per_cadence_max`.

**Curve 4: Context Efficiency**

- **Definition.** For each session `s`, `efficiency(s) = (tokens_packed / context_budget) × task_success_indicator(s)`. `task_success_indicator` is 1.0 if the session ended with an explicit success event (`engram status --complete`), 0.5 if no explicit outcome, 0.0 if an error event was logged. Rolling 7-session average is the plotted value.
- **Data source.** `engram context pack` invocation logs (tokens packed, budget used) + session outcome events, both written to `~/.engram/journal/sessions.jsonl`.
- **Units.** Efficiency index 0–1; time axis = per-session index (rolling avg).
- **Health signals:**

  | Signal | Interpretation |
  |---|---|
  | Index trending toward 0.8–0.9 | Relevance Gate selecting well; budget mostly filled with relevant content that leads to success. |
  | Index low and flat (< 0.4) | Either budget too small (tokens_packed / budget is low) or too many sessions fail (success factor low). |
  | Index drops > 15% week-over-week | Regression. May indicate memory store has grown stale or Relevance Gate threshold drifted. |

---

#### 5.6.2 Data model

New tables in `graph.db`:

```sql
CREATE TABLE metrics_wisdom (
    curve            TEXT    NOT NULL,   -- workflow_mastery | task_recurrence | memory_curation | context_efficiency
    scope            TEXT,               -- optional: workflow name, repo path, etc. NULL = global
    bucket_start     TEXT    NOT NULL,   -- ISO 8601 bucket boundary (start of week, start of round, etc.)
    bucket_duration  TEXT    NOT NULL,   -- 'weekly' | 'per_round' | 'per_session'
    value            REAL    NOT NULL,
    sample_count     INTEGER,            -- number of data points in this bucket
    metadata         TEXT,               -- JSON blob for curve-specific fields (e.g., accepted_rounds, p50_ratio)
    PRIMARY KEY (curve, scope, bucket_start)
);

CREATE INDEX idx_metrics_curve_time  ON metrics_wisdom(curve, bucket_start DESC);
CREATE INDEX idx_metrics_scope       ON metrics_wisdom(curve, scope, bucket_start DESC);

-- Regression alerts generated by check_health_signal()
CREATE TABLE metrics_wisdom_alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    curve            TEXT    NOT NULL,
    scope            TEXT,
    detected_at      TEXT    NOT NULL,
    alert_class      TEXT    NOT NULL,   -- wisdom-regression-mastery | wisdom-regression-recurrence | etc.
    detail           TEXT    NOT NULL,   -- human-readable description of the regression
    proposal_id      TEXT,               -- FK → consistency_proposals.id (once emitted)
    resolved         INTEGER NOT NULL DEFAULT 0
);
```

**Aggregation pipeline.** Runs hourly by the daemon (configurable via `[wisdom].aggregate_interval`):

```python
def aggregate_hourly():
    # Each sub-aggregator is idempotent: re-running for the same bucket
    # updates the row (INSERT OR REPLACE) rather than creating duplicates.
    aggregate_workflow_mastery()     # scan all workflows' evolution.tsv + runs.jsonl
    aggregate_task_recurrence()      # scan usage.jsonl + cosine similarity comparison
    aggregate_memory_curation()      # COUNT assets by lifecycle_state
    aggregate_context_efficiency()   # scan sessions.jsonl for pack invocations + outcomes

    # Regression detection (§5.6.5) — runs after aggregation
    for curve in ('workflow_mastery', 'task_recurrence', 'memory_curation', 'context_efficiency'):
        for scope in get_active_scopes(curve):
            check_health_signal(curve, scope)
```

`aggregate_workflow_mastery()` iterates every `~/.engram/workflows/*/journal/evolution.tsv`, computes the per-round index, and writes rows with `scope=<workflow-name>` and `bucket_duration='per_round'`. `aggregate_memory_curation()` runs a single `SELECT lifecycle_state, COUNT(*) FROM assets GROUP BY lifecycle_state` and writes a single `scope=NULL` row.

---

#### 5.6.3 CLI `engram wisdom report`

```
$ engram wisdom report --since=30d

Workflow Mastery (30-day, by autolearn round)
  release-checklist       ▁▂▃▅▆▇██  index 72 → 94  (+22 since 2026-03-18)
  pr-review               ▅▅▆▅▆▇▇▇  index 51 → 59  (+8)
  dep-upgrade             ▂▃▅▄▅▆▇▇  index 31 → 72  (+41)

Task Recurrence Efficiency (weekly, last 8 weeks)
  Ratio (median):   1.00 → 0.82  (cost 18% lower for similar tasks)
  Sample/week:      47 → 134 recurring task pairs

Memory Curation Ratio (current snapshot)
  Active:      487  (89.7%)  ██████████████████░░
  Deprecated:   38  (7.0%)   ████░░░░░░░░░░░░░░░░
  Archived:     18  (3.3%)   ██░░░░░░░░░░░░░░░░░░
  [All ratios within healthy range]

Context Efficiency (rolling 7-session avg, last 30d)
  Index:    0.71 → 0.84  (+0.13)
  Trend:    ▂▃▄▅▅▆▇▇  (improving)

✓ All 4 curves trending positive. No regressions detected.
```

**Flags:**

| Flag | Description |
|---|---|
| `--since=<duration>` | Time window: `7d`, `30d`, `90d`, `1y` (default `30d`) |
| `--curve=<name>` | Show only one curve: `workflow_mastery`, `task_recurrence`, `memory_curation`, `context_efficiency` |
| `--scope=<name>` | Filter to a specific workflow or repo path |
| `--json` | Emit JSON output (structured, LLM-consumable via MCP) |
| `--web-url` | Print URL to the `/wisdom` Web UI page instead of terminal output |

Exit code is 0 when all curves are healthy, 1 when any regression alert is active.

---

#### 5.6.4 Web UI integration

The `/wisdom` page is the primary visualization surface:

- **Four charts** (one per curve), each with a time-range selector: `7d` / `30d` / `90d` / `1y`. Charts render as line graphs with the healthy range shaded in green.
- **Workflow Mastery drill-down.** Clicking a workflow name in the Mastery chart opens a per-workflow panel showing each autolearn round: rev tag, primary metric value, accepted/rejected, proposer token count. This is the evolution.tsv data rendered visually.
- **Task Recurrence scatter.** Hovering a week's bin shows sample size and the p25/p50/p75 distribution of the ratio, so operators can distinguish noise from signal.
- **Regression banner.** When any curve shows an active regression alert (`metrics_wisdom_alerts.resolved = 0`), a red banner appears at the top of every page (not just `/wisdom`): `"Wisdom regression detected: context_efficiency dropped 17% this week — run engram wisdom report"`.
- **Export.** Each chart has a "Download CSV" button that returns the raw `metrics_wisdom` rows for that curve as a CSV file.
- **Real-time updates.** The `/wisdom` page subscribes to the SSE stream. When `aggregate_hourly()` writes new rows, an `metrics_updated` SSE event is emitted and the charts re-render without a full page reload.

---

#### 5.6.5 Regression detection

Automated health checks run at the end of every `aggregate_hourly()` call. Each check compares the most recent complete bucket against the prior bucket (or a rolling baseline). When a threshold is breached:

1. A row is inserted into `metrics_wisdom_alerts`.
2. A consistency proposal of the matching `wisdom-regression-*` class is emitted to `consistency.jsonl`.
3. The proposal appears in `engram review` alongside memory and consistency proposals.

**Regression thresholds:**

| Curve | Trigger condition | Alert class |
|---|---|---|
| Workflow Mastery | Any workflow's index drops > 10 points week-over-week | `wisdom-regression-mastery` |
| Task Recurrence Efficiency | Median ratio exceeds 1.0 for 3 or more consecutive weeks | `wisdom-regression-recurrence` |
| Memory Curation Ratio | `deprecated_ratio` exceeds 20% | `wisdom-regression-curation` |
| Context Efficiency | Rolling 7-session index drops > 15% relative to prior 7-session window | `wisdom-regression-context` |

**Resolution.** Regression proposals accept the same six resolution actions as Consistency Engine proposals (§5.2.5): `update`, `supersede`, `merge`, `archive`, `dismiss`, `escalate`. The most common resolution is `dismiss` after the operator has investigated and confirmed the regression is understood (e.g., a temporarily empty workflow fixture set), or `update` to record a corrective action taken. Like all proposals, regression alerts are **never** auto-resolved — they require explicit operator acknowledgment.

**Alert deduplication.** If the same curve + scope combination already has an open (unresolved) alert, no new alert is inserted for the same regression. New alerts are only emitted when a curve that was previously healthy enters regression territory again.

---

#### 5.6.6 MCP tool and Python SDK

```python
@mcp.tool()
def engram_wisdom_report(
    since: str = '30d',
    curve: str | None = None,
    scope: str | None = None,
) -> dict:
    """
    Return wisdom metrics as structured data. LLM-consumable.
    Returns: { curves: { <name>: { buckets: [...], health: 'ok'|'warning'|'regression', alerts: [...] } } }
    """
```

**Python SDK:**

```python
from engram import wisdom

# Full report
report = wisdom.report(since='30d')
print(report.to_sparklines())         # terminal sparkline rendering (same as CLI)
print(report.to_dict())               # structured dict for programmatic use

# Single curve
mastery = wisdom.report(since='90d', curve='workflow_mastery', scope='release-checklist')
print(mastery.health)                 # 'ok' | 'warning' | 'regression'
for bucket in mastery.buckets:
    print(bucket.round_tag, bucket.value, bucket.accepted)

# Check for active regressions
alerts = wisdom.active_alerts()
for a in alerts:
    print(a.curve, a.alert_class, a.detected_at, a.detail)
```

---

---

## 6. Layer 4 — Access Layer

### 6.0 Overview

Layer 4 is how LLMs and agents actually talk to the store. Four access paths coexist; the user or tool picks whichever fits the runtime context. All four read the same `.memory/` directory and write through the same Layer 2 CLI primitives. They differ in transport only.

#### 6.0.1 Access path table

| LLM / agent type | Best access path | Why |
|---|---|---|
| Claude Code / Codex / Gemini CLI / Cursor | Adapter (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.cursor/rules`) | Tool-native config file auto-loaded at startup; zero configuration overhead |
| Claude Desktop / Zed / any MCP client | MCP server | Native MCP protocol, typed tool schemas, real-time reads |
| Ollama / llama.cpp / any local small model | Prompt pack | One-shot system prompt injection; works offline; no server process required |
| Custom Python agent | Python SDK | In-process library, fine-grained control, no subprocess overhead |
| Custom TypeScript / Node agent | TypeScript SDK | `@engram/sdk` npm package; same API shape as the Python SDK |
| Anything else — scripts, ad-hoc tools, CI pipelines | CLI + shell glue | `engram context pack` pipes to any stdin-consuming tool |

**Shared state.** All four paths read the same `.memory/` directory and write via `engram memory add`, `engram workflow run`, `engram inbox send`, and related CLI primitives. Concurrent writes are serialized via file locks (§3.8). No path has privileged access to the store that another path lacks.

**Dependency on Layer 3.** When the Relevance Gate is enabled, `engram context pack` and the MCP `engram_context_pack` tool both route through it for candidate ranking. When the Relevance Gate is disabled, both fall back to deterministic scope/enforcement ordering. The access paths never directly invoke the Consistency Engine, Autolearn Engine, or Evolve Engine; those are triggered separately via `engram consistency scan`, `engram workflow autolearn`, and `engram memory evolve`.

---

### 6.1 Adapters

An adapter is a single-file prompt template generated at `engram init` time or on demand via `engram adapter <tool>`. It points the LLM tool at `.memory/` and provides the minimal behavioral contract: load memory on startup, follow METHODOLOGY.md, report at session end.

#### 6.1.1 Five adapter files

| Tool | File path | Notes |
|---|---|---|
| Claude Code | `CLAUDE.md` | Auto-loaded by Claude Code on every session start |
| Codex | `AGENTS.md` | OpenAI Codex standard config file |
| Gemini CLI | `GEMINI.md` | Google Gemini CLI standard config file |
| Cursor | `.cursor/rules` | Cursor IDE rules directory |
| Raw API / custom | `system_prompt.txt` | Plain text; paste or inject programmatically |

All five are generated from versioned templates in `adapters/<tool>/template.md` (shipped with `engram-cli`). The template is rendered with the project's `.memory/` path, the user's scope configuration, and the current SPEC version.

#### 6.1.2 Marker-bounded structure

Every adapter file uses a marker-bounded layout so that `engram adapter --regenerate` can update the managed zone without clobbering user customizations:

```markdown
<!-- engram:begin v0.2 -->
<!-- This section is managed by `engram adapter`. Edits here will be overwritten on regenerate. -->

## engram memory — session contract

**Read `.memory/MEMORY.md` on startup. Follow `METHODOLOGY.md`.**

Memory location: `.memory/`
Specification: `SPEC.md`
Glossary: `docs/glossary.md`
Methodology: `METHODOLOGY.md`

### Session start
Run `engram context pack --task="<current task>" --budget=6000` and add the output to your context.

### Session end
Run `engram context pack --close` to record the session outcome and trigger the Wisdom Metrics update.

### Budget hint
Keep L1 wake-up (mandatory + default memories, no project context) to ≤900 tokens.

<!-- engram:end v0.2 -->

# User customizations below this line are preserved across regenerations.
```

The user-editable zone (everything after `<!-- engram:end v0.2 -->`) is extracted before regeneration and re-appended unchanged. If the `engram:begin` / `engram:end` markers are not found in the existing file, `engram adapter --regenerate` emits an error and exits without writing; it never silently overwrites an unrecognized file.

#### 6.1.3 Managed zone contents

The engram-managed section always includes:

1. **Mission line.** "Read `.memory/MEMORY.md` on startup. Follow METHODOLOGY.md."
2. **File locations.** Relative paths to `.memory/`, `SPEC.md`, `docs/glossary.md`, `METHODOLOGY.md`.
3. **Lifecycle hooks.** Session start: `engram context pack`; session end: `engram context pack --close`.
4. **Per-tool hook references.** For Claude Code: references to `adapters/claude-code/hooks/` (PreCompact and Stop hooks). For other tools: equivalent hook file locations where they exist.
5. **Budget hint.** Token ceiling for the L1 wake-up prompt (default 900 tokens; configurable in `.memory/config.toml` under `[access.adapter]`).

#### 6.1.4 Regeneration algorithm

```python
def regenerate_adapter(tool: str, project_root: Path) -> None:
    adapter_path = adapter_file(tool, project_root)
    current = read_adapter_file(adapter_path)          # may be empty if first run
    user_section = extract_user_section(current)       # text after engram:end marker
    new_managed = render_managed_template(tool, project_root)  # engram:begin..engram:end block
    if current and BEGIN_MARKER not in current:
        raise AdapterMarkerNotFound(
            f"{adapter_path}: engram:begin marker missing. "
            "Rename or delete the file before regenerating."
        )
    write_atomic(adapter_path, new_managed + '\n' + user_section)
```

`write_atomic` writes to a `.tmp` file and renames into place, preventing partial writes from leaving the adapter in an inconsistent state.

#### 6.1.5 Invocation

```bash
# Generate all adapters for this project (runs at engram init)
engram adapter --all

# Generate or regenerate a specific adapter
engram adapter claude-code
engram adapter claude-code --regenerate

# List available adapter types
engram adapter --list

# Show diff before regenerating
engram adapter claude-code --dry-run
```

---

### 6.2 MCP Server

The MCP server exposes the full engram store as a set of typed tools consumable by any MCP-compatible client: Claude Desktop, Zed, the Claude API with tool use, or any custom client that speaks the MCP protocol.

Launched via `engram mcp serve [--transport=stdio|sse] [--port=N]`.

#### 6.2.1 Design principles

**Stateless per request.** Every tool call re-reads from the filesystem (with `graph.db` as an index cache for performance). Two concurrent sessions reading the same memory directory MUST yield identical results for read tools. There is no in-memory session state.

**Performance budget.** Each tool call MUST complete in under 300ms at p95 (§20 glossary). Cold MCP server start MUST complete in under 500ms. These budgets assume local filesystem; network-mounted filesystems are out of scope.

**Audit trail.** Every tool call — read and write — appends a structured event to `~/.engram/journal/<date>.jsonl`. The event includes the tool name, input parameters (with secrets redacted), timestamp, duration, and outcome.

**Write serialization.** Write tools acquire file locks (§3.8) before modifying assets. Concurrent write calls from separate MCP sessions serialize correctly; they do not deadlock.

#### 6.2.2 Read tools

```python
@mcp.tool()
def engram_search(
    query: str,
    scope: str = 'visible',   # 'visible' | 'project' | 'user' | 'team' | 'org' | 'pool:<name>'
    top_k: int = 10,
) -> list[dict]:
    """Semantic + BM25 hybrid search over all assets in scope. Returns ranked asset summaries."""

@mcp.tool()
def engram_read(asset_id: str) -> dict:
    """Return full content and frontmatter of a single asset by its asset_id."""

@mcp.tool()
def engram_list(
    scope: str | None = None,
    subtype: str | None = None,   # 'user' | 'feedback' | 'project' | 'reference' | 'workflow_ptr' | 'agent'
) -> list[dict]:
    """Return asset inventory, optionally filtered by scope and subtype."""

@mcp.tool()
def engram_context_pack(
    task: str,
    budget_tokens: int = 6000,
) -> str:
    """Assemble and return a packed system prompt for the given task within the token budget."""

@mcp.tool()
def engram_wisdom_report(
    since: str = '30d',
    curve: str | None = None,
) -> dict:
    """Return Wisdom Metrics as structured data. See §5.6 for curve names and schema."""
```

#### 6.2.3 Write tools — asset

```python
@mcp.tool()
def engram_memory_add(
    subtype: str,                 # 'user' | 'feedback' | 'project' | 'reference' | 'agent'
    scope: str,                   # 'user' | 'project' | 'team' | 'org' | 'pool:<name>'
    body: str,
    frontmatter_extras: dict = {},
) -> dict:
    """Create a new Memory asset. Returns the new asset_id and file path."""

@mcp.tool()
def engram_memory_update(
    asset_id: str,
    **fields,
) -> dict:
    """Edit an existing Memory asset. Immutable fields (asset_id, created_at) are rejected."""

@mcp.tool()
def engram_memory_validate_use(
    asset_id: str,
    outcome: str,   # 'helpful' | 'neutral' | 'harmful'
) -> dict:
    """Record a confidence signal for a memory. Feeds the Wisdom Metrics curation curve."""
```

#### 6.2.4 Write tools — workflow and KB

```python
@mcp.tool()
def engram_workflow_run(
    name: str,
    inputs: dict = {},
) -> dict:
    """Invoke the named workflow spine. Returns structured outcome including exit code and output."""

@mcp.tool()
def engram_kb_read(
    topic: str,
    chapter: str | None = None,
) -> str:
    """Return the content of a KB article (compiled digest). Specify chapter for sub-sections."""
```

#### 6.2.5 Inbox tools

```python
@mcp.tool()
def engram_inbox_list(
    status: str = 'pending',     # 'pending' | 'acknowledged' | 'resolved' | 'all'
    to_repo: str | None = None,
) -> list[dict]:
    """List inbox messages for this repo, filtered by status and optionally by target repo."""

@mcp.tool()
def engram_inbox_send(
    to_repo: str,
    intent: str,       # 'bug-report' | 'api-change' | 'dependency-update' | 'question' | 'info'
    severity: str,     # 'info' | 'warning' | 'critical'
    message: str,
    **kwargs,          # optional: related_code_refs, related_asset_ids, expires_at
) -> dict:
    """Send a point-to-point message to another repo's inbox. Returns message_id."""

@mcp.tool()
def engram_inbox_acknowledge(message_id: str) -> dict:
    """Mark a message as acknowledged (read but not yet resolved)."""

@mcp.tool()
def engram_inbox_resolve(
    message_id: str,
    note: str,
    commit_sha: str | None = None,
) -> dict:
    """Mark a message as resolved with a resolution note and optional commit reference."""
```

#### 6.2.6 Consistency tools (read-only for LLMs)

```python
@mcp.tool()
def engram_review() -> dict:
    """Return aggregate open items: consistency proposals, inbox pending, regression alerts."""

@mcp.tool()
def engram_consistency_list(status: str = 'open') -> list[dict]:
    """List Consistency Engine proposals by status: 'open' | 'resolved' | 'dismissed' | 'all'."""
```

These tools expose consistency information to LLMs for reporting purposes. Resolving proposals (accepting, dismissing, escalating) is done through the CLI (`engram consistency resolve <id>`) to keep the human in the decision loop, consistent with the §2.3 invariant that the Consistency Engine proposes and never auto-mutates.

---

### 6.3 Prompt Pack

`engram context pack` produces a single-file text prompt. This is the access path for any tool that cannot run a subprocess or connect to an MCP server.

#### 6.3.1 Use cases

- Ollama / llama.cpp / any model that reads a system prompt string.
- Offline or air-gapped environments where no network connection is available.
- Small-context models (4k–8k tokens) where every token counts.
- Quick experiments, debugging, and CI pipelines that inspect what context would be loaded.

#### 6.3.2 Command form

```bash
engram context pack \
  --task="fix checkout flow smoke test" \
  --budget=4000 \
  [--model=qwen2.5-7b] \
  [--output=prompt.txt] \
  [--format=markdown|json|plain]
```

`--model` is a hint for budget partitioning (larger models get richer workflow snippets). `--format=json` emits structured data for programmatic consumption. `--output` writes to a file; omitting it prints to stdout.

#### 6.3.3 Output structure

Sections are emitted in priority order and budget-filtered via the Relevance Gate (§5.1). Each included asset is tagged with its estimated token count. The final line shows total tokens used.

```markdown
# engram context (v0.2)

## Who you are talking to
<user-scope memories, top-K by relevance × scope-weight>

## Rules you must follow
<mandatory memories first, then default-enforcement memories>

## Current project state
<project-scope memories ranked by relevance to task>

## Relevant workflows
<workflow_ptr entries with brief description; full workflow available at .memory/workflows/<name>/>

## Knowledge base references
<_compiled.md snippets from relevant KB articles>

## Pending cross-repo messages
<pending inbox items addressed to this repo>

## Task
fix checkout flow smoke test

---
# Total: 3847 / 4000 tokens
```

**Budget enforcement.** If all mandatory memories alone exceed the budget, the prompt pack emits them in full with a `# WARNING: mandatory memories exceed budget` header. Default and hint memories are then omitted. The LLM receives a valid, if dense, prompt.

**Section ordering rationale.** Mandatory rules load before project context because mandatory memories represent authoritative constraints that must not be silently absent. Project state follows because it is task-relevant but not authoritative. Workflows and KB entries follow because they are reference material with lower recall cost.

#### 6.3.4 Pipe usage

```bash
# Pipe to Ollama
cat <(engram context pack --task="add OAuth2 support to auth service") my-task.md \
  | ollama run qwen2.5:7b

# Write to file for repeated use
engram context pack --task="add OAuth2 support to auth service" --output=.context.md

# JSON output for scripting
engram context pack --task="..." --format=json | jq '.sections[].token_count'
```

---

### 6.4 Python SDK

`pip install engram` → `import engram`.

The Python SDK is an in-process library that wraps either the MCP server protocol (for remote scenarios) or direct filesystem access (for local projects). It exposes the same surface as the MCP tools in a Pythonic form.

#### 6.4.1 Context and session API

```python
from engram import Context, memory, workflow, inbox, consistency, wisdom

# Context inherits ~/.engram config + project cwd auto-detection
ctx = Context()

# Explicit project path and scope override
ctx = Context(project_root='/home/user/myproject', scope='team')
```

#### 6.4.2 Read operations

```python
# Semantic + BM25 search
memories = ctx.memory.search('payment gateway', top_k=10)
for m in memories:
    print(m.asset_id, m.name, m.score)

# Full asset read
asset = ctx.memory.read('mem-20260418-abc123')

# Asset inventory
all_memories = ctx.memory.list(scope='project', subtype='feedback')

# KB article
article = ctx.kb.read('platform-arch')
chapter = ctx.kb.read('platform-arch', chapter='data-model')

# Packed context prompt
system_prompt = ctx.context_pack(task='fix login bug', budget_tokens=4000)
```

#### 6.4.3 Write operations

```python
# Create a memory
new_id = ctx.memory.add(
    subtype='feedback',
    scope='project',
    name='rebase before merge',
    body='Always rebase feature branches onto main before opening a PR.',
    enforcement='default',
)

# Edit a memory
ctx.memory.update(new_id, body='Always rebase onto main; squash fixup commits.')

# Record a usage outcome
ctx.memory.validate_use(new_id, outcome='helpful')
```

#### 6.4.4 Workflow and inbox

```python
# Invoke a workflow
result = ctx.workflow.run('release-checklist', inputs={'version': '1.2.0'})
print(result.exit_code, result.output)

# Send a cross-repo message
msg_id = ctx.inbox.send(
    to_repo='acme/service-b',
    intent='bug-report',
    severity='warning',
    message='The /users endpoint returns 500 when email contains a plus sign.',
    related_code_refs=['src/api/users.py:L42@abc123'],
)

# List and resolve inbox items
for msg in ctx.inbox.list(status='pending'):
    print(msg.message_id, msg.intent, msg.severity, msg.message)

ctx.inbox.resolve(msg_id, note='Fixed in commit abc456.', commit_sha='abc456')
```

#### 6.4.5 Consistency and wisdom

```python
# Review open items
review = ctx.review()
print(f"{len(review.proposals)} open proposals, {len(review.inbox_pending)} pending messages")

# List consistency proposals
for proposal in ctx.consistency.list_open():
    print(proposal.proposal_id, proposal.conflict_class, proposal.summary)

# Wisdom metrics
report = ctx.wisdom.report(since='30d')
print(report.to_sparklines())
```

#### 6.4.6 Error taxonomy

`engram.errors` defines a flat error hierarchy that maps 1:1 to CLI exit codes:

| Exception class | CLI exit code | When raised |
|---|---|---|
| `engram.errors.ValidationError` | 2 | Asset frontmatter fails SPEC validation |
| `engram.errors.ScopeError` | 3 | Operation targets a scope the caller cannot write |
| `engram.errors.NotFound` | 4 | Asset ID or workflow name does not exist |
| `engram.errors.RateLimitError` | 5 | MCP server rate limit exceeded (remote mode) |
| `engram.errors.LockTimeout` | 6 | File lock not acquired within timeout |

All SDK methods raise from this hierarchy. Callers catch `engram.errors.EngramError` to handle all engram exceptions in one clause.

---

### 6.5 TypeScript SDK

`npm install @engram/sdk`. The TypeScript SDK is the mirror of the Python SDK, designed for Node.js agents, browser-based tools, and Deno/Bun runtimes.

#### 6.5.1 API surface

```typescript
import { Context } from '@engram/sdk';

const ctx = new Context();
// or with explicit options:
const ctx = new Context({ projectRoot: '/home/user/myproject', scope: 'team' });

// Search
const memories = await ctx.memory.search('payment gateway', { topK: 10 });
for (const m of memories) {
  console.log(m.assetId, m.name, m.score);
}

// Pack context
const systemPrompt = await ctx.contextPack({
  task: 'add OAuth2 support to auth service',
  budgetTokens: 4000,
});

// Run a workflow
const result = await ctx.workflow.run('release-checklist', { version: '1.2.0' });

// Inbox
const msgId = await ctx.inbox.send({
  toRepo: 'acme/service-b',
  intent: 'bug-report',
  severity: 'warning',
  message: 'The /users endpoint returns 500 when email contains a plus sign.',
  relatedCodeRefs: ['src/api/users.py:L42@abc123'],
});

// Consistency
const openProposals = await ctx.consistency.listOpen();
```

#### 6.5.2 Runtime support

| Runtime | Status | Notes |
|---|---|---|
| Node.js ≥18 | Supported | Full filesystem access; recommended for CLI agents |
| Bun | Supported | Native filesystem I/O; faster cold start |
| Deno | Supported | Requires `--allow-read --allow-write --allow-run` |
| Browser | Local-only mode via WASM | Read-only; no subprocess; prompt pack only |

The browser WASM bundle bundles the prompt templates and JSON schemas so that `ctx.contextPack()` works without a running `engram mcp serve` process.

#### 6.5.3 Publishing

Published to npm as `@engram/sdk`. TypeScript type definitions are bundled. The package ships with the prompt templates (`adapters/*/template.md`) and the JSON schemas for all MCP tool inputs so that callers can validate inputs before sending.

---

### 6.6 Cross-path coexistence

The same project can have all four access paths active simultaneously without conflict.

#### 6.6.1 Concurrent example

```
Claude Code session:   reads CLAUDE.md (adapter) → loads context via `engram context pack`
Codex session:         reads AGENTS.md (adapter) → same context pack
Claude Desktop:        connects to `engram mcp serve` (MCP server) → real-time tool calls
Ollama qwen2.5:7b:    receives piped output of `engram context pack` (prompt pack)
```

All four are simultaneously reading `.memory/`. All four issue writes via the CLI primitives (`engram memory add`, `engram workflow run`, `engram inbox send`). File locks (§3.8) serialize the writes; no session sees a partially written asset.

#### 6.6.2 Recommended configuration

| Scenario | Primary path | Fallback |
|---|---|---|
| Developer IDE (Claude Code / Cursor / Zed) | Adapter or MCP | Prompt pack for offline |
| Local automation (Python scripts, CI) | Python SDK | CLI + shell glue |
| TypeScript / Node agents | TypeScript SDK | CLI via `child_process` |
| Air-gapped / offline | Prompt pack | — |
| Multiple tools simultaneously | MCP server as hub | Adapters for each IDE tool |

#### 6.6.3 Write consistency guarantee

Regardless of which path initiates a write, the following hold:

1. Every write goes through `engram-cli` primitives (or through the MCP server, which delegates to the same primitives). No path writes raw files directly to `.memory/` without frontmatter validation.
2. File locks prevent concurrent writes from interleaving partial content.
3. Every write appends an audit event to `~/.engram/journal/<date>.jsonl`.
4. The Consistency Engine, when enabled, sees all writes regardless of which path produced them — because it reads from Layer 1, not from any path-specific log.

---

## 7. Layer 5 — Observation Layer (Web UI)

### 7.0 Role + Technology Choices

The Observation Layer is the human-facing face of engram. Its purpose is to let humans see the engram store as humans need to see it — not as an LLM sees it. An LLM receives a packed prompt; a human needs spatial overview, drill-down, time series, and interactive control. The web UI provides all of that across 10 pages covering dashboard, graph, asset detail (memory, workflow, KB), pool management, inbox, project overview, context preview, wisdom curves, and the autolearn console.

**Not required to use engram.** The CLI alone (Layers 1–4) is fully functional and SPEC-compliant. The web UI is an optional extra that adds observability and operator tooling. A deployment with only the CLI is not degraded; it simply lacks the graphical views.

**Tech stack:**

| Layer | Tech | Alternatives considered | Reason for choice |
|-------|------|------------------------|-------------------|
| Backend | Python + FastAPI | Node + Express | Same Python runtime as CLI; async I/O; OpenAPI auto-gen |
| Frontend | Svelte + SvelteKit | React / Vue | Small bundle, no virtual DOM overhead, compile-time reactivity |
| Charts | D3 + Observable Plot | Chart.js / Recharts | Customizable force layout for graph; lightweight |
| Diagrams | Mermaid | D2 / PlantUML | Markdown-native; workflow state diagrams |
| Editor | CodeMirror 6 | Monaco | Lighter; markdown-first |
| Realtime | SSE (Server-Sent Events) | WebSockets | One-way push; cheaper; no handshake complexity |
| Auth | Basic auth + localhost bind | OAuth / JWT | Default bind 127.0.0.1; no network exposure without explicit config |

**Startup:** `engram web serve [--port=8787] [--bind=127.0.0.1] [--auth=<user:pass>]`. Opens `engram web open` in the default browser.

---

### 7.1 10-Page Map

Each page entry covers: purpose, primary data source (graph.db tables or files), key interactions, and realtime triggers.

#### /dashboard

- **Purpose:** Project-level overview — the first page an operator opens.
- **Data:** asset counts by type/scope/lifecycle; recent inbox messages; open consistency proposals; wisdom sparklines (last 30 days, all four curves).
- **Interactions:** click any count → filtered `/graph`; click inbox item → `/inbox/<msg-id>`; click proposal → consistency review modal; click sparkline → `/wisdom`.
- **Realtime:** SSE on `asset_changed`, `proposal_created`, `inbox_message` events — counters and sparklines update without reload.

#### /graph

- **Purpose:** Visual asset graph — assets as nodes, references as directed edges.
- **Data:** `graph.db` tables `assets` and `references_`; scope + subtype filters drive SQL WHERE clauses.
- **Interactions:** pan/zoom (mouse wheel + drag); click node → slide-out detail panel; right-click node → navigate to `/memory/<id>` or `/workflow/<name>`; filter sidebar (scope, subtype, lifecycle); search box highlights matching nodes.
- **Realtime:** SSE on `asset_changed` — adds or updates node/edge in the live graph without re-layout.
- **Tech note:** D3 force layout for ≤ 1000 nodes; WebGL (regl) for > 1000 nodes with SVG fallback if WebGL unavailable.

#### /memory/\<id\>

- **Purpose:** View and edit a single memory asset.
- **Data:** the `.memory/<scope>/<file>.md` on disk (loaded via `engram memory read <id>`); inbound references from `graph.db`.
- **Interactions:** frontmatter editor (structured form for id, subtype, scope, lifecycle, tags, confidence); body editor (CodeMirror 6, markdown mode); Save button → triggers `engram memory update`; Archive button → triggers `engram memory archive`; Delete button (soft — moves to archive).
- **Realtime:** SSE on `asset_changed` for this asset-id — if a CLI edit happens concurrently, the page shows a "file changed externally — reload?" banner.
- **"Used in" side panel:** inbound references listed by source asset-id; recent LLM usage events from `journal/*.jsonl` (last 10 context-pack events that included this asset).

#### /workflow/\<name\>

- **Purpose:** Workflow asset viewer and autolearn control panel.
- **Data:** `workflow.md`; `spine.md` or `spine.yaml`; fixture files; `metrics.yaml`; `evolution.tsv`; `rev/` directory.
- **Interactions:** tabs — Overview / Spine / Fixtures / Metrics / Revisions; Autolearn section with Start / Stop / Continue buttons; per-revision row in Revisions tab shows diff viewer (unified diff of spine changes) plus Accept / Reject icons; metrics chart (Observable Plot line chart of `confidence` and `pass_rate` over rounds).
- **Realtime:** SSE on `autolearn_round` event — Revisions tab appends new row; metrics chart extends right.
- **Revision graph:** horizontal timeline `r0 → r1 → r2 → … → rN` with accept/reject/current icons.

#### /kb/\<topic\>

- **Purpose:** KB article reader and editor.
- **Data:** `README.md` (article root); individual chapter files; `_compiled.md` (generated output); static assets.
- **Interactions:** TOC sidebar (auto-generated from chapter headings); click chapter → loads chapter in main pane; Edit mode toggle → CodeMirror editor for that chapter; Compile button → calls `engram kb compile <topic>` and refreshes `_compiled.md` pane; side-by-side view (source chapters left, compiled output right).
- **Realtime:** SSE on `asset_changed` for any file under `kb/<topic>/` → "Digest is stale — recompile?" banner appears.

#### /inbox

- **Purpose:** Cross-repo message center.
- **Data:** `graph.db` `inbox_messages` table; `~/.engram/inbox/<repo-id>/` files.
- **Interactions:** filter bar (status, intent, severity, to_repo, from_repo); per-message actions — Acknowledge / Resolve / Reject buttons (each calls the corresponding `engram inbox` command); Send New Message form (to_repo, intent, severity, subject, body); thread view (reply_to chains rendered as indented conversation).
- **Realtime:** SSE on `inbox_message` event — new message rows appear without reload; status badge updates on acknowledge/resolve.
- **Visualization:** message threads use `reply_to` linkage; thread collapsed by default if > 3 messages.

#### /pools

- **Purpose:** Pool subscription manager.
- **Data:** `graph.db` `subscriptions`; `~/.engram/pools/*/`; pool remote metadata.
- **Interactions:** subscribe/unsubscribe toggle per pool; propagation mode dropdown (`auto-sync` / `notify` / `pinned`); revision pinner (select from `rev/` list when mode = `pinned`); diff viewer (between current local copy and latest pool revision); Sync Now button.
- **Realtime:** SSE on `pool_updated` event — "New revision available" badge appears on the relevant pool row.
- **Visualization:** pool dependency graph — which pools depend on which (for org → team → project propagation chains).

#### /projects

- **Purpose:** Multi-project overview — for users managing multiple engram-enabled projects on one machine.
- **Data:** `~/.engram/projects.toml`; per-project `graph.db` summary stats.
- **Interactions:** grid of project cards with summary stats (asset count, open proposals, inbox unread, last wisdom sample); Switch Active Project button; Bulk Sync All Pools button; Open in Terminal button (opens a terminal in the project root).
- **Realtime:** per-project sparkline updates via SSE (one event stream multiplexed across all projects).

#### /context-preview (THE critical debug page)

- **Purpose:** Simulate exactly what the LLM would see given a task description, before any LLM is invoked. The most important diagnostic page in the web UI.
- **Data:** `graph.db` + cache + live Relevance Gate invocation (calls `engram context pack --dry-run`).
- **Interactions:** task input field (multiline); token budget slider (default 4000, range 500–32000); model selector (affects budget heuristics — different models have different effective context windows); scope filter (project / team / org / user / pool); Run button → triggers live pack simulation.
- **Output pane:** ranked candidate list with columns — rank, asset-id, subtype, scope, score, inclusion reason (why Relevance Gate selected it), token count, cumulative tokens; inclusion/exclusion boundary clearly marked.
- **Realtime:** per-keystroke preview (debounced 500 ms) — updates candidate list as the task description changes.
- **Special features:**
  - Export to clipboard — copies the full packed prompt as it would be sent to an LLM.
  - A/B compare mode — two task descriptions side-by-side; highlights assets that appear in one but not the other.
- **Why critical:** when an operator suspects the Relevance Gate is selecting the wrong memories, this page shows exactly which assets were scored, why each was included or excluded, and where the token boundary fell. It is also the primary pedagogical tool for understanding how engram's context packing works.

#### /wisdom

- **Purpose:** Visualize the four wisdom curves with drill-down to source data.
- **Data:** `graph.db` `metrics_wisdom` tables (one row per asset per day per curve).
- **Interactions:** time range selector (7d / 30d / 90d / all); per-curve drill-down → source rows (asset-id, date, value, contributing events); CSV export of any curve's raw data; regression alerts banner (shown when any curve drops > 10% week-over-week).
- **Realtime:** SSE on `wisdom_sample` event (emitted hourly by the metrics aggregation job) — charts extend right in real time.

#### /autolearn (global console + per-workflow sub-page)

- **Purpose:** Live autolearn console — both a global overview and the per-workflow detail reachable from `/workflow/<name>`.
- **Data:** `evolution.tsv`; workspace logs (`~/.engram/journal/*.jsonl` autolearn events).
- **Interactions:** Start / Pause / Abort buttons (per workflow); live log tail of the current round (SSE-streamed lines from the subprocess); past runs table with per-round accept/reject outcome and metric delta.
- **Realtime:** SSE on `autolearn_round` event — log tail updates per line; past runs table appends row on round completion.

---

### 7.2 Routing + URL Scheme

All routes are clean URLs, deep-linkable, and bookmarkable. SvelteKit file-based routing maps directly:

```
/
/dashboard
/graph
/graph?scope=project&subtype=feedback
/memory/<asset-id>
/memory/<asset-id>?edit=1
/workflow/<name>
/workflow/<name>/rev/<revN>
/kb/<topic>
/kb/<topic>/<chapter-filename>
/inbox
/inbox/<msg-id>
/pools
/pools/<pool-name>
/pools/<pool-name>/revisions
/projects
/context-preview
/context-preview?task=<urlencoded>&budget=4000
/wisdom
/wisdom/workflow-mastery/<name>
/autolearn
/autolearn/<workflow-name>
```

All routes are server-rendered (SvelteKit SSR) for accessibility and direct URL sharing. Query parameters carry filter state so that a filtered graph view or a specific context-preview task can be bookmarked or shared as a URL.

---

### 7.3 Realtime via SSE

**Watcher daemon** — started automatically when `engram web serve` runs — uses OS-native filesystem notification to monitor the engram store:

- `<project root>/.memory/` (all scopes)
- `~/.engram/pools/`, `~/.engram/team/`, `~/.engram/org/`, `~/.engram/user/`
- `~/.engram/inbox/`
- `~/.engram/journal/*.jsonl`

OS backend: `inotify` on Linux; `FSEvents` on macOS; `ReadDirectoryChangesW` on Windows. On change, the daemon publishes an event to all active SSE streams. The watcher runs in a background thread inside the `engram web serve` process; it also runs as a standalone background service under `engram daemon start` when the web UI is not active.

**Frontend subscription:** `EventSource('/events?filter=asset_changed,inbox_message,...')`. The filter query parameter limits which event types are delivered to a given page — `/graph` subscribes only to `asset_changed`; `/inbox` subscribes to `inbox_message`; `/dashboard` subscribes to all.

**Event types (JSON on the wire):**

```json
{"type":"asset_changed","id":"local/feedback_foo","change":"updated","ts":"2026-04-18T10:30:00Z"}
{"type":"inbox_message","msg_id":"m-abc","to":"this-repo","change":"created"}
{"type":"proposal_created","proposal_id":"cp-xyz","class":"factual-conflict","severity":"warning"}
{"type":"autolearn_round","workflow":"release-checklist","round":5,"status":"accepted","metric_delta":0.03}
{"type":"wisdom_sample","curve":"workflow_mastery","scope":"release-checklist","value":0.87}
{"type":"pool_updated","pool":"design-system","revision":"r8","change":"new_revision"}
```

**Backpressure:** server buffers up to 100 events per connection; oldest dropped on overflow (with a `{"type":"overflow","dropped":N}` sentinel so the client can force a full reload if needed).

**Fallback:** if SSE is unsupported by the client (rare), the frontend falls back to polling `GET /api/sync?since=<ts>` every 10 seconds.

---

### 7.4 Authentication

**Default: no auth, bind 127.0.0.1** — safe because only local processes can connect to a loopback address. No credentials needed for the typical solo-developer workflow.

**Optional modes** (set in `~/.engram/config.toml` under `[web].auth_mode`):

| Mode | Description | Config keys |
|------|-------------|-------------|
| `none` | No auth (default); bind 127.0.0.1 only | — |
| `basic` | HTTP Basic auth | `[web].auth_user`, `[web].auth_pass_hash` (argon2id) |
| `token` | Bearer token | `[web].tokens` (path to file with one token per line; revocable) |

**LAN exposure safety gate:** if `bind = "0.0.0.0"` (or any non-loopback address), `engram web serve` refuses to start unless `auth_mode` is `basic` or `token`. The error message is explicit: `"Refusing to start: non-loopback bind requires auth_mode != none. Set [web].auth_mode = basic or token."` There is no flag to bypass this check.

**What the web UI never does:** it does not accept LLM API keys, secrets, or credentials in any request body. All secrets stay in `config.toml` and environment variables on the server side. Requests from the browser carry only asset IDs, parameters, and the session token.

**Session:** HTTP-only cookie containing a signed session token; 8-hour default timeout; configurable via `[web].session_timeout_hours`.

---

### 7.5 Internationalization

Two locales ship on day one: English (`en`) and Chinese (`zh`).

**Selection priority (highest to lowest):**

1. URL query parameter `?lang=zh`
2. User preference cookie (`engram_lang`)
3. `Accept-Language` HTTP header
4. `[web].default_locale` in `config.toml` (default: `en`)

**Translation file structure:**

```
web/frontend/src/i18n/
├── en.json
└── zh.json
```

All user-facing strings are externalized. No hardcoded text appears in Svelte components — every label, button text, aria-label, and error message references a key. Key naming aligns with the glossary (e.g., `memory.subtype.feedback`, `scope.team`, `page.context_preview.title`) so that the translation files double as a machine-readable glossary index.

Additional locales can be added by dropping a new `<locale>.json` file; no code changes required.

---

### 7.6 Accessibility + Keyboard Navigation

- **Compliance target:** WCAG 2.1 AA.
- **Keyboard navigation:** Tab order follows DOM reading order; `j` / `k` moves to next / previous item in lists and tables; `/` focuses the global search box; `g g` (double-tap) navigates to `/dashboard` (vim-style global shortcut); `Esc` closes modals and side panels.
- **Screen reader support:** `aria-label` on all icon-only buttons; semantic HTML throughout (`<nav>`, `<main>`, `<article>`, `<section>`, `<aside>`); live regions (`aria-live="polite"`) for SSE-driven updates so assistive technology announces new messages and round completions.
- **Color:** no information conveyed by color alone (every status also uses an icon or text label); 4.5:1 minimum contrast ratio for all text; dark/light theme toggle in the header (preference saved in cookie).

---

### 7.7 Packaging + Deployment

**Distribution options:**

1. **pip optional extras (primary):** `pip install 'engram[web]'` — installs FastAPI, Uvicorn, and SvelteKit runtime dependencies; frontend bundle is pre-built at package time (no Node.js required at runtime).
2. **Single binary (future, post-v0.2):** via PyOxidizer or Nuitka; self-contained executable embedding the frontend bundle.
3. **Docker image:** `ghcr.io/tbosos/engram-web:latest` — containerized; mounts `~/.engram` and project directories via volume; exposes port 8787.

**Static assets:** the SvelteKit `build` output is bundled into the Python package under `engram/web/static/`. FastAPI serves it via `StaticFiles`. No Node.js, npm, or Vite is required on the end-user machine.

**Resource usage targets:**

| Resource | Target |
|----------|--------|
| RAM (steady state) | < 100 MB |
| CPU (idle) | < 5% |
| Disk (binary + bundle + graph.db cache) | < 200 MB |
| Cold startup time | < 1 s to first HTTP response |

**Startup:** `engram web serve` — opens port, starts watcher daemon, prints `Engram web UI running at http://127.0.0.1:8787`. `engram web open` opens the URL in the default browser.

**Graceful shutdown:** on SIGTERM — finish in-flight requests, close SSE connections (sends `{"type":"shutdown"}` event so clients can show a "server stopped" banner), stop watcher, flush journal, exit 0. Hard kill (SIGKILL) after a 5-second deadline if shutdown has not completed.

---

### 7.8 Testing Strategy

Detail deferred to §10; key points for the web UI:

- **Unit:** Svelte components tested with Vitest + `@testing-library/svelte`; FastAPI route handlers tested with pytest + httpx.
- **Integration:** API routes tested against a real (in-memory) SQLite graph.db; SSE event stream tested with an async httpx client that reads from the event stream.
- **E2E:** Playwright scenarios covering all 10 pages — smoke tests (load each page, no console errors, no broken aria roles); interaction tests for the critical flows (save memory, run context-preview, send inbox message, start autolearn round).
- **Visual regression:** Percy screenshots in CI (optional; gated behind `CI_PERCY=1` env flag).
- **Accessibility:** axe-core assertions in Playwright (`@axe-core/playwright`) run on every page load test to catch WCAG regressions.

---

### 7.9 Observability of the Web UI Itself

- **Access log:** all HTTP requests logged to `~/.engram/web.log` (Apache Combined Log Format); no PII beyond IP (loopback only by default).
- **Error log:** uncaught exceptions + 5xx responses logged with stack traces to `~/.engram/web.log`.
- **No telemetry:** the web UI makes no outbound network calls. No analytics, no crash reporting, no external CDN. All assets served locally.
- **Health check:** `GET /healthz` → `{"status": "ok", "version": "0.2.x", "watcher": "running", "db": "ok"}`. Suitable for use as a Docker/systemd health check.
- **Debug page:** `GET /debug` (accessible only when `auth_mode = basic` or `token`, and only to authenticated sessions) — shows: watcher stats (files watched, events/s), graph.db cache hit rates, SSE subscriber counts per event type, active session count, uptime, and server version.

---

### 7.10 Implementation Priority

Not all 10 pages ship in the initial web UI release. Priority is tracked in TASKS.md milestones M4–M7:

**P0 — M7 MVP (must ship):**

| Page | Reason for P0 |
|------|---------------|
| `/dashboard` | First page opened; shows system health at a glance |
| `/memory/<id>` | Core asset editing — most frequent human interaction |
| `/workflow/<name>` | Autolearn control requires a UI; CLI-only is too opaque |
| `/kb/<topic>` | KB compile + edit loop benefits from side-by-side view |
| `/inbox` | Cross-repo coordination requires UI for non-trivial message volumes |
| `/context-preview` | Critical debug tool; operators cannot trust the system without it |

**P1 — M7 polish (ship before M7 closes):**

| Page | Reason for P1 |
|------|---------------|
| `/graph` | High value but complex; D3 force layout is non-trivial to get right |
| `/pools` | Needed once team pools are in use; not day-one requirement |
| `/projects` | Only relevant when user has ≥ 2 engram projects |
| `/wisdom` | Curves available via CLI `engram wisdom report`; UI is convenience |
| `/autolearn` | Global view; per-workflow tab in `/workflow/<name>` covers the P0 use case |

---

## 8. Key Invariants

### 8.0 Introduction

Earlier chapters introduced invariants locally: §2.3 listed five "immutables" for data independence, journaling, intelligence gating, conflict resolution, and no auto-delete; §5.0.3 stated six intelligence-layer design principles; SPEC §11 declared consistency non-goals. §8 consolidates all of them into a single authoritative reference list of twelve non-negotiable invariants.

Every implementation — the reference engram-cli, third-party tools, future components, and any subsystem added after this document is written — MUST satisfy every invariant below, in addition to every SPEC rule. An implementation that satisfies eleven of the twelve is non-conforming.

---

### 8.1 The Twelve Invariants

**1. Data Independence**

Layer 1 files never reference any tool-specific path, binary format, or engram-proprietary field. A `.memory/` directory that is SPEC-compliant works without engram-cli installed: any LLM can read it, any text editor can edit it, any version control system can track it, any human can understand it.

- Rationale: the store outlives the tool. Users must not be locked in.
- Enforcement: no SPEC frontmatter field is named with an `engram_`-prefixed namespace that has no meaning outside engram. SPEC §12 FM validator catches tool-specific namespaces on `engram validate`.

**2. Real-File Uniqueness**

Each asset's canonical file lives in exactly one location (its scope root). All other apparent paths are symlinks pointing to that canonical location. Duplicate file contents at multiple non-symlink paths are forbidden.

- Rationale: eliminates "which copy is truth?" ambiguity; simplifies sync, backup, and validation.
- Enforcement: `engram validate` detects multiple regular files with identical `asset_id` or identical content hash; operator is required to fix before validation passes.

**3. No Auto-Delete**

No layer ever deletes asset data without explicit operator action. Archive is the mandatory intermediate step. Physical removal requires the asset to have resided in `archive/` for at least six months, and the `engram archive gc` command requires the explicit `--past-retention` flag plus an interactive confirmation prompt.

- Rationale: users lose months of memory only through their own deliberate decisions; mistakes are recoverable.
- Enforcement: archive retention floor is a hardcoded constant (not a config value); any PR that makes it configurable below 180 days is rejected at review.

**4. Intelligence Layer Is Disableable**

Every Intelligence Layer component (Relevance Gate, Consistency Engine, Autolearn Engine, Evolve Engine, Inter-Repo Messenger, Wisdom Metrics) has an `enabled = false` configuration toggle. With every toggle set to false, the system MUST still pass `engram validate`, `engram memory retrieve`, and `engram review`.

- Rationale: intelligence is an optional enhancement, not a foundation. Server deployments, air-gapped environments, and minimalists are first-class users.
- Enforcement: CI runs an "all intelligence off" test profile on every commit; the full command suite must pass in that profile.

**5. Observation Layer Is Optional**

The CLI alone (`engram-cli`) must deliver a fully functional engram experience. The web UI (Layer 5) is a convenience. Installing `pip install engram` must not pull in FastAPI, Svelte build artifacts, or any GUI dependency.

- Rationale: headless deployments (servers, CI pipelines, terminal minimalists) are first-class.
- Enforcement: `engram-cli` package extras are optional (`pip install engram[web]` for the UI); the base package dependency list is reviewed on every release.

**6. Adapters Regenerate Non-Destructively**

`engram adapter <tool> --regenerate` preserves all user-authored content enclosed in `engram:begin`/`engram:end` marker blocks. It never overwrites user text. A missing or malformed marker pair is an error, not a silent overwrite.

- Rationale: users customize adapter files; tool version updates must not destroy their work.
- Enforcement: missing marker emits error code `E-ADP-001` and exits non-zero; the regeneration function has unit tests covering marker-present, marker-absent, and marker-malformed cases.

**7. MCP Server Is Stateless**

Every MCP request re-reads filesystem state from scratch. No in-memory session state is carried between calls. Each tool function is a pure function over the filesystem: same inputs plus same filesystem state produce identical outputs.

- Rationale: predictability and concurrent-session safety. Multiple LLM sessions hitting the same store simultaneously must produce identical results for identical inputs.
- Enforcement: MCP server architecture review prohibits instance-level mutable state; integration tests run two concurrent MCP sessions against a shared store and assert result equivalence.

**8. CLI Commands Are Idempotent by Default**

Running the same `engram` command twice in succession produces the same observable outcome as running it once. Exceptions are explicitly mutating commands (e.g., `engram workflow run`, `engram journal append`) which are documented as non-idempotent in their man page entries.

- Rationale: safe scripting and automation; retries do not corrupt state.
- Enforcement: CLI command design checklist requires an idempotency assessment for every new command; non-idempotent commands carry a `# NON-IDEMPOTENT` annotation in the CLI module.

**9. Journals Are Append-Only**

`~/.engram/journal/*.jsonl` files are never edited in place. New events are always appended. Compaction (for storage management) moves complete journal files to `archive/journal/` and starts a fresh file; it never deletes events or modifies existing rows.

- Rationale: audit trail integrity. The full event history enables state reconstruction at any past point in time.
- Enforcement: `engram validate` detects in-place edits by comparing file mtime against the timestamp of the oldest entry in the file; any mismatch is a validation error.

**10. Spec Precedes Implementation**

Any feature that affects on-disk format (Layer 1), wire protocol (Layer 4 MCP), or cross-scope behavior first appears in a SPEC change, then in DESIGN, then in code. No behavior in any implementation layer is "implementation-defined" when it touches the on-disk format.

- Rationale: multi-implementation compatibility. Third-party tools build against SPEC with confidence only if SPEC is always ahead of code.
- Enforcement: PR review checklist requires a SPEC reference or SPEC change for any new on-disk field; SPEC changes require a discussion issue with at least one week open before merge.

**11. No Capacity Caps**

engram imposes no hard upper bound on the number of assets in any scope, the number of scopes, or the size of any asset class. Quality is maintained by the Consistency Engine (§5.2) and user-driven archival, not by eviction or size limits.

- Rationale: users' knowledge stores can grow decade-scale. Eviction destroys memory without user consent and violates Invariant 3.
- Enforcement: `engram validate` rules reject any hardcoded size check in component code; MEMORY.md templates have no line-count gate; performance requirements are expressed as latency SLOs, not capacity limits.

**12. Cross-Process Safety**

Concurrent `engram` invocations — multiple LLM sessions, GUI + CLI, parallel CI jobs — never corrupt shared state. SQLite operates in WAL mode. Asset file writes use atomic write-temp-then-rename. Exclusive operations (archive gc, schema migration) acquire `fcntl` advisory locks.

- Rationale: real-world usage involves simultaneous access from multiple processes.
- Enforcement: integration test suite includes N-concurrent-operation stress tests (N ≥ 4); CI test combinations cover POSIX file-locking (Linux, macOS) and Windows file-locking separately.

---

### 8.2 Composability of the Invariants

The twelve invariants are not independent rules — they form a mutually reinforcing foundation. Removing any single invariant undermines others:

| If you drop… | …it breaks |
|---|---|
| Invariant 3 (no auto-delete) | Users cannot trust archive; memory loss becomes invisible |
| Invariant 9 (append-only journals) | Consistency Engine cannot audit history; reconstruct-state breaks |
| Invariant 7 (stateless MCP) | Concurrent sessions diverge; Invariant 12 becomes unenforceable |
| Invariant 1 (data independence) | Store is no longer portable; third-party tools cannot conform |
| Invariant 4 (intelligence disableable) | Invariant 5 (CLI sufficiency) is undermined for offline environments |
| Invariant 11 (no capacity caps) | Eviction silently deletes memory, violating Invariant 3 |

**Adding a new invariant** requires: a spec-level discussion issue open for at least two weeks, consensus from at least two maintainers, and a rationale entry in this section explaining what breaks if the new invariant is dropped. Invariants are easier to add than to remove; removal requires demonstrating that no existing invariant depends on the one being dropped.

---

---

## 9. Source Repository Layout

### 9.0 Introduction

§9 specifies the source tree for the engram GitHub repository itself, and the runtime layout created on user machines (under `~/.engram/` and each `<project>/.memory/`). Implementers reading this section know where every piece of code, configuration, and data goes — both at development time (what lives in the repo) and at runtime (what the CLI creates on a user's system).

The two layouts are complementary: the repo tree defines what ships; the machine layout defines what runs. Neither duplicates the other.

### 9.1 GitHub Repository Tree

```
engram/                                     # GitHub repo root
├── README.md / README.zh.md                # bilingual intro
├── SPEC.md / SPEC.zh.md                    # format spec (v0.2)
├── DESIGN.md / DESIGN.zh.md                # this doc
├── METHODOLOGY.md / METHODOLOGY.zh.md      # how LLMs should write memory (to be written in Phase 4)
├── TASKS.md / TASKS.zh.md                  # live milestone board (Phase 3)
├── CONTRIBUTING.md / CONTRIBUTING.zh.md    # (Phase 4)
├── LICENSE                                 # MIT
├── CHANGELOG.md                            # (created at v0.2.0 release)
├── pyproject.toml                          # root (workspace for cli/, web/)
├── .pre-commit-config.yaml                 # lint/format hooks
├── .github/
│   ├── workflows/
│   │   ├── ci.yaml                         # test + lint + typecheck combinations
│   │   ├── release.yaml                    # pypi publish on tag
│   │   ├── benchmark.yaml                  # per SPEC Amendment B — on release only
│   │   └── pages.yaml                      # GitHub Pages deploy (already served from /docs)
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── cli/                                    # Layer 2 + parts of 3, 4
│   ├── pyproject.toml
│   ├── engram/                             # Python package
│   │   ├── __init__.py
│   │   ├── __main__.py                     # `python -m engram` entrypoint
│   │   ├── cli.py                          # click CLI dispatcher
│   │   ├── core/                           # Layer 1 access
│   │   │   ├── paths.py                    # ~/.engram/ + project root resolution
│   │   │   ├── frontmatter.py              # YAML parse + validation
│   │   │   ├── fs.py                       # atomic writes, locks, symlinks
│   │   │   ├── graph_db.py                 # SQLite schema + queries
│   │   │   ├── journal.py                  # append-only jsonl helpers
│   │   │   └── cache.py                    # embedding + FTS5 + relevance cache
│   │   ├── memory/                         # memory subcommands
│   │   │   ├── commands.py                 # add/list/read/update/archive/search
│   │   │   └── render.py                   # MEMORY.md generation
│   │   ├── workflow/
│   │   │   ├── commands.py
│   │   │   ├── runner.py                   # spine invocation
│   │   │   └── fixtures.py                 # fixture harness
│   │   ├── kb/
│   │   │   ├── commands.py
│   │   │   └── compiler.py                 # _compiled.md generation
│   │   ├── pool/
│   │   │   ├── commands.py
│   │   │   ├── propagation.py              # auto-sync/notify/pinned logic
│   │   │   └── git_sync.py                 # git-based team/org/pool sync
│   │   ├── team/                           # same as pool for team scope
│   │   ├── org/                            # same for org scope
│   │   ├── inbox/
│   │   │   ├── commands.py
│   │   │   ├── messenger.py                # SPEC §10 implementation
│   │   │   ├── dedup.py
│   │   │   └── rate_limit.py
│   │   ├── consistency/
│   │   │   ├── commands.py
│   │   │   ├── engine.py                   # DESIGN §5.2 4-phase scan
│   │   │   ├── phase1_static.py
│   │   │   ├── phase2_semantic.py          # DBSCAN
│   │   │   ├── phase3_llm.py
│   │   │   ├── phase4_execution.py
│   │   │   └── resolve.py                  # apply_update/supersede/merge/archive/dismiss
│   │   ├── relevance/                      # Layer 3 §5.1
│   │   │   ├── gate.py                     # 7-stage hybrid pipeline
│   │   │   ├── embedder.py                 # providers: local bge / openai / cohere
│   │   │   ├── bm25.py
│   │   │   └── temporal.py                 # "N weeks ago" parsing
│   │   ├── autolearn/                      # §5.3
│   │   │   ├── engine.py                   # Darwin 8-discipline loop
│   │   │   ├── proposer.py
│   │   │   ├── judge.py
│   │   │   └── ratchet.py
│   │   ├── evolve/                         # §5.4
│   │   │   └── engine.py                   # ReMem action-think-refine
│   │   ├── wisdom/                         # §5.6
│   │   │   ├── aggregator.py
│   │   │   └── curves.py
│   │   ├── context/                        # §6.3 prompt pack
│   │   │   └── pack.py
│   │   ├── mcp/                            # §6.2 MCP server
│   │   │   ├── server.py
│   │   │   └── tools.py                    # typed pydantic schemas
│   │   ├── migrate/                        # SPEC §13.4/6
│   │   │   ├── commands.py
│   │   │   ├── v0_1.py
│   │   │   ├── claude_code.py
│   │   │   ├── chatgpt.py
│   │   │   ├── mem0.py
│   │   │   ├── obsidian.py
│   │   │   ├── letta.py
│   │   │   ├── mempalace.py
│   │   │   └── markdown.py
│   │   ├── adapter/                        # §6.1 adapters
│   │   │   └── commands.py
│   │   ├── playbook/                       # §6/§8 playbook install
│   │   │   └── commands.py
│   │   └── config.py                       # ~/.engram/config.toml
│   └── tests/                              # pytest
│
├── web/                                    # Layer 5 engram-web
│   ├── backend/                            # FastAPI
│   │   ├── pyproject.toml
│   │   ├── engram_web/
│   │   │   ├── app.py                      # FastAPI app factory
│   │   │   ├── routes/
│   │   │   ├── sse.py                      # Server-Sent Events
│   │   │   ├── watcher.py                  # inotify/FSEvents
│   │   │   └── auth.py                     # none/basic/token
│   │   └── tests/
│   └── frontend/                           # Svelte
│       ├── package.json
│       ├── svelte.config.js
│       ├── src/
│       │   ├── routes/                     # SvelteKit pages (§7.1)
│       │   ├── lib/
│       │   │   ├── components/
│       │   │   ├── stores/
│       │   │   └── api/
│       │   └── i18n/                       # en.json, zh.json
│       └── tests/
│
├── sdk-ts/                                 # TypeScript SDK
│   ├── package.json
│   ├── src/
│   │   ├── context.ts
│   │   ├── memory.ts
│   │   ├── workflow.ts
│   │   ├── inbox.ts
│   │   └── index.ts
│   └── tests/
│
├── adapters/                               # §6.1 templates
│   ├── claude-code/
│   │   ├── CLAUDE.md.tmpl
│   │   └── hooks/
│   │       ├── engram_stop.sh              # SPEC Amendment B §B.4
│   │       └── engram_precompact.sh
│   ├── codex/AGENTS.md.tmpl
│   ├── gemini-cli/GEMINI.md.tmpl
│   ├── cursor/rules.tmpl
│   └── raw-api/system_prompt.txt.tmpl
│
├── seeds/                                  # init seeds
│   ├── base/                               # neutral defaults
│   ├── opinionated/                        # optional baseline feedback
│   └── profiles/
│       ├── embedded-systems/
│       ├── web-platform/
│       └── data-eng/
│
├── playbooks/                              # community-contributed playbooks
│   └── README.md                           # submission guide
│
├── tests/                                  # cross-component
│   ├── conformance/                        # SPEC §12 fixtures
│   │   ├── healthy/
│   │   ├── edge-cases/
│   │   ├── v0_1_legacy/
│   │   └── broken/
│   ├── e2e/
│   └── manual-checklist.md
│
├── benchmarks/                             # Amendment B §B.3
│   ├── BENCHMARKS.md
│   ├── consistency_test/
│   ├── scope_isolation_test/
│   ├── longmemeval_bench.py
│   └── evolution_test/
│
└── docs/                                   # GitHub Pages root (/docs)
    ├── .nojekyll
    ├── index.html                          # language chooser
    ├── en/index.html
    ├── zh/index.html
    ├── assets/                             # fonts.css + anthropic.css + app.css
    ├── WEBSITE-MAINT.md
    ├── glossary.md / glossary.zh.md
    ├── archive/v0.1/                       # frozen
    └── superpowers/
        ├── plans/
        └── specs/
```

### 9.2 Top-Level Directory Responsibilities

One-line summary per top-level entry; a reader can scan this table and jump to the relevant sub-tree above.

| Directory | Purpose |
|---|---|
| `cli/` | Python CLI — reference implementation, ships as `engram` package on PyPI |
| `web/` | engram-web — FastAPI backend + SvelteKit frontend; optional install via `engram[web]` extra |
| `sdk-ts/` | TypeScript SDK — `@engram/sdk` npm package |
| `adapters/` | Prompt template files (source); `engram adapter <tool>` renders instance to user project |
| `seeds/` | Template memory content for `engram init`; base (neutral) + opinionated + domain profiles |
| `playbooks/` | Community-contributed Playbook submissions (gathered here for discoverability) |
| `tests/` | Cross-component tests (conformance + E2E + manual); per-component tests live in their own directories |
| `benchmarks/` | Self-built + LongMemEval + evolution — reproducible; results committed per Amendment B |
| `docs/` | GitHub Pages (landing page + spec companions); served from `main/docs` |

### 9.3 User Machine Layout

The following paths are created on user machines by `engram init` / runtime operations. This is independent of the repository and describes what implementers must produce on disk (recap from SPEC §3.2 / DESIGN §3).

```
~/.engram/
├── version                                 # "0.2"
├── config.toml
├── org/<org>/                              # scope: org
├── team/<team>/                            # scope: team
├── user/                                   # scope: user
├── pools/<pool>/                           # subscribable (scope: pool)
├── playbooks/<name>/                       # installed playbooks
├── inbox/<repo-id>/                        # cross-repo messages
├── archive/                                # tombstoned assets (retention)
├── workspace/                              # autolearn / evolve / consistency sandboxes
├── cache/                                  # embedding + FTS5 + relevance
├── journal/                                # *.jsonl append-only
├── graph.db                                # SQLite index
└── web.log                                 # if web server ran

<project>/
├── .memory/                                # project-scope store
│   ├── MEMORY.md
│   ├── pools.toml
│   ├── local/                              # scope: project assets
│   ├── pools/                              # symlinks to ~/.engram/pools/<name>/
│   ├── workflows/
│   ├── kb/
│   └── index/                              # optional topic sub-indexes
├── .engram/
│   └── version
├── CLAUDE.md / AGENTS.md / GEMINI.md       # adapter files (if generated)
└── .cursor/rules                           # if cursor adapter
```

### 9.4 Code Style and Tooling

**Python (`cli/`, `web/backend/`):**
- Linter: `ruff` (replaces flake8/isort/pylint in one)
- Formatter: `ruff format` (not black — ruff covers it)
- Type checker: `mypy --strict` on `cli/engram/` and `web/backend/engram_web/`
- Line length: 100 cols
- Python version: 3.10+ minimum (tested on 3.10, 3.11, 3.12, 3.13)

**TypeScript (`web/frontend/`, `sdk-ts/`):**
- Linter: `eslint` with `@typescript-eslint`
- Formatter: `prettier` (100 cols, single quotes)
- Type strictness: `tsconfig strict: true`
- Node: ≥18 (for `sdk-ts`); Bun/Deno compatible on best-effort

**Shell scripts (`adapters/*/hooks/`):**
- `shellcheck` in CI
- Shebang: `#!/usr/bin/env bash`, set `set -euo pipefail`

**Commit conventions:** Conventional Commits (`type(scope): subject`). Types: `feat / fix / docs / refactor / test / chore / perf / ci / spec / design / website`.

**Branch model:**
- `main` — stable; every commit passes CI
- `feat/<topic>` — feature branches (merged via PR)
- Release tags: `v0.2.0`, `v0.2.1`, …

### 9.5 Package Distribution

| Package | Registry | Install |
|---|---|---|
| `engram` (CLI + intelligence + MCP) | PyPI | `pip install engram` |
| `engram[web]` (+ FastAPI + Svelte bundle) | PyPI extra | `pip install 'engram[web]'` |
| `@engram/sdk` | npm | `npm install @engram/sdk` |
| `engram` (Homebrew) | `brew tap TbusOS/engram` | `brew install engram` (M3+) |
| GitHub Pages site | static | automatic on push to `main/docs` |

---

## 10. Testing Strategy

### 10.0 Test Pyramid and Philosophy

**Five test types, ordered by feedback speed:**

| Layer | Scope | Speed | External deps |
|---|---|---|---|
| Unit | Pure functions, data structures | < 1s total | None |
| Integration | Component interactions (graph.db + fs + cli) | Seconds | Local DB, filesystem |
| E2E | Full-stack scenarios (init → add → search → review) | Minutes | CLI in tempdir |
| Conformance | SPEC compliance fixtures (portable, 3rd-party reusable) | Minutes | None |
| LLM behavior | Adapter + context-pack correctness with real LLMs | Hours / on-demand | LLM provider |

**Philosophy:** Unit tests are the fastest feedback loop and catch the most regressions cheaply. E2E tests catch integration bugs that unit tests miss. Conformance fixtures make the SPEC portable — any engram-compliant tool (Go port, Rust port) can run them to certify compliance. LLM behavior is inherently probabilistic; full automation is impractical, so accept a semi-automated model with golden records and manual checkpoints at release boundaries.

### 10.1 Coverage Targets

- **Python (`cli/engram/`):** ≥ 80% line coverage, enforced by `pytest-cov --fail-under=80`
- **TypeScript SDK (`sdk-ts/`):** ≥ 80% line coverage, enforced by `vitest --coverage`
- **Svelte frontend (`web/frontend/`):** ≥ 70% component coverage, enforced by `vitest` + `@testing-library/svelte`
- **CI enforcement:** PR is blocked if coverage drops > 2% below the current baseline (stored in `tests/.coverage-baseline.json`)
- **Benchmark scripts (`tests/perf/`):** no coverage requirement — not production code
- **Mandatory path:** every CLI subcommand (`init`, `add`, `search`, `review`, `migrate`, `pool`, `inbox`, `context pack`, `validate`, `consistency scan`, `mcp serve`, `web serve`, `export`, `conformance`) has at least one E2E test covering the happy path

### 10.2 Conformance Fixtures (`tests/conformance/`)

A SPEC-level test suite that any engram-compliant tool can run. Every fixture is a complete `.memory/` directory plus an expected `validate` JSON output committed alongside it.

```
tests/conformance/
├── healthy/
│   ├── minimum-viable/             # SPEC §14.A example
│   ├── mid-size/                   # ~50 assets across subtypes
│   └── large-with-pools/           # ~500 assets + 3 pools
├── edge-cases/
│   ├── unicode-names/
│   ├── symlink-chains/
│   ├── empty-workflows/
│   └── long-memory/                # single memory >10K lines (no cap)
├── v0_1_legacy/
│   ├── flat-memory/                # needs migration
│   └── shared-pool-v0_1/
├── broken/
│   ├── missing-frontmatter/
│   ├── mandatory-override-conflict/
│   ├── circular-supersedes/
│   ├── dangling-symlink/
│   └── wrong-scope-location/
└── expected/
    └── <fixture-name>.json         # canonical validate output
```

**Running:** `engram conformance test tests/conformance/<fixture-name>` — runs `validate`, diffs against the expected JSON, returns pass/fail.

**Authoring rule:** every new SPEC rule gets at least one corresponding fixture (either in `healthy/`, `edge-cases/`, or `broken/`). When a rule is deleted or relaxed, the fixture moves to a `deprecated/` directory and is removed from CI rather than deleted, preserving migration history.

**3rd-party portability:** Go and Rust engram ports run this suite via a thin shim that calls their own `validate` implementation and compares output to `expected/*.json`. Fixture format is stable across minor versions; breaking changes require a new fixture version prefix (`v2/`).

### 10.3 E2E Test Scenarios (`tests/e2e/`)

Pytest-based. Each scenario creates a fresh tempdir, runs the CLI as a subprocess, and asserts on stdout/stderr/filesystem state. No mocking of the CLI itself.

```
tests/e2e/
├── test_init_and_review.py              # empty dir → init → review: all green
├── test_migrate_from_v0_1.py            # build v0.1 store → migrate → validate clean
├── test_multi_adapter.py                # init with claude+codex+gemini → verify all 3 adapter files + same .memory/
├── test_pool_subscribe_notify.py        # publish pool → subscriber notified → accept → sync
├── test_pool_subscribe_pinned.py        # subscribe pinned → publish new → no auto-update → manual update
├── test_inbox_roundtrip.py              # send from A → B acknowledges → B resolves → A sees notification
├── test_consistency_scan_seven_classes.py  # inject synthetic conflicts → scan detects → resolve
├── test_autolearn_smoke.py              # minimal workflow → 3 autolearn rounds → verify monotone improvement
├── test_mcp_stdio.py                    # spawn MCP server → call each tool → verify responses
├── test_web_smoke.py                    # start web serve → playwright click through 10 pages → no 500s
└── test_export_formats.py              # export markdown/prompt/json — verify output structure
```

**Runtime target:** the full E2E suite completes in < 3 minutes on a consumer laptop (Apple M-series or equivalent x86-64). No LLM calls by default. Scenarios that require a live LLM are decorated `@pytest.mark.llm_live` and run only when `--llm-live` is passed.

**Isolation:** each test gets its own `tmp_path` (pytest fixture). Parallel execution via `pytest-xdist -n auto` is safe because tests do not share filesystem state or ports (each picks a random free port for `web serve` / `mcp serve`).

### 10.4 LLM Behavior Verification (Semi-Automated)

The CLI is deterministic; LLM responses are probabilistic. A two-tier approach keeps CI costs low while preserving behavioral coverage.

**Tier 1 — Automated prompt-pack validation** (runs in CI when a provider API key is present in the environment):

- Fixed store + fixed task → `engram context pack --task="..."` → compare packed-prompt bytes against a committed baseline
- Output is deterministic when the asset set and budget are fixed (no LLM call in this step)
- 50 canonical tasks × stable asset sets → byte-for-byte comparison to `tests/llm-eval/baselines/pack/*.txt`
- Test fails if packed output changes; reviewer must approve baseline update via PR

**Tier 2 — Semi-automated LLM-behavior eval** (`tests/llm-eval/`):

- Fixed store + fixed task → live LLM call (reference model: Claude Sonnet 4.6) → structured JSON output
- Assertions: did the LLM cite the expected memory? (check for specific asset IDs or key phrases in response)
- Runs on-demand only (`make llm-eval`); not per-PR (avoids API budget burn)
- Results stored as golden records in `tests/llm-eval/golden/`; changes require manual sign-off

**Example eval scenarios:**

| Scenario | Expected LLM behavior |
|---|---|
| "User asks about push rules" | Response cites `feedback_push_confirmation` asset |
| "Agent discovers bug in sibling repo" | LLM emits `engram_inbox_send` tool call with correct `intent` field |
| "Task in same topic as 3 recent memories" | LLM loads all 3 + stays internally consistent |
| "User asks to add a new team member" | LLM checks `onboarding_checklist` workflow before answering |

### 10.5 Performance Tests (`tests/perf/`)

Scale-based regression guards. Not run per-PR; run weekly in CI and on-demand before releases.

**Asset counts under test:**

| Scale | Represents |
|---|---|
| 100 assets | Minimum feasibility |
| 1,000 assets | Typical user after ~3 months |
| 10,000 assets | Typical user after ~2 years |
| 100,000 assets | Power user / long-term store |

**Targets (per SPEC §20 performance budgets):**

| Operation | Target |
|---|---|
| `engram init` on empty project | < 1s |
| `engram context pack --budget=900` (cold cache, 10K assets) | < 100ms |
| `engram context pack --budget=900` (cold cache, 100K assets) | < 500ms |
| `engram context pack --budget=900` (warm cache, any scale) | < 50ms |
| `engram validate` (1K assets) | < 2s |
| `engram validate` (100K assets) | < 20s |
| `engram consistency scan --phase=1+2` (10K assets) | < 10min |
| `engram consistency scan --phase=1+2` (100K assets) | < 90min (daily cron acceptable) |
| `engram memory search` (any scale) | < 100ms (graph.db indexes + FTS5) |

**Test harness:** `tests/perf/bench_*.py` — generates synthetic stores via `engram conformance gen --count=N`, times each operation with `time.perf_counter`, compares against committed baselines in `tests/perf/baselines.json`. A 20% regression from baseline fails the weekly job and opens a GitHub issue automatically.

### 10.6 CI Test Combinations

`.github/workflows/ci.yaml`:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ['3.10', '3.11', '3.12', '3.13']
    exclude:
      # macOS + Python 3.10 tested at monthly cadence only (save CI minutes)
      - {os: macos-latest, python: '3.10'}
```

**Per-combination:** unit tests + integration tests + conformance suite.

**E2E:** runs only on `ubuntu-latest` + Python 3.12 (fast path). Adding additional OS/version combos for E2E requires explicit justification (high CI cost).

**Web E2E (Playwright):** ubuntu-latest only. Playwright browser binaries are not installed on macOS or Windows runners.

**TypeScript SDK:** Node 18, 20, 22 × ubuntu-latest + macos-latest; Windows skipped (less common deployment environment; tested monthly via a separate scheduled workflow).

**Scheduled jobs:**

| Job | Cadence | Trigger |
|---|---|---|
| Performance benchmarks | Weekly (Monday 02:00 UTC) | Cron |
| macOS + Python 3.10 combination | Monthly | Cron |
| TypeScript SDK on Windows | Monthly | Cron |
| LLM-eval golden-record refresh | On-demand | Manual `workflow_dispatch` |

### 10.7 Manual Release Checklist

`tests/manual-checklist.md` — humans run at each release tag before publishing to PyPI:

- [ ] Install via `pip install 'engram'` in a fresh venv — works offline except for LLM provider calls
- [ ] `engram init` in a fresh directory — generates all expected files with correct structure
- [ ] Open Claude Code on the project — `CLAUDE.md` auto-loaded, `.memory/` referenced without errors
- [ ] Web UI smoke test: open 10 distinct pages, verify no console errors, confirm keyboard navigation works
- [ ] Migrate a real Claude Code memory store — zero data loss, `validate` reports clean after migration
- [ ] Regression sanity: run the prior release's E2E suite against the new version binary — all tests pass
- [ ] Performance dashboard: compare benchmark output against prior release — no curve regressions
- [ ] Conformance suite: run against all three reference implementations (Python, Go, Rust) — all pass

---

## 11. Developer Pitfalls + Mitigations

### 11.0 Introduction

§11 enumerates 8 systemic pitfalls that implementers MUST defend against. Each is a failure mode the design has seen in similar systems (MemPalace, Letta, mem0, v0.1 engram). Defenses are distributed across chapters; this section maps them centrally so engineers can internalize the failure pattern before encountering it in production. The pitfalls are independent but share a common set of cross-cutting defenses summarised in §11.9.

### 11.1 Pitfall 1 — Write Amplification

**Trigger:** Every user correction spawns a new memory entry. After months of use, `.memory/` explodes with near-duplicate feedback entries that differ only in phrasing.

**Symptom:** `engram review` shows 500+ similar feedback entries; the Relevance Gate packs redundant content into context windows; the LLM receives conflicting signals about which rule is current and hedges rather than acting.

**Root mitigation:**

- **Write-time dedup:** `engram memory add` checks for semantic similarity (cosine > 0.85 + keyword overlap) against existing entries in the same scope; prompts the user with "similar memory exists — update or create new?" before writing.
- **Evolve Engine consolidation (§5.4):** the monthly `merge` proposal pass automatically clusters semantically-close entries and proposes a single canonical replacement.
- **Supersede chains over duplication:** prefer updating the existing asset with `supersedes:` linkage to the prior version; document the evolution, not the complete history.

**Monitoring signal:** Asset count growth rate > 50/week for the same scope without proportional unique-semantic-cluster growth (measured by the Consistency Engine's `topic-divergence` detector).

**Fallback:** Run `engram consistency scan --phase=2` followed by `engram evolve scan` to surface aggressive merge proposals; operator accepts in batch via the `engram evolve scan` interactive UI.

### 11.2 Pitfall 2 — Metric Gaming (Autolearn)

**Trigger:** LLM-generated spine modifications maximise the declared acceptance metric via shortcuts — skipping edge-case branches, hardcoding fixture outputs, or trivially satisfying the success predicate.

**Symptom:** The metric improves each round; real-world task performance degrades; fixtures pass but production workflows fail on inputs not in the fixture set.

**Root mitigation:**

- **Complexity floor (SPEC §5 / DESIGN §5.3 G2):** minimum N steps required in a proposed spine; trivial single-branch rewrites are rejected outright.
- **Simplicity criterion:** reject diffs exceeding `complexity_budget_factor` (default 1.5×) net lines for a metric gain of < 5%.
- **Independent judge (DESIGN §5.3 G3):** a separate LLM instance from the proposer grades the diff; the judge is blind to the proposer's reasoning chain, catching self-reinforcing bias.
- **Secret-leak regex scan (G2 static check):** catches hardcoded API responses or fixture-exact outputs embedded in the spine.
- **Fixture diversity requirement:** every workflow must have at least one success-case fixture, one failure-case fixture, and at least one edge case discovered from production telemetry.

**Monitoring signal:** Acceptance rate > 90% over 20 consecutive rounds (difficulty floor too low); post-deployment failure rate on autolearn-modified workflows exceeds pre-autolearn baseline by more than 5%.

**Fallback:** `engram workflow autolearn --abort <name>` halts the run; `engram workflow rollback <name> --to=<rev>` restores the last known-good spine revision.

### 11.3 Pitfall 3 — Stale Cascade (Cross-Reference Rot)

**Trigger:** An upstream pool deletes or renames a memory asset referenced by 50+ downstream subscribers. The subscribers' `references:` frontmatter now dangles and their validation fails on the next sync.

**Symptom:** `engram validate` emits `W-REF-001` errors across many projects simultaneously immediately after the pool maintainer pushes a breaking revision.

**Root mitigation:**

- **Reference graph enforcement (SPEC §3.3 MUST 4 + DESIGN §3.2 `references_` table):** removal of a referenced asset is blocked at the CLI layer; the asset must transition through `deprecated → archived` lifecycle states before deletion is permitted.
- **Propagation `notify` mode (SPEC §9.3):** non-breaking changes (content updates) propagate silently to subscribers, but BREAKING changes (rename, removal, type change) require an explicit operator decision before propagating.
- **Warning cascade (DESIGN §5.2 Phase 1):** downstream validate emits `W-REF-001 reference-rot`; the operator sees the warning in `engram review`; the asset remains valid but flagged until resolved.

**Monitoring signal:** Surge in `W-REF-001` warnings across multiple projects within 24 hours of a pool revision; cross-project validation failure rate spike visible in the CI dashboard.

**Fallback:** Pool maintainer restores or renames the asset; subscriber `references:` entries auto-follow a rename if the pool asset carries a `supersedes:` link. For catastrophic breaking revisions: `engram pool rollback <name> --to=<prev-rev>` reverts the entire pool to a prior revision.

### 11.4 Pitfall 4 — Concurrent Write Corruption

**Trigger:** Two CLI invocations (or a CLI process, an MCP server process, and a web UI process) write to the same asset simultaneously. Non-atomic partial writes leave YAML frontmatter truncated or the graph database out of sync with the filesystem.

**Symptom:** Malformed YAML frontmatter (parse errors on next read); truncated asset files; `graph.db` index entries that no longer match the file content on disk.

**Root mitigation:**

- **Atomic rename pattern (DESIGN §3.1):** all writes follow write-to-tmp → fsync → rename; the rename is POSIX-atomic and guarantees readers always see complete files.
- **`fcntl` exclusive locks (DESIGN §3.8):** `.engram/.lock` is acquired for all mutating operations; a second process attempting to acquire the lock blocks rather than racing.
- **SQLite WAL mode (DESIGN §3.2):** `graph.db` allows concurrent readers and serializes writers via WAL; no manual locking is required for read paths.
- **Optimistic concurrency on asset writes:** the write path records the sha256 of the file as read; if the sha256 has changed by the time the write commits, the operation retries after a reload.
- **Journal append-only (invariant §8.1 #9):** the journal is never rewritten, only appended; it cannot be corrupted by concurrent writes.

**Monitoring signal:** Journal monotonic-counter discontinuities; `graph.db` integrity check failures (`PRAGMA integrity_check`); `engram validate` finds an asset whose file mtime post-dates the graph.db index entry by more than a clock-skew tolerance of 2 seconds.

**Fallback:** `engram graph rebuild` regenerates the full index from the filesystem (filesystem is authoritative); any ambiguity resolves to filesystem content. Last resort: `engram snapshot restore <snapshot-id>` to a prior backup snapshot.

### 11.5 Pitfall 5 — Circular Subscription

**Trigger:** Pool A subscribes to pool B for shared conventions; a maintainer later makes pool B subscribe to pool A for a different shared set. The subscription graph now contains a cycle.

**Symptom:** Infinite propagation loops; graph traversal during `engram pool sync` does not terminate; the sync daemon consumes 100% CPU until killed.

**Root mitigation:**

- **Cycle detection at subscribe time:** `engram pool subscribe` walks the would-be subscription graph depth-first before writing `pools.toml`; if a cycle is detected the command is rejected with `E-POOL-004 circular_subscription` and no change is written.
- **Graph integrity enforcement (DESIGN §3.2 subscriptions table):** a periodic integrity job asserts the DAG property on the subscriptions table; any cycle is an alarm-level alert.
- **Propagation iteration cap:** the propagation daemon refuses to process more than 10 hops in a single propagation chain, providing a hard backstop against bugs that bypass the DAG check.

**Monitoring signal:** Subscription graph depth > 5 hops typically indicates a design smell; the CLI emits a `W-POOL-002` warning at subscribe time when depth exceeds this threshold.

**Fallback:** `engram pool unsubscribe <pool>` on one participant breaks the cycle immediately; operator restructures pool hierarchy and re-subscribes in the correct direction.

### 11.6 Pitfall 6 — Embedding Drift

**Trigger:** The user upgrades the configured embedding model (e.g., `bge-reranker-v2-m3` → `v3`). Cached vectors produced by the old model are dimensionally or semantically incompatible with queries from the new model.

**Symptom:** Retrieval quality degrades silently; the Relevance Gate returns wrong or irrelevant assets for familiar queries; users do not notice for days because the degradation is gradual rather than a hard error.

**Root mitigation:**

- **Embedding model version stamp (DESIGN §3.3 `cache/embedding/version`):** a JSON file stores `{model_name, version, embed_date}`; every query operation checks for a match against the current config before using the cache.
- **Full cache rebuild on version mismatch:** a mismatch auto-triggers a background rebuild; progress is displayed in `engram review`; the old cache is preserved at `.bak` until the new one is complete and verified.
- **Per-asset sha256 re-embed check:** during a rebuild, only assets whose content sha256 has changed since the last index pass are re-embedded, minimising LLM provider cost.

**Monitoring signal:** Sudden drop in embedding cache hit rate after a configuration change; Relevance Gate reporting unusually low top-K cosine scores (below 0.4 average) on queries that previously scored above 0.7.

**Fallback:** `engram cache rebuild --embedding` forces a full regeneration from scratch. If the new model proves worse, `engram config set embedding.model=<prev>` followed by rebuild reverts to the prior model. Worst case: `engram config set embedding.enabled=false` disables the embedding cache entirely and falls back to BM25-only retrieval (Relevance Gate offline mode, §5.1.7).

### 11.7 Pitfall 7 — Privacy Leak via Cross-Scope Reference

**Trigger:** A private project memory references `pool/secret-rotation-schedule` (a team-internal pool asset containing sensitive operational data). The project repository is later made public. The reference text, or a rendered wiki-link, exposes the pool content.

**Symptom:** Sensitive content from a private pool leaks via wiki-link rendering in a public repository or public engram export.

**Root mitigation:**

- **Explicit cross-scope reference declaration (SPEC §3.3 MUST 3):** any `references:` entry that crosses scope boundaries must be declared in frontmatter; undeclared cross-scope references are caught by `engram validate` as `E-MEM-007`.
- **Cross-scope publish guard (DESIGN §9.6):** `engram pool publish` scans pool assets for `references:` pointing to `scope: project` or `scope: user` (private scopes) and refuses to publish unless `--allow-private-refs` is explicitly passed.
- **Project share guard:** `engram export --format=markdown` warns if the exported project contains references to team, org, or pool scopes that have not been cleared for sharing.

**Monitoring signal:** Any asset whose `references:` list crosses scope boundaries without an explicit `--allow-cross-scope` acknowledgement flag recorded in `graph.db`.

**Fallback:** Remove or redirect the cross-scope reference; if the referenced content is genuinely safe to share, update the source pool asset's scope to `public` and re-publish.

### 11.8 Pitfall 8 — LLM Hallucinated Subscription

**Trigger:** An LLM-authored memory asset writes "this project subscribes to pool kernel-work" in its body text. No such entry exists in `pools.toml`. Downstream LLM sessions read the body and believe the claim, expecting assets from that pool to be present.

**Symptom:** Memory bodies claim capabilities or pool memberships the project does not have; LLMs in subsequent sessions act on the claimed subscriptions; users see unexpected context injections or missing context depending on which claim the LLM believed.

**Root mitigation:**

- **Frontmatter-only subscription authority (SPEC §8.2):** pool subscriptions live exclusively in `pools.toml`; body text is not authoritative for subscription state and is never parsed for subscription claims.
- **Validation rule `E-MEM-008 phantom_subscription` (DESIGN §5.2):** `engram validate` scans memory bodies for patterns matching "subscribes to", "member of pool", and similar claims; cross-checks against `pools.toml`; emits an error if the claim does not match reality.
- **LLM authoring discipline (METHODOLOGY.md):** the LLM authoring guide explicitly teaches that pool membership claims belong only in `pools.toml`, never in body prose.
- **Review UI highlight:** `engram review` renders body text that references pool names in a distinct visual style, prompting the human reviewer to verify against actual subscriptions.

**Monitoring signal:** `E-MEM-008` hits in validate output; user-reported confusion about which pools are actually subscribed when asking the LLM about project context.

**Fallback:** If the claimed subscription was aspirational, run `engram pool subscribe <name>` to make it real. If it was erroneous, update the hallucinated memory body to remove the claim and run `engram validate` to confirm clean.

### 11.9 Cross-Cutting Defense Summary

Many pitfalls in this chapter share common underlying defenses that make the individual mitigations composable:

- **Journal-everything (invariant §8.1 #9):** all mutations are observable after the fact; enables forensic reconstruction for pitfalls 1, 4, and 8.
- **No-auto-mutate (invariant §8.1 #3):** intelligence layers propose; humans confirm; prevents pitfalls 2 and 8 from causing silent corruption.
- **Cross-process safety (invariant §8.1 #12):** locking + atomic rename + WAL; the mechanical foundation for pitfall 4.
- **Validation-first pipeline (§12):** every `engram` command that reads memory runs structural and semantic validation before acting; surface pitfalls 3, 5, 7, and 8 at the earliest possible moment.

Fixing one pitfall's defenses does not weaken another's because each defense operates on a different layer (filesystem, graph, validation rule, propagation daemon). Engineers adding new features should map them to this table and verify they do not introduce a new instance of any of the 8 patterns.

---

## 12. Comparison with Alternative Systems

### 12.0 Preamble

This section positions engram against eight alternative systems. The intent is engineering clarity, not marketing. Each competitor solves a well-defined slice of the memory/context problem; the comparison maps which slice, what their published constraints are, and where engram's design decisions differ.

Ground rules for this section:

1. Only published properties are cited. No claim of the form "engram is faster than X" without a benchmark. No claim of the form "X cannot do Y" without citing X's own documentation.
2. Where engram borrows from a competitor, that borrowing is named explicitly (§12.3).
3. Where engram diverges, the divergence is explained in terms of design goals, not superiority.
4. All competitor URLs and capability descriptions reflect publicly available information as of April 2026.

### 12.1 Comparison Table

The following table evaluates 8 systems across 13 dimensions. Cells are kept to ≤20 characters: ✅ = yes / implemented, ❌ = no / not implemented, "partial" = partially or with caveats, short qualifiers for specifics.

| Dimension | engram v0.2 | claude-mem | basic-memory | Karpathy LLM Wiki | mem0 | MemGPT / Letta | ChatGPT Memories | MemPalace |
|---|---|---|---|---|---|---|---|---|
| **Storage format** | Markdown + TOML | SQLite / ChromaDB | Markdown | Markdown (manual) | Hosted DB | Hosted / SQLite | Hosted (opaque) | Markdown |
| **Tool-agnostic** | ✅ | ❌ Claude only | ✅ | ✅ methodology | ❌ per-provider API | partial (LLM-as-OS) | ❌ ChatGPT only | partial |
| **Local-first** | ✅ | ✅ | ✅ | ✅ | ❌ cloud lock-in | partial | ❌ hosted | ✅ |
| **Scope / hierarchy** | ✅ 2-axis model | ❌ | ❌ single-tier | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Explicit enforcement** | ✅ mandatory/default/hint | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Consistency detection** | ✅ 7-class taxonomy | ❌ | ❌ | ❌ | partial (dedup) | partial (dedup) | partial (dedup) | ❌ |
| **Executable workflows (spine)** | ✅ | ❌ | ❌ | ❌ | ❌ | partial | ❌ | ❌ |
| **Knowledge Base (multi-chapter)** | ✅ | ❌ | partial (wiki-links) | ✅ methodology | ❌ | ❌ | ❌ | ❌ |
| **Web UI (first-class)** | ✅ | ❌ | ❌ | ❌ | ✅ hosted dashboard | partial | ✅ | ❌ |
| **MCP protocol server** | ✅ | partial | ❌ | ❌ | partial | ❌ | ❌ | partial |
| **Cross-repo inbox** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Quantified self-improvement** | ✅ 4 wisdom curves | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | partial (LongMemEval) |
| **Open source** | ✅ | ✅ | ✅ | ✅ (gist) | partial (SDK OSS) | ✅ | ❌ | ✅ |

**Caption:** engram is the only system in this table that is simultaneously local-first, tool-agnostic, multi-scope with explicit enforcement, and ships consistency detection + executable workflows + cross-repo collaboration as first-class primitives.

### 12.2 Per-System Short Assessment

**claude-mem** — Claude Code's native memory layer. Strengths: deep integration with Claude Code, working retrieval without user configuration, automatic memory capture during sessions. Limitations: Claude-only (no adapter for other LLMs or IDEs), SQLite/ChromaDB backend is opaque to tools outside Claude Code, no cross-project scope model, no consistency engine, no Workflow asset class. engram v0.2 is designed as a superset: engram's Claude Code adapter generates `CLAUDE.md` files that coexist with native Claude Code memory. Users can migrate via `engram migrate --from=claude-code` (SPEC §13.4).

**basic-memory** (github.com/basic-machines-co/basic-memory) — markdown-first memory with wiki-link graph navigation. Strengths: portable plain text, local-first, git-friendly, human-readable without tooling. Limitations: single-tier (no scope/enforcement model), no consistency engine, no Workflow asset class, single-user model with no cross-repo primitives. engram shares the portability ethos (all assets are readable markdown) and extends it with multi-tier scope, enforcement semantics, and intelligence layers.

**Karpathy LLM Wiki** — a methodology, not a product (published as a gist / talk). Strengths: demonstrates the compounding value of human-written, LLM-compiled knowledge; shows that structured curation beats raw retrieval over time. Limitations: no tooling; the operator maintains everything manually; no enforcement, consistency detection, or automated evolution. engram's KB asset class (SPEC §6, `_compiled.md` contract) directly productizes this idea with automated compilation tooling.

**mem0** (mem0.ai) — hosted agent memory service with embedding + knowledge-graph retrieval. Strengths: zero setup, strong retrieval via hybrid embedding + graph, per-user memory isolation. Limitations: cloud lock-in (users don't own the data), pricing scales with usage, per-provider API (not tool-agnostic at the storage layer). engram is the local-first alternative for teams that require data ownership. Users can import via `engram migrate --from=mem0`.

**MemGPT / Letta** (letta.com) — treats memory as OS virtual memory; pages information between context window and external storage using an LLM-as-OS abstraction. Strengths: elegant tiering metaphor handles long contexts well; clear paging contract. Limitations: tied to the Letta runtime (LLM-as-OS framework); no multi-scope model; no Consistency Engine; no Workflow asset class; external storage is not filesystem-native markdown. engram draws the L0–L3 tiering metaphor from MemGPT (DESIGN §5.1) but keeps all assets as filesystem-native markdown files accessible without the runtime.

**ChatGPT Memories** — OpenAI-provided personal memory for ChatGPT sessions. Strengths: seamless integration in the ChatGPT UI, zero configuration for users. Limitations: ChatGPT-only (not tool-agnostic), hosted with no export pathway, users cannot inspect or version their memories, no scope/enforcement/consistency model. engram is the open, portable counterpart for users who need data ownership and cross-tool portability.

**MemPalace** (github.com/MemPalace/mempalace) — verbatim conversation storage with Zettelkasten structure and Claude Code hooks integration. Strengths: 96.6% R@5 on LongMemEval (per published BENCHMARKS.md), local-first, Claude Code hooks, git-diffable storage, hybrid retrieval combining BM25 + vector + temporal signals + two-pass reranking. Limitations: optimized for verbatim transcript storage, not curated structured knowledge; no Workflow asset class; no multi-scope enforcement; no cross-repo inbox; single-scope model. engram directly adopts MemPalace's hybrid retrieval algorithm (Amendment B §B.2, DESIGN §5.1) and its BENCHMARKS.md measurement discipline, and addresses the structured-knowledge + multi-scope + enforcement gap that MemPalace does not target.

### 12.3 What engram Borrows from Each

| Source | engram borrows | Where in engram |
|---|---|---|
| Karpathy LLM Wiki | Human-written + LLM-compiled KB pattern; curation > raw retrieval principle | SPEC §6 |
| autoresearch (Karpathy) | Ratchet loop + 8 disciplines for workflow evolution | DESIGN §5.3 |
| Agent Factory | Workflow = doc + executable spine (experience as code) | SPEC §5, DESIGN §5.3 |
| evo-memory | Search→Synthesize→Evolve lifecycle; ReMem action-think-refine loop | DESIGN §5.4 |
| MemoryBank | Ebbinghaus-inspired confidence decay (evidence-driven forgetting curve) | SPEC §4.8, §11 |
| MemGPT / Letta | Memory tiering metaphor (L0–L3 wake-up stack) | SPEC §7, DESIGN §5.1 |
| claude-mem (Claude Code memory) | Direct predecessor; subtype + frontmatter pattern; session memory capture | SPEC §4 |
| MemPalace | Hybrid retrieval (BM25 + vector + temporal + two-pass rerank); BENCHMARKS.md discipline | DESIGN §5.1, benchmarks/ |
| Darwin.skill | Autolearn ratchet (git-native) + dual eval + independent judge + phase gate | DESIGN §5.3 |
| Nuwa.skill | `limitations:` frontmatter field (honest boundary declaration) | SPEC §4 |
| `npx skills add` convention | Playbook install URL scheme | SPEC §4, DESIGN §6 |

All 11 borrowings above are acknowledged rather than implicit. Where engram's implementation diverges from the source (e.g., MemPalace's retrieval is adapted to engram's multi-scope graph rather than a flat index), the divergence is documented in the referenced section.

### 12.4 What engram Uniquely Adds

The following features are not found, individually or in combination, in any of the eight systems assessed in §12.1:

1. **Two-axis scope model** — membership hierarchy (user → project → team → org) combined with orthogonal pool subscription — SPEC §8. No assessed system implements both axes simultaneously.
2. **Explicit `enforcement` semantics with deterministic conflict resolution** — mandatory/default/hint levels with a defined precedence order and override audit trail — SPEC §8.3–8.4.
3. **Three distinct asset classes** (Memory / Workflow / Knowledge Base) with separate formats, lifecycle rules, and authorship models — SPEC §3. Competitors (including claude-mem and basic-memory) treat all stored content as undifferentiated memory.
4. **Seven-class consistency taxonomy** — seven named contradiction/staleness types with a "suggest, never mutate" contract — SPEC §11.
5. **Cross-repo Inbox** — point-to-point agent collaboration across repository boundaries with priority ordering and structured acknowledgement — SPEC §10.
6. **Quantified self-improvement** — four wisdom curves (Memory Health Score, Workflow Fitness, KB Freshness, Scope Coherence) with automated regression detection — DESIGN §5.6.
7. **First-class observation layer** — Web UI with Context Preview debug page for human inspection of what the LLM will see before a session — DESIGN §7.

The combination of these seven properties makes engram the first system in this comparison that is simultaneously portable (all assets are plain markdown, no runtime lock-in), intelligent (consistency engine + autolearn + evolve pipeline), and multi-scope (two-axis membership + subscription with explicit enforcement).

---

## 13. Non-MVP Scope Boundaries

### 13.0 Purpose

This chapter explicitly catalogues what IS in v0.2 and what is NOT. It removes ambiguity for implementers who must decide whether a feature belongs in the v0.2 milestone and for users who expect a clear promise about what ships. Items are grouped into four tiers:

- **P0** — Must ship at the v0.2.0 tag. Work not done here is a release blocker.
- **P1** — Targeted for the first post-release wave (v0.2.1 through v0.3.0). Fully planned; not release-blocking.
- **P2** — Future consideration. Listed to avoid re-inventing them later; no milestone commitment.
- **Non-goals** — Permanently out of scope by design. These are intentional exclusions, not backlog items.

### 13.1 P0 — v0.2 Open-Source Release (M1–M7 Milestones)

The following components must be complete and tested before the v0.2.0 tag is cut.

| Component | Scope | Chapter |
|---|---|---|
| Layer 1 Data format | Full SPEC §1–§14 compliance | SPEC |
| Layer 2 CLI core | `init / status / version / config / review / validate / migrate --from=v0.1 / memory (full) / pool (subscribe/publish/sync/list/unsubscribe) / team (full) / org (full) / inbox (full) / context pack/preview / graph rebuild / cache rebuild / archive list/restore / snapshot create/list/restore / export` | §4 |
| Layer 3 Intelligence — partial | Relevance Gate full; Consistency Engine Phase 1 (static) + Phase 2 (semantic cluster); Inter-Repo Messenger full | §5 |
| Layer 4 Access | Claude Code + Codex + Gemini CLI + Cursor + raw-api adapters; MCP server with read + inbox tools; prompt pack; Python SDK base | §6 |
| Layer 5 Observation — subset | Web UI pages: Dashboard, Memory Detail, Workflow Detail (view only), KB Article (read only), Inbox, Context Preview — 6 of 11 pages | §7 |
| Benchmarks | `benchmarks/consistency_test/` + `benchmarks/scope_isolation_test/` self-built suites | Amendment B §B.3 |

All P0 items map to milestones M1 through M7 in `TASKS.md`. An item is done when its unit tests pass, its integration tests pass, and it appears in the CLI `--help` output or is accessible through the MCP server as documented in §6.

### 13.2 P1 — v0.2 Post-Release First Wave (M5–M8 After MVP)

These features are fully designed and will be targeted in the first post-release development cycle. They are not blocking v0.2.0 but are expected to land before v0.3.0.

| Component | Scope | Chapter |
|---|---|---|
| Workflow asset + Autolearn Engine | Full spine execution + Darwin ratchet + phase gate + independent judge | §5, DESIGN §5.3 |
| Knowledge Base + compile | Full `_compiled.md` generation + staleness detection | §6, DESIGN §6.2 |
| Consistency Engine Phase 3 | LLM-assisted review (optional, opt-in per config) | DESIGN §5.2 |
| Consistency Engine Phase 4 | Fixture execution verification for workflows | DESIGN §5.2 |
| Evolve Engine | ReMem loop for memory asset refinement proposals | DESIGN §5.4 |
| Pool propagation full | notify + pinned modes beyond auto-sync | SPEC §9, DESIGN §5.2 |
| Web UI remaining 5 pages | Graph (D3 force layout), Pools, Project Overview, Wisdom, Autolearn Console | §7 |
| TypeScript SDK | `@engram/sdk` mirror of Python SDK | §6 |
| Wisdom Metrics dashboard | Full 4 curves + regression alerts | DESIGN §5.6 |
| Additional migrate sources | chatgpt, mem0, obsidian, letta, mempalace, markdown | SPEC §13.6 |
| Playbook pack/install | `engram playbook` command family | SPEC §4, DESIGN §6 |

P1 items are tracked on the `v0.3.0` milestone in `TASKS.md`. Design for each is stable; implementation begins after v0.2.0 is tagged. No P1 item requires a spec change — all formats and contracts are defined in SPEC.md.

### 13.3 P2 — Future Consideration (No Milestone Yet)

The following ideas are worth recording to avoid duplicating design effort when they come up. They are not committed to any release and may be superseded or dropped. Adding a P2 item does not imply it will ever ship.

- **Multi-machine sync daemon** — cross-device sync for `~/.engram/user/` beyond rsync/git (possibly CRDT-based). The current design assumes a single primary machine; multi-machine use is supported only via manual git sync.
- **Local small-model reranker** — optional LLM-based rerank step in Relevance Gate using an on-device model (currently cross-encoder only). Would improve retrieval quality without a cloud round-trip but requires hardware profiling.
- **Obsidian plugin** — first-party plugin to edit `.memory/` from Obsidian with live validation. The on-disk format is already Obsidian-compatible; this is a UI-layer addition.
- **IDE deep integration** — VS Code extension for inline Memory authoring + consistency alerts in the editor gutter. Lower priority than CLI and Web UI.
- **Multilingual embeddings** — non-English embedding models for better non-English Memory retrieval. The embedding model is pluggable (see §5.1); this is a configuration and documentation task.
- **Collaborative editing** — structured merging when two humans + two agents edit the same asset nearly simultaneously. v0.2 assumes single-writer at a time; conflicts escalate to human via the Consistency Engine. Full OT or CRDT merging is a separate project.
- **Runtime consistency enforcement** — intercept LLM actions in real time (not just post-hoc) to block outputs that violate active `enforcement=mandatory` rules. Requires a proxy or hook layer that does not exist in v0.2.
- **Federated pools** — a pool registry service for discovering community pools beyond raw GitHub URL install. Requires a trusted registry infrastructure outside the scope of the local-first design.

### 13.4 Non-Goals — Explicitly Out of Scope Forever

These are design-intentional exclusions. They will not be added to any backlog. If a contributor proposes one of these in a PR, the response is a link to this section, not a "maybe later."

- **Cloud/SaaS service.** engram is local-first. We will not build a hosted engram where users store their data on Anthropic's or any third-party servers. If someone else builds that on top of the open format, that is their project — but it is not this one.
- **Mobile app.** The current Web UI targets desktop browsers. No native mobile app. Read-only browsing from a mobile browser may work incidentally but is not a supported target and will not receive mobile-specific design investment.
- **Proprietary model bundling.** engram does not ship with or require any specific LLM. The Relevance Gate uses local embedding models (bge-reranker-v2-m3 default) — those are optional and user-replaceable. We will not package or redistribute any proprietary model weights.
- **Automatic runtime code generation.** engram does not generate or modify LLM inference code. Workflows use spines that operators author (or that Autolearn evolves from an operator-authored baseline); we do not ship LLM-side automation that produces executable code without a human in the loop.
- **Cross-repo lock manager.** Inbox is message-based (async, best-effort). We do not guarantee distributed locks or consistent ordering across repositories. Distributed coordination is the responsibility of the operator; use git or external coordination primitives for that.
- **Real-time operational transformation.** Two users editing the same Memory asset simultaneously is rare enough that we use filesystem atomic rename + optimistic concurrency + conflict escalation to human. We will not add CRDTs or OT for Memory content. The complexity is not justified by the use case frequency.
- **Auto-resolution of Consistency proposals.** The Consistency Engine's invariant is "suggest, never mutate" (DESIGN §5.2, SPEC §11). Automating resolution would violate this contract and break user trust in the system. No exceptions, even for clearly safe cases.
- **Gamification.** No streaks, no XP, no quests, no leaderboards. Wisdom Metrics exist to provide signal about system health, not to drive engagement. Adding engagement mechanics would corrupt the signal and contradict the design's premise that humans are the authors, not players.

---

**DESIGN v0.2 draft complete.** Chapters §0 through §13 cover the full 5-layer architecture, intelligence layer contracts, access paths, observation layer, source layout, testing, pitfalls, and scope boundaries. Companion documents:

- [`SPEC.md`](SPEC.md) — on-disk format contract (v0.2 complete)
- [`METHODOLOGY.md`](METHODOLOGY.md) — how LLMs should write memory (pending)
- [`TASKS.md`](TASKS.md) — milestone and task board (pending)
- [`docs/glossary.md`](docs/glossary.md) — authoritative terms

Design changes after this draft go through PR + design review at the GitHub Discussions page.
