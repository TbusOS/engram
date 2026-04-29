[English](README.md) · [中文](README.zh.md)

# engram

> **engram** *(/ˈenɡram/, noun)* — a physical trace of memory left in the brain.
> In this project: a local, portable, LLM-agnostic memory system that grows smarter with use.

**Status:** v0.2 design rewrite in progress — see [the implementation plan](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md). v0.1 is archived at [`docs/archive/v0.1/`](docs/archive/v0.1/).

---

## What engram is

Most LLM tools try to own your memory. Claude Code has its own memory. ChatGPT has "Memories". mem0, Letta, MemGPT pull your data into their storage. Switch models, lose context. Switch tools, re-teach from scratch.

**engram is the opposite design.** Memory lives as plain markdown files on your disk, in a format any LLM can read without a plugin. Tools come and go. Your memory stays. And the longer you use it, the smarter it gets — because engram actively maintains quality rather than just storing what you dump in.

## Goal: the best open-source permanent memory system

engram targets five things none of the existing systems (claude-mem, basic-memory, Karpathy's LLM Wiki, mem0, MemGPT, Letta, ChatGPT Memories) do *all* of:

1. **LLM-first, tool-agnostic** — any model, local or cloud, reads `.memory/` the same way
2. **Human-observable** — first-class web UI to see the full knowledge graph, evolution, and what any LLM would actually load for a given task
3. **Team / org / pool sharing without pollution** — two-axis scope (a 4-level membership hierarchy plus orthogonal topic pools) with explicit `enforcement` (mandatory / default / hint); updates propagate to subscribers, noise never crosses boundaries
4. **Three asset classes, not just Memory** — short Memory for LLM priming, medium Workflow (doc + executable spine + fixtures) for procedural knowledge, long Knowledge Base (human-written, LLM-compiled digest) for domain references
5. **Measurably gets smarter** — four quantitative "wisdom" curves (workflow mastery, task recurrence efficiency, memory curation ratio, context efficiency) proving the system learns, not just remembers

**No hard capacity cap.** Quality maintained by a **Consistency Engine** that detects seven classes of conflicts (factual / rule / reference-rot / workflow-decay / time-expired / silent-override / topic-divergence) across your entire store and suggests — never auto-executes — updates, merges, supersessions, and archives.

## Five-layer architecture

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
│           (plain markdown)    SPEC-compliant; any LLM can read it        │
└──────────────────────────────────────────────────────────────────────────┘
```

Each layer is independently replaceable. Remove Layer 5, you still have a working CLI. Disable Layer 3 intelligence, the system still behaves correctly (just doesn't self-improve). Uninstall the CLI entirely, the markdown store remains readable by hand, by LLMs, by Obsidian, and by anything that understands markdown.

## Three asset classes

Classes are distinguished by **function** — what the asset *is* — not by size. No hard line limits. The system uses adaptive signals (see below) instead of fixed thresholds.

| Class | What it is | Required structure | Role in LLM context |
|-------|-----------|-------------------|---------------------|
| **Memory** | An **atomic assertion** — one fact / rule / preference / pointer that can be independently superseded | A single `.md` with frontmatter + body | loaded into system prompt via Relevance Gate |
| **Workflow** | An **executable procedure** — has a spine that actually runs | `workflow.md` + `spine.*` + `fixtures/` + `metrics.yaml` + `rev/` | loaded on task match; autolearn evolves it over time |
| **Knowledge Base** | A **domain reference** — multi-chapter document a human would read deliberately | `README.md` + chapter sections + `assets/` + `_compiled.md` (LLM-generated digest) | retrieved on demand; `_compiled.md` enters budget first |

**No size caps.** Three adaptive signals replace fixed thresholds:

- **Dynamic budget allocation** — Relevance Gate shifts per-type token budget based on observed utilization
- **Percentile length signal** — assets in the top 5% of length (within their type) get a *review suggestion* in `engram review` — never a warning or hard block
- **Split / promote / demote proposals** — the Evolve Engine proposes splitting dense memories, promoting memory clusters to KB articles, demoting unused workflows to memory, and promoting procedural memories to workflows — all as suggestions, never auto-executed

A new project doesn't start from zero — it subscribes to the pools (shared knowledge) it needs, instantly inheriting proven workflows and references:

```bash
engram init --org=acme --team=bsp --subscribe=kernel-work,android-bsp
```

## Scope: two axes, not one line

Real teams share knowledge in more than one way. engram separates these into two independent axes:

### Hierarchy (membership — you belong, you inherit)

```
org      ~/.engram/org/<name>/       company / organization rules (highest authority)
team     ~/.engram/team/<name>/      team or department conventions
user     ~/.engram/user/             this user's cross-project baseline
project  <project>/.memory/local/    this project only (most specific)
```

You belong to 0 or 1 org, 0 or N teams, you're always you, you work in N projects. Everything up the chain is inherited automatically. Most specific wins (within the same `enforcement` level).

### Subscription (pool — you opt in)

```
pool     ~/.engram/pools/<name>/     topic-shared knowledge, explicitly subscribed
```

Pools are **orthogonal** to the hierarchy. A pool is subscribed *at* a hierarchy level — declared in `pools.toml` as `subscribed_at: org | team | user | project`. The pool's content then behaves as that level of authority for that subscriber.

Examples:
- Your **org** subscribes to `pool: compliance-checklists` → all projects in the org see it as org-level mandatory
- Your **platform team** subscribes to `pool: design-system` → all projects in the team inherit it at team level
- **You personally** subscribe to `pool: my-dotfiles-notes` → only your own projects see it
- A single **project** subscribes to `pool: acme-checkout-service-playbooks` → only that project uses it

### Enforcement

Every rule declares how strict it is:

- `mandatory` — cannot be overridden by a lower scope; `engram validate` errors
- `default` — can be overridden, but the override must declare `overrides: <id>`
- `hint` — freely overridable

### Conflict resolution (one decision tree)

1. `mandatory` beats `default` beats `hint`
2. Within the same enforcement, **more specific wins**: `project > user > team > org`
3. Pool content participates at its `subscribed_at` level
4. If still tied, the LLM arbitrates with context present and `engram review` flags a warning

## Cross-repo collaboration

Your agents often work on multiple related repos in parallel — e.g., repo A uses repo B's SDK. When agent A notices a bug or awkward API in B, it can send a structured message to B's inbox:

```bash
engram inbox send --to=repo-b \
  --intent=api-change \
  --message="Your read_config() silently returns {} on missing file — should raise." \
  --code-ref="libb/config.py:L42@abc123"
```

Next time repo B's LLM starts a session, it sees the pending message alongside its own memory. When it's fixed, the sender gets notified on their next startup. All messages are journaled, deduplicated (by `code-ref`), and rate-limited to prevent noise.

## Why markdown (and not a vector database)

- **Any LLM can read it** — no SDK, no parser, no embeddings required to get started
- **Any human can edit it** — Obsidian, Logseq, vim, VS Code all work today
- **Git-friendly** — diffs are readable, teams share via `git push`
- **Survives engram itself** — if this project vanished tomorrow, your store is still a legible set of markdown notes

engram uses embeddings (locally, via `bge-reranker-v2-m3`) for the Relevance Gate, but embeddings are a **cache**, not the source of truth. The markdown files are always canonical.

## Differentiators (at a glance)

| | engram v0.2 | claude-mem | basic-memory | Karpathy Wiki | mem0 | MemGPT / Letta | ChatGPT Mem |
|---|---|---|---|---|---|---|---|
| Plain markdown storage | ✅ | SQLite | ✅ | ✅ | hosted | internal | hosted |
| Tool-agnostic | ✅ | Claude only | mostly | mostly | mostly | SDK-coupled | ChatGPT only |
| Hierarchy + pool scope | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Explicit `enforcement` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Consistency detection (7 classes) | ✅ | partial | ❌ | ❌ | ❌ | ❌ | ❌ |
| Executable workflows | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Knowledge Base class | ✅ | ❌ | partial | ✅ | ❌ | ❌ | ❌ |
| First-class Web UI | ✅ | ❌ | ❌ | ❌ | partial | partial | ✅ |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cross-repo inbox | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Quantified self-improvement | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Open source | ✅ | ✅ | ✅ | ✅ | partial | ✅ | ❌ |

## Philosophy

Five principles, non-negotiable:

1. **Your memory is a data asset, not a product feature.** Own it.
2. **Portability beats cleverness.** Boring markdown wins decade-scale bets.
3. **Quality over capacity.** No cap on how much you store; strict bar on how good it is. The Consistency Engine keeps the store coherent as it grows.
4. **Never auto-delete.** Deletions go through `archive/` with ≥ 6-month retention. Mistakes are recoverable.
5. **Evidence-driven evolution.** Memory confidence is computed from recorded outcomes, not vibes. The system retires bad memories because it has *data* that they're bad.

## Quick start (v0.2 — M2 / M3 / M4 implemented; M4.6 sprint underway)

```bash
# Install
pip install engram-cli   # editable install: cd cli && pip install -e ".[dev]"

# Just want to record one thing? Zero-config one-liner:
engram memory quick "kinit before ssh to build.acme.internal"

# In any project directory — small team, minimal setup
engram init --subscribe=kernel-work --adapter=claude-code,codex

# Cloned a teammate's engram-managed repo? Just init — adopt is the default.
git clone <repo-with-existing-memory> && cd repo
engram init                    # adopts existing .memory/, never overwrites MEMORY.md

# Large organization — full hierarchy
engram init --org=acme --team=platform \
  --subscribe=compliance-checklists,kernel-work,design-system \
  --adapter=claude-code,codex,gemini

# Generates:
#   .memory/MEMORY.md                        — landing index (LLM reads first)
#   .memory/local/                           — project-scope assets
#   .memory/pools/<name>/ → ~/.engram/...    — subscribed pool symlinks
#   .memory/workflows/<name>/                — project-owned workflows
#   .memory/kb/<topic>/                      — project-owned knowledge base
#   .memory/pools.toml                       — subscription config (subscribed_at)
#   CLAUDE.md, AGENTS.md, GEMINI.md          — adapter prompt templates

# Use any LLM — the store is canonical
claude                   # reads CLAUDE.md → reads .memory/
codex                    # reads AGENTS.md → reads .memory/
engram mcp serve         # for Claude Desktop, Zed, any MCP client
engram context pack --task="fix checkout flow smoke test" --budget=4k | ollama run qwen:7b

# Observe and maintain
engram web serve         # open the dashboard at http://127.0.0.1:8787
engram consistency scan  # detect conflicts, suggest resolutions
engram review            # aggregate health check
engram wisdom report     # see the four self-improvement curves
```

**Command details?** See [`SPEC.md`](SPEC.md) and [`DESIGN.md`](DESIGN.md) once they're written for v0.2 (in progress — track [the plan](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md)).

## Commands

The complete list of CLI subcommands, with their current implementation
status. **Implemented** commands are usable today; **Planned** commands
appear in `engram --help` only after their tracking task lands. New users:
do not run a planned command and assume it works — check the table.

### Implemented (M2 – M4 complete)

| Command | Purpose | Tracking |
|---|---|---|
| `engram init` | Initialize project `.memory/` + `.engram/`. Defaults to **adopt** mode when `.memory/` already exists (registers existing assets without overwriting `MEMORY.md`). | T-17, **T-161** |
| `engram init --adopt` | Explicit adopt: register an existing `.memory/` into graph.db; never touches markdown. Use after `git clone` of a teammate's engram-managed repo. | **T-161** |
| `engram init --force` | Regenerate the skeleton (overwrites `MEMORY.md` / `pools.toml`). Legacy escape hatch. | T-17 |
| `engram memory add` | Create a memory asset from full flags (`--type --name --description --body` + optional fields). | T-19 |
| `engram memory quick "<body>"` | One-line capture: name + description auto-derived from body, type defaults to `project`. Made for LLM agents and quick human notes. | **T-160** |
| `engram memory list / read / update / archive / search` | Full CRUD + BM25 search over project-scope memories. | T-19, T-38 |
| `engram validate` | Frontmatter / enforcement / reference / pool integrity check (exit codes per SPEC §12.13). | T-20, T-37 |
| `engram review` | Aggregated health report: percentile length signal, low-confidence assets, expired items. | T-21 |
| `engram status` | Project scope + pool subscription + graph.db summary. | T-22 |
| `engram pool subscribe / unsubscribe / list / sync / pull` | Pool subscription + git sync (auto-sync mode). | T-30 ~ T-32 |
| `engram team join / sync / publish / status / list` | Team-scope git repo management. | T-33 |
| `engram org join / sync / publish / status / list` | Org-scope git repo management. | T-33 |
| `engram migrate --from=v0.1` | v0.1 → v0.2 store migration with backup + rollback + journal. | T-34, T-35 |
| `engram config get / set / list` | CLI configuration (TOML, atomic writes). | T-18 |
| `engram version` | Print engram-cli version. | T-18 |
| `engram context pack --task=<text>` | Drive the Relevance Gate from the CLI; output prompt / json / markdown. Pipe directly to local LLMs. | T-56 |
| `engram consistency scan` | 4-phase Consistency Engine (Phase 1 + 2 active; Phase 3 + 4 stub). | T-46 (T-47 / T-48 in M4.6) |
| `engram consistency apply` | Apply a consistency proposal (default dry-run; `--consent` required to touch disk). | T-49 |
| `engram inbox send / list / acknowledge / resolve / reject` | Cross-repo Inter-Repo Messenger (SPEC §10). | T-50 |
| `engram mcp serve` | Stateless MCP server over stdio JSON-RPC (works with Claude Code / Claude Desktop / Cursor / Zed / Codex / Opencode / VS Code). | T-51, T-52 |
| `engram mcp install --target=<client>` | One-line MCP config install for 9 clients (claude-desktop / claude-code / cursor / zed / codex / opencode / vscode-{continue,cline,copilot}). `write` mode merges JSON; `paste` mode prints snippet. | **T-163** |
| `engram adapter list / install / refresh` | Generate or refresh `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.cursor/rules/engram.mdc` / `ENGRAM_PROMPT.md` with marker-bounded blocks. | T-53 ~ T-55 |
| `engram doctor` | One-shot store health check: layout / graph.db drift / index reachability / pool sync / mandatory budget. Every issue ends with `→ run: <fix command>`. | **T-162** |
| `engram wisdom report` | 6 wisdom curves (C1 retrieval hit rate / C2 task recurrence / C3 write friction / C4 mandatory false-positive / C5 redundancy / C6 confidence calibration) rendered as Unicode-block sparklines from `~/.engram/journal/usage.jsonl`. | **T-188** |
| `engram observe --session=<id> --client=<client>` | Append a tool-use event to the observer queue (`~/.engram/observe-queue/<session>.jsonl`). Stage 0 of the auto session continuation pipeline. p99 < 50 ms; queue-full is non-fatal. Reads JSON from stdin or `--event`. Optional `--from=<client>` translator. | **T-200** |
| `engram observer install --target=<client>` | One-line install of observer hooks for 5 clients (claude-code → write to `~/.claude/settings.json`; codex / cursor / gemini-cli / opencode → paste mode). `--list` enumerates targets; `--dry-run` previews the change. | **T-205** |
| `engram distill review / promote / reject` | Consent gate for Tier 2 distilled candidates. `review` lists `*.proposed.md` under `.memory/distilled/`; `promote <name>` moves a candidate into `.memory/local/<name>.md` and back-links to source sessions; `reject <name>` archives under `~/.engram/archive/distilled/<YYYY-MM>/`. Both LLM and human can invoke. | **T-209** |
| `engram propose review / promote / reject` | Consent gate for Tier 3 procedural proposals. `review` lists `workflows/<slug>/proposal.md`; `promote <name>` upgrades into a real Workflow scaffold (`README.md` + `spine.toml` placeholder + `metrics.yaml` + `fixtures/`); `reject <name>` archives the directory under `~/.engram/archive/workflows/<YYYY-MM>/`. | **T-210** |

### Planned (M4.6 – M8)

See [`docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md`](docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md) for the full M4.6 12-week plan.

| Command | Purpose | Tracking |
|---|---|---|
| `engram pool accept <name>` / `engram pool diff <name>` | notify-mode pool review: accept the latest revision after diff, instead of auto-applying. | T-183 |
| `engram graph rebuild --recompute-confidence` | Rebuild graph.db from `~/.engram/journal/usage.jsonl` event log. | T-185 |
| `engram migrate --from=v0.2` | In-place migration to v0.2.1 SPEC-AMEND (adds `primary_topic`, `directive`, derived `confidence` cache, `accepted_revision`). | T-186 |
| `engram workflow add / run / revise / promote / rollback / list / test` | Workflow asset full lifecycle. | T-70 ~ T-79 |
| `engram workflow autolearn <name>` | Darwin-ratchet autolearn loop with phase gate. | T-79 |
| `engram workflow evolve <name> --variants=N` | Fork-and-evaluate variants, top-1 → `rev/proposed`. | T-191 |
| `engram autolearn run --duration=Nh` | Bounded background daemon: continuous evolve + consistency + wisdom recompute within a time window. | T-193 |
| `engram kb new-article / compile / list / read` | Knowledge Base authoring + LLM-compiled `_compiled.md`. | T-90 ~ T-92 |
| `engram playbook install / publish / list / uninstall` | Installable Workflow + KB + seed Memory bundles via GitHub URL. | T-141 |
| `engram web serve / open` | Browser dashboard on `http://127.0.0.1:8787` (P0 pages: Dashboard / Memory / Workflow / KB / Inbox / Context Preview). | T-110 ~ T-123 |
| `engram migrate --from={chatgpt,mem0,obsidian,letta,mempalace,markdown}` | External system import. | T-140 |

## Migrating from other systems

```bash
engram migrate --from=v0.1        # engram v0.1
engram migrate --from=claude-code # ~/.claude/projects/.../memory/
engram migrate --from=chatgpt     # ChatGPT Memory export JSON
engram migrate --from=mem0        # mem0 db export
engram migrate --from=obsidian    # Obsidian daily notes / specific folder
engram migrate --from=letta       # Letta / MemGPT archival
```

## Project layout

```
engram/
├── README.md / README.zh.md               # you are here
├── SPEC.md / SPEC.zh.md                   # v0.2 data format spec (in progress)
├── DESIGN.md / DESIGN.zh.md               # v0.2 5-layer implementation design (in progress)
├── METHODOLOGY.md / METHODOLOGY.zh.md     # how LLMs should write memory (in progress)
├── TASKS.md / TASKS.zh.md                 # live milestone board (in progress)
├── CONTRIBUTING.md / CONTRIBUTING.zh.md
├── docs/
│   ├── glossary.md / glossary.zh.md       # bilingual term anchor
│   ├── archive/v0.1/                      # the earlier 3-layer design (frozen)
│   └── superpowers/plans/                 # execution plans
├── cli/                                   # Python CLI (M2–M4)
├── web/                                   # FastAPI + Svelte Web UI (M7)
├── sdk-ts/                                # TypeScript SDK
├── adapters/                              # tool-specific prompt templates
├── seeds/                                 # init seeds
├── playbooks/                             # installable workflow bundles
└── tests/
```

## Inspiration

engram stands on ideas from several projects and papers. Each shaped a specific piece:

- [**Karpathy — LLM Wiki as a personal knowledge base**](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — write-side synthesis, compounding artifact (Knowledge Base class)
- [**autoresearch**](https://github.com/karpathy/autoresearch) (Karpathy) — 8-discipline agentic optimization loop (Autolearn Engine)
- **Agent Factory** (2026-03 arXiv) — *experience as executable code, not text* (Workflow class with spine)
- **evo-memory** (DeepMind 2025) — Search → Synthesize → Evolve life cycle, ReMem action-think-refine (Evolve Engine)
- [**MemoryBank**](https://arxiv.org/abs/2305.10250) — Ebbinghaus-curve inspiration, adapted to confidence-driven retention instead of time-based decay
- [**MemGPT / Letta**](https://github.com/cpacker/MemGPT) — memory as OS virtual memory (inspired the tiered Layer 1 thinking)
- **The Claude Code memory system** — the direct precursor this project generalizes

## Community

- **Discussions** — design review, Q&A, use-case sharing: https://github.com/TbusOS/engram/discussions
- **Issues** — bug reports, feature requests: https://github.com/TbusOS/engram/issues
- **Landing site** — https://TbusOS.github.io/engram/
- **Web UI preview** — https://TbusOS.github.io/engram/design/
- **Contributing**: see [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **v0.2 implementation plan**: [`docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md`](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md)

## License

MIT.
