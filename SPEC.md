[English](SPEC.md) · [中文](SPEC.zh.md)

# engram Memory System Specification

**Version**: 0.2 (draft)
**Status**: Open for comment
**Last updated**: 2026-04-18
**Canonical**: https://github.com/TbusOS/engram/blob/main/SPEC.md
**Glossary**: [docs/glossary.md](docs/glossary.md) — terms in this doc follow that table

---

<!-- engram glossary lock: all terms in this document must match docs/glossary.md -->

## 0. Purpose

engram v0.2 is a local, portable, LLM-agnostic memory system designed to be **the best open-source permanent memory system** for anyone building with large language models. The version number is a statement of direction: every design decision in this document exists to close the gap between what the ecosystem has today and what a serious memory system ought to be.

Existing systems — claude-mem, basic-memory, Karpathy's LLM Wiki, mem0, MemGPT, Letta, ChatGPT Memories — each solve a slice of the problem. None of them solve all five of the following together:

1. **LLM-first, tool-agnostic.** Any model, local or cloud, reads the `.memory/` directory the same way. No proprietary SDK, no hosted endpoint, no lock-in.
2. **Human-observable.** A first-class Web UI lets you see the full knowledge graph, the evolution of every asset over time, and exactly what any LLM would load for a given task before it loads it.
3. **Team and org sharing without pollution.** A two-axis scope model (a four-level membership hierarchy plus orthogonal topic pools) with explicit `enforcement` semantics (`mandatory` / `default` / `hint`) lets knowledge flow where it belongs and stop where it should not.
4. **Three asset classes, not just Memory.** Short Memory files for LLM priming; medium Workflow assets (doc + executable spine + fixtures + metrics + revision history) for procedural knowledge; long Knowledge Base articles (human-written, LLM-compiled digest) for domain references. Each class has a distinct format, lifecycle, and loading path.
5. **Measurably gets smarter.** Four quantitative Wisdom Metrics curves (workflow mastery, task recurrence efficiency, memory curation ratio, context efficiency) provide evidence that the store self-improves rather than simply accumulating.

Quality is maintained not by imposing a capacity ceiling but by a **Consistency Engine** that detects seven classes of conflict — `factual-conflict`, `rule-conflict`, `reference-rot`, `workflow-decay`, `time-expired`, `silent-override`, and `topic-divergence` — across the entire store and proposes, never auto-executes, remediation. Deletions never happen silently; they flow through an `archive/` path with a retention floor of six months before physical removal.

Cross-project and cross-team knowledge is coordinated through two complementary mechanisms: topic pools (shared `~/.engram/pools/<name>/` directories, with explicit `subscribed_at` declarations that position each pool in the hierarchy) and the Inter-Repo Messenger (point-to-point inbox at `~/.engram/inbox/<repo-id>/`, for direct communication between repos). Together, these allow engram to serve teams of different sizes without forcing a single sharing model on everyone.

### Document scope

This file, `SPEC.md`, defines the **on-disk format** of an engram memory store: directory layout, file naming, YAML frontmatter schemas, validation rules, versioning, and the compatibility contract. It is the authoritative source for format decisions; a breaking change to any field, naming rule, or structural invariant bumps the major version.

Companion documents cover the rest of the system:

- **`DESIGN.md`** — implementation of Layers 2 through 5 (CLI architecture, the Intelligence Layer components, Access Layer adapters and MCP server, and the Observation Layer web UI).
- **`METHODOLOGY.md`** — how LLMs should author, evolve, and retire memory assets: the behavioral discipline that makes the store grow smarter.

This document deliberately says nothing about how an LLM should decide when to write a memory, how the Relevance Gate scores candidates, or how the Autolearn Engine evolves a workflow. Those are design and methodology concerns, not format concerns.

### Intended readers

Any LLM agent that loads this document into its context, any tool author implementing an engram-compatible reader or writer, and any human who wants to understand what lives on disk and why.

Reading this document, an LLM should be able to answer: What files constitute a valid engram store? What frontmatter is required for each asset type? What does `enforcement: mandatory` mean for conflict resolution? Reading this document, a tool author should be able to implement a validator that accepts every valid store and rejects every invalid one, without consulting any other document.

### A note on v0.1 compatibility

v0.1 stores — those using the three-layer architecture (adapters / CLI / data) with four Memory types (`user`, `feedback`, `project`, `reference`) and no scope model — are valid v0.2 stores with the following interpretation: all existing files are treated as `scope: project`, all `feedback` files gain an implicit `enforcement: default`, and the missing `MEMORY.md` format fields are filled with their defaults. The migration contract is specified in full in §13.

---

## 1. Scope

This document is scoped to the Layer 1 — Data concerns of the five-layer architecture. Layers 2 through 5 (Control, Intelligence, Access, Observation) are specified in `DESIGN.md` and are deliberately excluded here so that the format contract remains stable regardless of which intelligence or access implementations are in use. A store that conforms to this document will function correctly with any compliant CLI, any compliant adapter, and any compliant Intelligence Layer — or with none of them at all.

### In scope

The following topics are fully specified in this document. An engram-compatible tool MUST implement every in-scope item correctly. The word MUST in this document follows RFC 2119 conventions.

- **Directory layout.** The project-level `.memory/` hierarchy and the user-global `~/.engram/` hierarchy, including subdirectory names and their semantics.
- **File naming and YAML frontmatter contract.** Required and optional fields for every asset type, their data types, and the forward-compatibility rule (unknown fields MUST be preserved on rewrite).
- **Six Memory subtypes and their body conventions.** The `user`, `feedback`, `project`, `reference`, `workflow_ptr`, and `agent` subtypes, each with a purpose, required frontmatter, and body structure. Subtype is orthogonal to scope.
- **Workflow asset format.** The `workflow.md` doc, `spine.*` executable, `fixtures/` test cases, `metrics.yaml` outcome tracker, and `rev/` copy-on-write revision history.
- **Knowledge Base asset format.** The `articles/` source directory, the `assets/` binary attachment directory, and the `_compiled.md` LLM-generated digest.
- **MEMORY.md hierarchical landing index.** Format, grouping, ordering, line-length limit, and the rule that every asset file must appear in the index.
- **Two-axis Scope model.** The four-level membership hierarchy (`org` > `team` > `user` > `project`) and the orthogonal subscription axis (`pool`, positioned by `subscribed_at`). Conflict resolution rules. Enforcement semantics.
- **Pool propagation modes.** The three subscriber modes — `auto-sync`, `notify`, and `pinned` — and the `subscribed_at` field that determines a pool's effective hierarchy level for a given subscriber.
- **Cross-repo inbox message protocol.** Directory layout of `~/.engram/inbox/<repo-id>/`, message frontmatter fields, the five `intent` values (`bug-report`, `api-change`, `question`, `update-notify`, `task`), and the `acknowledged` / `resolved` lifecycle. The Inter-Repo Messenger component in the Intelligence Layer implements the delivery and routing logic; this document specifies only the message format and directory contract.
- **Consistency contract.** The seven conflict classes that the Consistency Engine detects, the confidence fields that feed its evidence model (`validated_count`, `contradicted_count`, `confidence_score`, `staleness_penalty`), and the invariant that the engine never auto-mutates assets. The four-phase scan algorithm is `DESIGN.md` territory; the contract that the engine must not mutate is fixed here.
- **Validation rules and error-code table.** Structural, content, index, symlink, time, scope, and consistency validation rules, each with a machine-readable error code.
- **Versioning and v0.1 → v0.2 migration contract.** The `.engram/version` file, the semver bump rules, and the field-by-field migration guide for stores written under v0.1.

### Out of scope

The following topics are explicitly deferred to other documents. Implementing them in ways inconsistent with those documents is a project error, but that is not this document's concern.

- **CLI UX and command design.** Which flags `engram memory add` accepts, how `engram consistency scan` renders its report, what the `engram review` output format looks like — these are `DESIGN.md` topics (Layer 2).
- **Embedding algorithms and model choices.** Whether the Relevance Gate uses BM25, bge-reranker-v2-m3, or a hosted re-ranker is a runtime concern specified in `DESIGN.md` and the adapter guides. This document does not require or prohibit any embedding strategy.
- **LLM authoring discipline.** When to write a memory, how to phrase it, when to promote a `draft` to `active`, how often the Evolve Engine should propose revisions — see `METHODOLOGY.md`.
- **Web UI page design and interaction patterns.** The Context Preview simulation, the Autolearn Console, the Pool Manager matrix, the Graph force layout — see `DESIGN.md §7`.
- **Consistency Engine algorithms.** The four-phase scan sequence, scoring weights, and proposal ranking — see `DESIGN.md §5`. This document only fixes the conflict taxonomy, the seven class names, and the non-mutation invariant.
- **Playbook packaging and distribution.** The format of a distributable Playbook bundle (`engram playbook pack`) — deferred to a future SPEC §15 once the schema stabilizes.

---

## 2. Design Philosophy and Differentiators

The five principles below are design axioms, not aspirational statements. Each has concrete consequences for decisions made later in this document: the "never auto-delete" principle is why the `archived` and `tombstoned` lifecycle states exist; the "evidence-driven evolution" principle is why `validated_count` and `confidence_score` are required frontmatter fields for Memory assets; the "portability beats cleverness" principle is why the format is plain markdown and not a binary or graph format. Where a later section appears to make an arbitrary choice, tracing it back to one of these principles will explain why.

### Core principles

**1. Memory is a data asset, not a product feature.**

Every design decision in engram starts from a single premise: the memory store belongs to its owner, not to the tool that writes it. This is not an obvious position. Most LLM tools treat memory as a feature they provide — data stored in their format, in their system, retrievable through their API. The consequence is that switching tools means losing context, and abandoning a tool means losing years of accumulated knowledge.

engram inverts this. The store is a directory of plain markdown files with YAML frontmatter. Any text editor can open it. Any LLM can read it without a plugin. Any version control system can track it. If engram is abandoned tomorrow, the store remains fully functional as a knowledge base for whatever comes next. The tool is replaceable. The data is not.

**2. Portability beats cleverness.**

It is technically possible to build a more sophisticated storage format: a graph database with typed nodes and edges, a vector store with semantic search, a binary format with sub-millisecond reads. engram has deliberately chosen none of these. The on-disk format is markdown plus YAML — a combination that has been stable for decades, that a human can read without a tool, and that passes through git diff, grep, Obsidian, Logseq, and every other text-handling system without modification.

The Relevance Gate, the Consistency Engine, and the Autolearn Engine add intelligence on top of this format. But the intelligence layer is optional and disposable. Strip it away and the store still works. The format is the permanent bet; the intelligence is the optional investment. Portability wins decade-scale competitions against cleverness every time.

**3. Quality over capacity.**

engram imposes no hard limit on the size of a store. Disk space is cheap; forgetting is expensive. But unbounded accumulation without curation produces a store that grows noisier over time: contradictory rules pile up, stale references remain, project memories for finished work clutter the context budget.

The answer is not a capacity cap. Capacity caps destroy information and create arbitrary cutoffs. The answer is active quality maintenance: the Consistency Engine continuously scans for the seven conflict classes and surfaces remediation proposals to the owner. The Wisdom Metrics track the curation ratio — the fraction of the store that is active, validated, and non-redundant — as a first-class health signal. Quality is maintained by evidence-driven curation, not by forced eviction.

**4. Never auto-delete.**

An asset is never deleted from the store without an explicit human or LLM decision. When the Consistency Engine or the Evolve Engine proposes that an asset be retired, the proposal creates a `deprecated` lifecycle marker and surfaces the item in `engram review`. The owner makes the call. Accepted retirements move the file to `~/.engram/archive/` with a retention floor of six months before physical deletion. Mandatory assets at `enforcement: mandatory` cannot be archived by a project-level decision; they require action at the scope that created them.

This invariant exists because an incorrect retirement is harder to recover from than an incorrect addition. If a memory is wrong, the Consistency Engine will surface it for correction. If it is merely stale, the staleness penalty in the confidence formula will deprioritize it. There is no emergency that requires silent deletion.

**5. Evidence-driven evolution.**

Memories do not simply accumulate. Every time an LLM acts on an asset and the outcome is recorded, the asset's `validated_count` or `contradicted_count` increments. The `confidence_score` formula — `(validated - 2×contradicted - staleness_penalty) / max(1, total_events)` — produces a single number that summarizes how much the store's evidence supports each asset. Assets with falling confidence surface in `engram review` for human decision. Assets with sustained high confidence are promoted to `stable` and deprioritized for future scrutiny.

This mechanism — documented in the glossary as evidence-driven evolution — draws from several prior art threads. MemoryBank applies the Ebbinghaus forgetting curve to LLM memory prioritization. The Karpathy LLM Wiki demonstrates the compounding value of persistent, LLM-compiled knowledge over time. The autoresearch agentic loop shows that disciplined self-critique cycles produce reliable self-improvement in automated systems. The evo-memory Search-Synthesize-Evolve framework from DeepMind demonstrates that synthesis and evolution, not just retrieval, are what make memory systems intelligent. engram integrates these into the Consistency Engine, the Evolve Engine, and the Autolearn Engine — all of which operate on the plain-markdown store defined in this document without modifying its fundamental format.

### Differentiators

The table below compares engram v0.2 against the systems it was designed to improve upon. Cells use ✅ (full support), ❌ (not supported), or a short qualifier where partial or conditional support needs context.

| Capability | engram v0.2 | claude-mem | basic-memory | Karpathy LLM Wiki | mem0 | MemGPT / Letta | ChatGPT Memories |
|---|---|---|---|---|---|---|---|
| Plain markdown storage | ✅ | ❌ SQLite | ✅ | ✅ gist | ❌ hosted | ❌ hosted | ❌ hosted |
| Tool-agnostic (any LLM) | ✅ | ❌ Claude only | partial | partial | partial API | partial API | ❌ ChatGPT only |
| Two-axis scope (hierarchy + pool) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Explicit enforcement (mandatory/default/hint) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Consistency detection (7 classes) | ✅ | ❌ | ❌ | ❌ | partial | ❌ | ❌ |
| Executable workflows | ✅ | ❌ | ❌ | ❌ | ❌ | partial | ❌ |
| Knowledge Base class | ✅ | ❌ | ❌ | ✅ manual | ❌ | ❌ | ❌ |
| First-class Web UI | ✅ | ❌ | ❌ | ❌ | partial hosted | partial hosted | partial hosted |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cross-repo inbox | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Quantified self-improvement | ✅ Wisdom Metrics | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Open source | ✅ | ✅ | ✅ | ✅ | partial | ✅ | ❌ |

The differentiating bet engram makes is a specific combination that no other system attempts: data-asset portability (plain markdown you own, readable by anything) combined with active quality maintenance (Consistency Engine, evidence-driven confidence, evidence-driven curation) and quantifiable self-improvement (Wisdom Metrics that turn "smarter over time" from a marketing claim into a measurement). Most systems pick one: portability without quality maintenance, or quality maintenance without portability, or hosted quality with no portability at all. engram bets that serious users need all three, and that the only architecture that delivers all three is one where the format is a permanent commitment and the intelligence is a composable layer on top.

Table notes: "claude-mem" refers to the Claude Code project memory system in its pre-v0.2 form (SQLite-backed, Claude-specific). "basic-memory" refers to the open-source basic-memory project. "partial" in the Tool-agnostic row means the system works with more than one tool but is not format-open. "partial hosted" in the Web UI row means some hosted dashboard exists but it is tied to the vendor's platform. Cells marked ❌ reflect the system's design intent, not temporary gaps — these are structural limitations, not missing features in a roadmap.

### Design inspirations

engram v0.2 synthesizes ideas from several prior systems, each of which solved one part of the problem well.

- **Karpathy LLM Wiki** — demonstrated that a persistent, LLM-compiled knowledge artifact compounds in value over time in a way that ephemeral chat context does not. engram extends this to all three asset classes and makes the compilation step explicit and reproducible.
- **MemoryBank** — applied the Ebbinghaus forgetting curve to LLM memory prioritization. engram adopts the evidence-driven confidence model (validated/contradicted counts with staleness decay) but applies it beyond simple memory retrieval to asset lifecycle decisions.
- **autoresearch** — showed that disciplined agentic self-critique loops produce reliable self-improvement. The Autolearn Engine's evolution loop for Workflow assets is structured after autoresearch's eight-discipline cycle.
- **evo-memory (DeepMind, 2025)** — demonstrated that Search-Synthesize-Evolve is more powerful than retrieval alone. The Consistency Engine's proposal cycle and the Evolve Engine's ReMem action-think-refine loop are the engram instantiations of this insight.
- **MemGPT / Letta** — pioneered the idea of memory as structured OS-like virtual memory with paging. engram keeps the structure without the hosting: the store is on disk, not in a managed service.

---

## 3. Three Asset Classes

### §3.0 Introduction

engram v0.2 is not a single-asset-type system. Three classes — Memory, Workflow, and Knowledge Base — exist because three genuinely different kinds of knowledge need to live in a persistent store, and forcing all three into one format produces either a bloated single-purpose tool or a weakly typed catch-all that serves none of them well.

The distinction matters at the point of authorship, loading, and evolution:

- **Short assertions that an LLM should hold as baseline context** belong in Memory. A Memory asset is an atomic assertion — one fact, rule, preference, or pointer — that can be independently superseded without touching anything else. It is designed to load into every relevant session via the Relevance Gate.
- **Reusable procedures that must be executable and measurable** belong in Workflow. A Workflow asset has a runnable spine, fixture cases, and a metrics tracker. It is not enough to write down the steps; the spine must actually run, the fixtures must validate, and the metrics must prove that the procedure is improving over time.
- **Extended domain material that a human would read deliberately as a reference** belongs in a Knowledge Base. A KB asset is multi-chapter documentation written by a human, with an LLM-generated `_compiled.md` digest that can enter the context budget efficiently when the full article is too large to load.

**Classes are distinguished by function, not by size.** There are no hard line counts on any class. A Memory asset that happens to be 300 lines long is still a Memory asset if it encodes a single assertion that can be independently superseded. A Workflow asset is always a Workflow, regardless of how brief its spine is, because it carries the structural contract of executability. A KB article is a KB article because it is reference material a human navigates deliberately.

Size management is handled adaptively, not by imposing caps. Three signals surface review candidates to the owner without blocking or warning: the **dynamic budget allocation** (Relevance Gate shifts per-type token budget based on observed utilization), the **percentile length signal** (assets at or above the 95th percentile of length within their type appear in `engram review` as candidates for review), and **split / promote / demote proposals** from the Evolve Engine (splitting dense memories, promoting memory clusters to KB articles, demoting unused workflow spines, promoting procedural memories to workflows). All three signals are defined in glossary §16. All three are suggestive, never enforcing.

---

### §3.1 Three Asset Classes at a Glance

The table below is the authoritative summary. Later sections (§4, §5, §6) expand each class into its full frontmatter schema and validation rules.

| Class | Function | Required structure | Authorship model | Primary lifecycle state | Role in LLM context |
|---|---|---|---|---|---|
| **Memory** | An **atomic assertion** — one fact / rule / preference / pointer that can be independently superseded | A single `.md` file with YAML frontmatter + body | LLM drafts a candidate, human confirms before promotion to `active` | `draft → active → stable → deprecated → archived → tombstoned` | Enters system prompt via Relevance Gate; loaded per-session when relevance score meets threshold |
| **Workflow** | An **executable procedure** — has a runnable spine plus fixtures that validate it and metrics that track its outcomes | `workflow.md` (doc) + `spine.*` (executable) + `fixtures/` (test cases) + `metrics.yaml` (outcome tracker) + `rev/` (copy-on-write revision history) | LLM and human co-author; Autolearn Engine proposes spine revisions; human confirms phase gates | Same six states | Loaded on task match; spine invocation returns a structured outcome that feeds `metrics.yaml`; Autolearn Engine evolves it over time |
| **Knowledge Base** | A **domain reference** — multi-chapter document a human would read deliberately | `README.md` (entry point) + one or more chapter `.md` files + `assets/` (binary attachments) + `_compiled.md` (LLM-generated digest) | Human writes chapters; LLM compiles digest via `engram kb compile`; human reviews digest before promotion | Same six states | `_compiled.md` retrieved on demand and enters context budget first; full chapter files fetched when the LLM explicitly requests them |

**One decision tree for choosing a class.** When authoring a new asset, apply the following tests in order:

1. **Am I stating one thing that can be independently superseded?** → Memory. Even if the body is 300 lines long, if it encodes a single assertion whose retirement or replacement leaves everything else intact, it is a Memory asset.
2. **Does it have steps that must execute, with a measurable outcome?** → Workflow. If you find yourself wanting to attach a test case or a success/failure metric, the asset needs a spine. A prose description of a procedure is not a Workflow; a runnable spine is what makes it one.
3. **Is it extended domain material that someone would sit down and read as a reference?** → Knowledge Base. If the asset is the kind of thing you would open in a browser, scroll through, and navigate by section heading, it belongs in `kb/`.

If none of the three tests resolve the question, the default is Memory. A Memory asset that accumulates enough correlated siblings will eventually receive a *promote to KB* proposal from the Evolve Engine.

---

### §3.2 Directory Layout

Two directory trees constitute the complete on-disk layout of an engram v0.2 store. The project-level tree lives inside a single project. The user-global tree is shared across all projects for this user.

**Project-level store: `<project>/.memory/`**

```
<project-root>/
└── .memory/                            # project-scope store root
    ├── MEMORY.md                       # landing index (LLM reads first; §7)
    ├── pools.toml                      # pool subscription config (subscribed_at per pool)
    ├── local/                          # project-scope Memory (scope: project)
    │   ├── user_*.md
    │   ├── feedback_*.md
    │   ├── project_*.md
    │   ├── reference_*.md
    │   ├── workflow_ptr_*.md           # lightweight pointer into ../workflows/<name>/
    │   └── agent_*.md                  # LLM-learned heuristics (agent subtype)
    ├── pools/                          # subscribed pool symlinks → ~/.engram/pools/<name>/
    ├── workflows/                      # project-owned Workflow assets
    │   └── <name>/
    │       ├── workflow.md             # procedure doc (human-readable entry point)
    │       ├── spine.py                # runnable spine (or spine.sh / spine.toml)
    │       ├── fixtures/
    │       │   ├── success-case.yaml   # expected-success fixture
    │       │   └── failure-case.yaml   # expected-failure fixture
    │       ├── metrics.yaml            # outcome tracker (run count, success rate, ...)
    │       └── rev/                    # copy-on-write revision history
    │           ├── r1/ ...
    │           └── current → r7/       # symlink to active revision
    ├── kb/                             # project-owned Knowledge Base assets
    │   └── <topic>/
    │       ├── README.md               # article entry point
    │       ├── 01-overview.md          # chapter files (numbered for stable ordering)
    │       ├── 02-details.md
    │       ├── assets/                 # binary attachments (images, diagrams)
    │       └── _compiled.md            # LLM-generated digest (regenerated by engram kb compile)
    └── index/                          # (optional) topic sub-indexes (§7 detail)
        └── <topic>.md
```

**Directory-name note:** the folder `local/` is the filesystem location for project-scope Memory assets; the frontmatter `scope:` label for these files is `project`, not `local`. These two identifiers are independent: one is a path, the other is a scope label that participates in conflict resolution. Do not conflate them.

The `pools/` folder contains symlinks that point into the user-global `~/.engram/pools/<name>/`. The frontmatter `scope:` label for assets inside a pool is `pool`, and each subscribing project declares `subscribed_at: org | team | user | project` in `pools.toml`. The `subscribed_at` value determines the effective hierarchy level that pool content occupies in conflict resolution for that subscriber — it is not a property of the pool itself, but of the subscription.

**User-global store: `~/.engram/`**

```
~/.engram/                              # tool-private, per-user; never checked into project git
├── version                             # plain text file: "0.2"
├── config.toml                         # user-level engram configuration
├── org/<org-name>/                     # scope: org (git-synced; company / org rules)
│   └── *.md (+ workflows/, kb/ as needed)
├── team/<team-name>/                   # scope: team (git-synced; team / dept conventions)
│   └── *.md (+ workflows/, kb/ as needed)
├── user/                               # scope: user (this user's cross-project baseline)
│   └── *.md
├── pools/<name>/                       # scope: pool (canonical location; projects subscribe via symlinks)
│   └── *.md (+ workflows/, kb/)
├── inbox/<repo-id>/                    # Cross-Repo Messenger inbox (one dir per remote repo)
├── archive/                            # tombstoned assets; retained ≥ 6 months before physical removal
├── playbooks/<name>/                   # installable Playbook bundles (github:owner/repo clones)
├── graph.db                            # SQLite: subscription graph, reference graph, index
├── cache/                              # embedding index, FTS5 full-text index (rebuildable from files)
├── journal/                            # append-only event logs
│   ├── evolution.tsv                   # Autolearn / Evolve Engine runs
│   ├── propagation.jsonl               # pool update propagation events
│   ├── inter_repo.jsonl                # cross-repo inbox send/receive events
│   └── consistency.jsonl               # Consistency Engine scan results
└── workspace/                          # isolated per-run sandbox for Autolearn Engine
```

**User-global invariants.** Three invariants hold for `~/.engram/` and must not be violated by any compliant tool:

- `~/.engram/` is never checked into a project's git repository. It is tool-private and user-private. Org and team content is git-synced via `~/.engram/org/` and `~/.engram/team/` — those subdirectories have their own git remotes, not the project's.
- Every file in `journal/` is strictly append-only. No tool may truncate, rewrite, or delete a journal file. Journal compaction (to reclaim space) is performed only by `engram snapshot` and only after creating a verified archive.
- Asset deletions never go directly to the filesystem. Retiring an asset moves it to `~/.engram/archive/` where it is retained for a minimum of six months before physical removal. Direct `rm` on an asset file is a protocol violation.

---

### §3.3 Cross-Asset Reference Rules

The five rules below govern how assets reference one another across the three classes and across scope boundaries. The first four are MUST rules — a store that violates them fails `engram validate`. The fifth is a SHOULD rule — recommended practice that tools should support but that does not produce a validation error if absent.

**MUST 1 — Memory-to-Memory internal references use wiki-link syntax.**

A Memory asset that references another Memory asset MUST use the syntax `[[<memory-id>]]`, where `<memory-id>` is the file path relative to the nearest scope root, without the `.md` extension. Examples: `[[local/feedback_push_confirm]]` for a project-scope asset; `[[pools/kernel-work/reference_linux_lts]]` for an asset in a subscribed pool. This syntax is the canonical reference format. A tool that renders Memory assets MUST resolve wiki-links to their target files.

**MUST 2 — Workflow spine code reads Memory only through the CLI.**

A Workflow spine (`spine.py`, `spine.sh`, `spine.toml`, or any other executable) MUST read Memory assets through the `engram memory read <id>` CLI command, never by direct filesystem access. Direct filesystem reads bypass the scope enforcement model and the access logging that feeds `usage_count`. A spine that reads `.memory/local/feedback_push_confirm.md` directly by path is non-compliant. A spine that calls `engram memory read local/feedback_push_confirm` is compliant.

**MUST 3 — Cross-scope references MUST be declared in frontmatter.**

Any asset that references another asset in a different scope MUST list the target asset's ID in the `references:` frontmatter field (a YAML list of asset IDs). Cross-scope reference declarations feed the `graph.db` integrity model and enable the Consistency Engine to detect `reference-rot`. Example:

```yaml
references:
  - pools/kernel-work/reference_linux_lts
  - user/feedback_code_style
```

**MUST 4 — Assets with inbound references cannot be hard-deleted.**

Deleting an asset that has one or more other assets declaring it in their `references:` field is blocked by `engram validate`. Before deletion can proceed, the asset MUST first be transitioned to `deprecated` state, and all referrers must either update their `references:` field or acknowledge the supersedure via `supersedes:`. This rule ensures that `reference-rot` is detected before it occurs, not after.

**SHOULD 1 — KB and Memory use typed cross-class reference syntax.**

KB articles referencing Memory assets SHOULD use the syntax `@memory:<id>`. Memory assets referencing KB sections SHOULD use `@kb:<topic>/<section>`. These are typed sugar over the wiki-link format: a compliant tool MAY render `@memory:local/feedback_push_confirm` identically to `[[local/feedback_push_confirm]]`. The typed syntax makes cross-class references machine-discoverable without parsing body prose.

**Reference-rot detection.** The Consistency Engine detects dangling references — references where the target asset has been tombstoned or the ID no longer resolves — and surfaces them under the `reference-rot` conflict class (see §11). The engine does not auto-repair dangling references; it proposes remediation and leaves the decision to the owner.

---

### §3.4 Where to Go Next

The sections below expand each asset class and the shared infrastructure into their full format contracts.

- **§4 — Memory subtypes and frontmatter.** The six Memory subtypes (`user`, `feedback`, `project`, `reference`, `workflow_ptr`, `agent`), their required and optional frontmatter fields, the body conventions for each subtype, and the complete schema for the `confidence` evidence block.
- **§5 — Workflow asset format.** The `workflow.md` document schema, the `spine.*` contract (what makes a spine compliant), the `fixtures/` case format, the `metrics.yaml` outcome tracker schema, and the `rev/` copy-on-write revision protocol.
- **§6 — Knowledge Base asset format.** The `README.md` entry-point schema, chapter file conventions, the `assets/` directory contract, and the `_compiled.md` digest format and regeneration rules.
- **§7 — MEMORY.md hierarchical landing index.** The format, grouping rules, line-length limits, and the invariant that every asset in the project store must appear in the index exactly once.
- **§8 — Scope model.** The full two-axis scope model: the four-level membership hierarchy (`org > team > user > project`), the orthogonal subscription axis (`pool` with `subscribed_at`), conflict resolution rules, and `enforcement` semantics.

---

## 3.5 Session Asset (Episodic) — SPEC v0.2.1 Draft

This section is a **draft** that lands with v0.2.1; it is reproduced
here so that observer code (T-200 ~ T-212) has a stable contract to
build against. The full normative wording moves into §3 / §4 once the
v0.2.1 migrate (T-186) closes.

A **Session** is a fourth asset class, distinct from Memory / Workflow
/ Knowledge Base. Sessions capture **episodic** memory: one continuous
LLM-driven work span, from `session_start` to `session_end`. They feed
Stage 0 of the Relevance Gate (DESIGN §5.1, T-206) and may be promoted
to Memory only via explicit consent (T-209).

### 3.5.1 Layout

```
.memory/
  sessions/
    2026-04-26/                            # UTC date bucket
      sess_<id>.md                         # session asset file
      sess_<id>.timeline.jsonl             # Tier 0 mechanical fact stream
```

The date bucket uses the UTC calendar date of `started_at`. Two
machines in different timezones produce identical paths.

### 3.5.2 Session id

A session id MUST match the regex `^[a-z0-9][a-z0-9_-]{0,95}$`:
lowercase alphanumeric, underscore, or hyphen, length 1..96, leading
character alphanumeric. Path components are forbidden. The filename
prefix is always `sess_`.

### 3.5.3 Frontmatter schema

Required fields:

- `type: session` — fixed string.
- `session_id` — matches §3.5.2.
- `client` — one of `claude-code | codex | cursor | gemini-cli |
  opencode | manual | raw-api`.
- `started_at` — ISO-8601 datetime (UTC if no timezone is supplied).

Optional fields with default values:

- `ended_at: null` — ISO-8601 datetime when the session ended.
- `duration_seconds` — derived from `ended_at - started_at`.
- `task_hash: null` — see DESIGN §11.4 for derivation.
- `tool_calls: 0` — Tier 0 count.
- `files_touched: []` — sorted, de-duplicated list of file paths read or modified.
- `files_modified: []` — subset of `files_touched` that were modified.
- `outcome: unknown` — one of `completed | abandoned | error | unknown`.
- `error_summary: null` — first-line error if `outcome=error`.
- `prev_session: null` — same-task-hash predecessor (T-207).
- `next_session: null` — same-task-hash successor (T-207).
- `distilled_into: []` — list of distilled candidate Memory ids.
- `scope: project` — fixed default; `user` allowed via explicit consent.
- `enforcement: hint` — sessions never participate in mandatory bypass.
- `confidence` — same five-field block as §4.8 v0.2.1 (validated_score,
  contradicted_score, exposure_count, last_validated, evidence_version).

Unknown frontmatter fields MUST be preserved (§4.1 invariant).

### 3.5.4 Body

The body is a Markdown narrative with four required sections:
**Investigated**, **Learned**, **Completed**, **Next steps**. Tier 1
(LLM compactor) writes 150–300 token narratives; the mechanical
fallback (Tier 0 only, no LLM available) renders deterministic
bulleted lists from the timeline jsonl.

### 3.5.5 Reachability

Sessions are NOT subject to the §11 reachability invariant: they do not
need to be referenced from MEMORY.md. Sessions are addressed by their
task_hash linkage and date bucket, not by the topic graph.

### 3.5.6 Lifecycle

Sessions decay on a confidence-driven TTL (DESIGN §22.4, T-211):

```
effective_ttl = max(7d, 30d
                    + min(exposure_count * 3d, 60d)
                    - contradicted_score * 5d
                    - (14d if outcome=abandoned else 0))
```

When `effective_ttl` elapses, the asset moves to
`~/.engram/archive/sessions/<YYYY-MM>/`. Archive is never silently
deleted; SPEC §1.2 six-month retention floor applies.

---

## 4. Memory Subtypes and Frontmatter Schema

### §4.0 Overview

Memory is one of three asset classes defined in §3. Where §3 establishes the class boundary — Memory is an atomic assertion that can be independently superseded — this section defines Memory's internal taxonomy: six subtypes, the extended v0.2 frontmatter fields that every Memory asset carries, and the body conventions that distinguish one subtype from another.

The central organizing concept is **epistemic status**: subtype captures *who authored the asset and how we know it is true*, not what topic it covers or how large it is. A `feedback` asset is a rule handed down by a human; an `agent` asset is a heuristic inferred by the LLM itself. The same claim written by a human becomes `feedback`; the same claim written by the LLM becomes `agent`, with different default trust, different consistency scrutiny, and different confidence bootstrapping. Subtype is orthogonal to scope — any subtype can live at any scope level. A team-wide mandatory rule is `feedback` with `scope: team` and `enforcement: mandatory`, not a separate `team` subtype.

The six subtypes — `user`, `feedback`, `project`, `reference`, `workflow_ptr`, and `agent` — correspond to the six file prefixes used in `local/` and scope directories. The first four are carried forward from v0.1 with modest extension; the last two are new in v0.2. All six subtypes participate in the same lifecycle (`draft → active → stable → deprecated → archived → tombstoned`) and in the same evidence model (the `confidence` block described in §4.8).

§4.1 specifies the complete frontmatter schema: required fields, scope-conditional fields, and optional fields. §4.2–§4.7 define each subtype in turn. §4.8 defines the `confidence` object schema and the score formula. §4.9 resolves common overlap cases. §4.10 is a quick-reference summary table.

---

### §4.1 Frontmatter Schema

Every Memory asset file begins with a YAML frontmatter block delimited by `---`. The tables below list every recognized field. Unknown fields MUST be preserved by tools on rewrite — a tool MUST NOT delete a frontmatter key it does not recognize.

#### Required fields (all Memory assets)

| Field | Type | Since | Semantics |
|---|---|---|---|
| `name` | string | v0.1 | Short human-readable title. Displayed in `MEMORY.md`. |
| `description` | string | v0.1 | One-line relevance hook (≤150 chars). Used by the Relevance Gate when scanning `MEMORY.md` to decide whether to load the full asset. |
| `type` | enum | v0.1 | One of `user / feedback / project / reference / workflow_ptr / agent`. |
| `scope` | enum | v0.2 | One of `org / team / user / project / pool`. For v0.1 stores, defaults to `project` during migration (see §13). |
| `enforcement` | enum | v0.2 | One of `mandatory / default / hint`. Required on `feedback` subtype; optional elsewhere, defaults to `hint`. See glossary §5 for semantics. |

#### Scope-conditional required fields

These fields are required only when `scope` takes the indicated value.

| Field | Required when | Semantics |
|---|---|---|
| `org` | `scope: org` | Organization name matching `~/.engram/org/<name>/`. |
| `team` | `scope: team` | Team name matching `~/.engram/team/<name>/`. |
| `pool` | `scope: pool` | Pool name matching `~/.engram/pools/<name>/`. |
| `subscribed_at` | `scope: pool` | The effective hierarchy level for this subscriber: one of `org / team / user / project`. Declared in `pools.toml`, referenced here for per-asset clarity. |

#### Optional fields (all Memory assets)

| Field | Type | Since | Semantics |
|---|---|---|---|
| `created` | ISO 8601 | v0.1 | First write date. |
| `updated` | ISO 8601 | v0.1 | Last edit date. |
| `tags` | list[string] | v0.1 | Free-form topic tags for grouping and search. |
| `expires` | ISO 8601 | v0.1 | Single-point hint: asset may be stale after this date. Triggers a review prompt; does not auto-archive. |
| `valid_from` | ISO 8601 | v0.2 | The fact became true on or after this date. Enables time-filtered queries in `graph.db`. |
| `valid_to` | ISO 8601 | v0.2 | The fact stopped being true on this date. Distinct from `expires`: `valid_to` marks historical closure, `expires` marks a future review trigger. |
| `source` | string | v0.1 | Where the claim came from — a conversation date, incident ID, URL, or `agent-learned` (for `agent` subtype). |
| `references` | list[string] | v0.2 | IDs of assets this one depends on. Cross-scope references MUST be declared here (see §3.3 MUST 3). Feeds `graph.db` integrity. |
| `overrides` | string | v0.2 | ID of a higher-scope asset this one overrides. Required when overriding a `default`-enforcement asset; MUST NOT be used against a `mandatory`-enforcement asset. |
| `supersedes` | string | v0.2 | ID of an older asset this one replaces. Creates a lineage chain; prevents `silent-override` conflicts. |
| `limitations` | list[string] | v0.2 | Conditions under which this asset does not apply. Recommended on `feedback`, `project`, and `agent` subtypes when scope is narrow. |
| `confidence` | object | v0.2 | Evidence-driven confidence block. Schema defined in §4.8. Effectively required on `agent` subtype; recommended for all assets once they become `active`. |

#### Subtype-specific required fields

Individual subtype sections (§4.2–§4.7) list any fields that are required for that specific subtype beyond the common required set above.

---

### §4.2 `user` Subtype

**Purpose.** Facts about the human: their role, skills, working context, preferences, and constraints the LLM should tailor its behavior to. This is the "who am I talking to" baseline. It is human-authored and rarely changes relative to other subtypes.

**Body convention.** Free prose of at least 20 characters. No required subsections. Write in the third person from the LLM's perspective ("The user maintains…", "They prefer…") so the text reads naturally when injected into a system prompt.

**No additional required frontmatter.** `enforcement` defaults to `hint` — user context is advisory, not a hard rule.

**Example:**

```markdown
---
name: user is a platform team lead at acme
description: leads the acme platform team; Go and Kubernetes primary stack; prefers terse technical explanations
type: user
scope: user
created: 2026-04-18
tags: [role, context]
---

The user leads the platform team at Acme Corp, responsible for the internal Kubernetes-based deployment infrastructure used by roughly forty product engineers. They have seven years of experience with Go and four with Kubernetes operators. Their primary domain is cluster networking, admission webhooks, and custom controllers.

Frame all explanations assuming they already know Go and Kubernetes internals. Skip preambles like "Kubernetes is a container orchestration system." When proposing solutions, lead with the Go code or YAML — motivation second, not first.

They keep a strict work-life boundary: do not propose batch operations that might run overnight or on weekends without explicit scheduling guardrails.
---
```

---

### §4.3 `feedback` Subtype

**Purpose.** Rules the LLM must follow — either corrections the user has given after an observed failure, or approaches the user has confirmed work well. These are human-authored behavioral constraints. The `enforcement` field is required and non-negotiable for this subtype: it determines whether the rule can be locally overridden.

**Required frontmatter for this subtype:** `enforcement` (one of `mandatory / default / hint`). Unlike other subtypes where `enforcement` defaults to `hint`, on `feedback` it must be stated explicitly.

**Required body structure:**

```
<one-line rule statement>

**Why:** <reason tied to an incident, preference, or explicit instruction>

**How to apply:** <when and where this rule kicks in; include edge cases>
```

The "Why" and "How to apply" sections are required, not optional prose. Knowing *why* lets future readers — human or LLM — reason about edge cases instead of applying the rule blindly. A rule without a "Why" is not a `feedback` asset; it is a note. Rules that genuinely admit no exceptions should be `enforcement: mandatory`. Rules that are good defaults but can be project-overridden should be `enforcement: default`. Personal stylistic preferences that the user does not want enforced should be `enforcement: hint`.

**Example — org-scope mandatory rule:**

```markdown
---
name: all commits must include SPDX license headers
description: every source file committed to any acme-org repo must carry an SPDX-License-Identifier header
type: feedback
scope: org
org: acme
enforcement: mandatory
created: 2026-01-15
tags: [compliance, licensing]
source: 2026-01-14 legal team directive
---

Every source file committed to an acme-org repository must include an `SPDX-License-Identifier:` header on the first or second line of the file.

**Why:** Legal team directive issued 2026-01-14 after an IP audit found unlicensed files in three repos. Non-compliance now blocks CI for all org repos.

**How to apply:** Before generating or modifying any source file (`.go`, `.py`, `.ts`, `.sh`, etc.), check for an existing SPDX header. If absent, prepend `// SPDX-License-Identifier: Apache-2.0` (or the project's declared license). Do not commit files without it. If the project's license is not Apache-2.0, confirm with the user before assuming.
---
```

**Example — user-scope hint:**

```markdown
---
name: prefer table-driven tests in Go
description: write Go tests as table-driven subtests unless the test is trivially single-case
type: feedback
scope: user
enforcement: hint
created: 2026-03-02
tags: [go, testing, style]
source: preference stated 2026-03-02
---

Write Go tests using table-driven subtests (`for _, tc := range cases { t.Run(tc.name, ...) }`), not a flat sequence of assertion calls.

**Why:** Table-driven tests are easier to extend, produce cleaner failure messages that identify the failing case by name, and match the Go standard library's own style. The user has stated this preference explicitly.

**How to apply:** For any new Go test or when refactoring an existing test, default to table-driven. Exception: if there is genuinely only one case and more cases are unlikely, a flat test is fine.
---
```

---

### §4.4 `project` Subtype

**Purpose.** Facts about ongoing work: initiatives in flight, active decisions, deadlines, incident postmortems, or any context that cannot be recovered from code or git history alone. These are human-authored observations about the current project state. They are expected to change frequently and expire when the project phase concludes.

**Required body structure:**

```
<one-line fact or decision>

**Why:** <motivation — constraint, deadline, stakeholder requirement>

**How to apply:** <how this shapes the LLM's future suggestions or plans>
```

**Absolute dates only.** Relative references like "next Thursday" or "end of Q2" must be written as ISO 8601 dates at write time (`2026-04-23`, `2026-06-30`). Relative references become ambiguous the moment the asset ages past the original session. The `expires` field is strongly encouraged for time-bounded project facts.

**No additional required frontmatter.** `enforcement` defaults to `hint` — project decisions are context, not mandates.

**Example:**

```markdown
---
name: acme platform migrating to Go 1.23 for Q2 release
description: all platform services must target Go 1.23 by 2026-06-30; 1.22 support dropped after that date
type: project
scope: project
created: 2026-04-10
updated: 2026-04-18
tags: [migration, go, deadline]
expires: 2026-07-01
valid_from: 2026-04-10
valid_to: 2026-06-30
source: Q2 planning doc, 2026-04-10
---

All platform services must target Go 1.23 by 2026-06-30. After that date, the internal CI base image drops the Go 1.22 toolchain entirely.

**Why:** The Go 1.22 toolchain has a known vulnerability (CVE-2026-0001) that cannot be backported. The security team has set 2026-06-30 as the hard cutoff. Missing the date means a mandatory rollback to pre-release builds.

**How to apply:** When suggesting any code changes or dependency updates for platform services, target Go 1.23 syntax and standard library. Do not suggest `go mod` changes that pin to 1.22. If a dependency has not released a 1.23-compatible version, flag it explicitly rather than silently downgrading.
---
```

---

### §4.5 `reference` Subtype

**Purpose.** Pointers to external systems, documents, dashboards, tickets, authoritative codebases, or any resource outside the store that the LLM should know exists and consult. References are human-authored. They are not about project state (that is `project`) and not about rules (that is `feedback`) — they are "here is where to find X."

**Body convention.** Free prose. Include enough context to: (1) locate the resource without ambiguity, (2) explain *why* this resource matters and when to use it, and (3) note any access requirements or caveats. A reference that says only "here is the URL" without explaining when to use it or what it covers will score low in relevance ranking.

**No additional required frontmatter.** `enforcement` defaults to `hint`.

**Example:**

```markdown
---
name: acme internal latency dashboard (Grafana)
description: team's primary SLO dashboard; shows p50/p95/p99 latency for all platform services broken down by region
type: reference
scope: team
team: platform
created: 2026-02-20
updated: 2026-04-18
tags: [observability, slo, grafana, latency]
source: platform on-call handbook v3
---

The primary latency and SLO dashboard for the platform team is hosted at the company's internal Grafana instance. It covers p50, p95, and p99 latency for all platform services, broken down by region and endpoint, with a 30-day rolling window.

Consult this dashboard before making any performance-related recommendations for platform services. The dashboard's "SLO breach risk" panel shows current error budget burn rate — if it is above 50%, treat any proposal that increases request fanout or adds synchronous RPCs as high-risk.

Access requires the internal VPN and membership in the `grafana-platform-team` group. The on-call rotation member for the week is listed in the top-right panel.
---
```

---

### §4.6 `workflow_ptr` Subtype — New in v0.2

**Purpose.** A lightweight pointer from the Memory store into a full Workflow asset (see §5). `MEMORY.md` is designed to load into every LLM session; full Workflow documents are loaded only on task match. The `workflow_ptr` bridges this: an LLM scanning `MEMORY.md` sees the pointer and knows a complete, executable procedure exists at the reference, without loading the full `workflow.md` into the context budget prematurely.

This subtype keeps `MEMORY.md` small and scannable while allowing the LLM to discover available workflows. When the LLM determines a workflow is relevant, it loads the full `workflow.md` from the `workflow_ref` path.

**Required frontmatter for this subtype:**

| Field | Type | Semantics |
|---|---|---|
| `workflow_ref` | string | Path to `workflows/<name>/` relative to the scope root. The full procedure lives at `<scope-root>/<workflow_ref>/workflow.md`. |

**Body convention.** One to three paragraphs summarizing: (1) what the workflow does, (2) when to use it, and (3) what outcome to expect. Do not reproduce the full procedure steps — those live in `workflow.md`. The body is the "should I load this workflow?" decision aid.

**Example:**

```markdown
---
name: git merge workflow (platform team standard)
description: step-by-step procedure for merging feature branches with squash, changelog entry, and team notification
type: workflow_ptr
scope: team
team: platform
workflow_ref: workflows/git-merge-standard/
created: 2026-03-15
updated: 2026-04-10
tags: [git, workflow, merge, release]
---

The `git-merge-standard` workflow covers the complete lifecycle of merging a feature branch into `main` for platform services: pre-merge checks (test pass, coverage gate, diff size review), squash-merge with a conventional commit message, CHANGELOG.md entry generation, and the Slack notification to `#platform-releases`.

Use this workflow whenever merging a branch that touches platform service code. Do not use for documentation-only branches (those follow a lighter path) or for hotfix branches (those have a separate `git-hotfix` workflow with different release gating).

Expected outcome: the branch is squash-merged into `main`, a `CHANGELOG.md` entry is appended, and a formatted release summary is posted to `#platform-releases` within two minutes of merge. The metrics tracker records the merge event and updates the workflow success rate.
---
```

---

### §4.7 `agent` Subtype — New in v0.2

**Purpose.** LLM-learned meta-heuristics: behavioral patterns that the LLM has inferred from observed outcomes, not rules a human has stated. This is distinct from `feedback` in a critical way: the source is the LLM itself. That distinction has three concrete consequences.

**Implications of LLM-authored status:**

1. **Lower default trust.** The Consistency Engine scrutinizes `agent` assets more frequently than `feedback` assets. A `feedback` rule has human authority behind it; an `agent` heuristic is a hypothesis.
2. **`source` is required.** The `source` field must identify the origin: `agent-learned` for unsourced heuristics, or a more specific reference like `source: autolearn/git-merge-standard/r5` when the heuristic emerged from a specific workflow revision.
3. **`confidence` is effectively required.** `agent` assets are hypotheses; their evidence base must be explicit. Bootstrap with `validated_count: 0` and `contradicted_count: 0` at creation. The asset does not become `stable` until it has accumulated enough positive outcomes.

**Required body structure:**

```
<one-line heuristic statement>

**Why:** <concrete outcomes observed — "observed N successful results using this approach"; cite the revision or session>

**How to apply:** <when and where this heuristic applies; include known failure modes>
```

The "Why" must reference concrete evidence, not intuition. "Observed 5 successful merges using squash after adopting this approach in rev r5" is a valid Why. "This seems cleaner" is not.

**Example:**

```markdown
---
name: squash before merge prevents platform CI flakiness
description: squashing commits locally before pushing to the merge queue reduces CI re-run rate on platform services
type: agent
scope: project
source: autolearn/git-merge-standard/r5
enforcement: hint
created: 2026-04-12
tags: [git, ci, merge, agent-learned]
confidence:
  validated_count: 5
  contradicted_count: 0
  last_validated: 2026-04-17
  usage_count: 7
limitations:
  - observed only on platform service repos; not validated on SDK or docs repos
  - may not apply when commits carry individual authored-by attribution requirements
---

Squash local commits into a single commit before pushing to the merge queue; do not rely on the merge queue to squash.

**Why:** Observed across 5 consecutive merges after adopting this approach in `git-merge-standard` revision r5: CI re-run rate dropped from approximately 40% to zero. The likely cause is that merge queue's squash triggers a cache invalidation in the Go build cache that local squash does not, because the merge-queue squash changes the commit tree structure in a way the build cache does not recognize.

**How to apply:** Before pushing any platform service branch, run `git rebase -i origin/main` and squash to a single commit. If the branch is too large to squash cleanly, split it into smaller chunks rather than pushing unsquashed. Apply to platform service repos only; behavior has not been observed elsewhere.
---
```

---

### §4.8 Confidence Field Schema

The `confidence` block is a YAML object nested inside frontmatter. It is required on `agent` subtype and recommended for all Memory assets once they reach `active` state. The four sub-fields below are all required when the `confidence` block is present.

```yaml
confidence:
  validated_count: 12         # Times LLM acted on this asset and reality confirmed it
  contradicted_count: 0       # Times reality contradicted the asset's claim or rule
  last_validated: 2026-04-15  # ISO 8601 date of most recent positive outcome
  usage_count: 38             # Times this asset entered any LLM context
```

**Sub-field semantics:**

| Sub-field | Type | Semantics |
|---|---|---|
| `validated_count` | integer ≥ 0 | Incremented each time the LLM acted on this asset and an outcome journal entry records success or confirmation. |
| `contradicted_count` | integer ≥ 0 | Incremented each time a journal entry records that following this asset produced an incorrect result or was explicitly corrected. |
| `last_validated` | ISO 8601 | Date of the most recent positive outcome event. Used to compute the `staleness_penalty`. |
| `usage_count` | integer ≥ 0 | Total times this asset entered an LLM context of any kind (priming, reference, or review). Useful for weighting the confidence score by exposure. |

**Confidence score formula** (applied by the Consistency Engine in §11; defined here as the canonical reference):

```
score = (validated_count - 2 × contradicted_count - staleness_penalty) / max(1, total_events)

where:
  total_events     = validated_count + contradicted_count
  staleness_penalty = 0.0   if last_validated is within 90 days of today
                   | 0.3   if last_validated is within 365 days of today
                   | 0.7   if last_validated is older than 365 days
```

When an asset is first created, all counts start at zero. After a configurable number of uses with no contradictions (default N = 3), the asset is eligible for promotion to lifecycle state `stable`.

**Invariant:** A low confidence score does not trigger automatic archiving. It surfaces the asset in `engram review` for human decision. The Consistency Engine proposes; it never auto-mutates. See §11 for the full consistency contract.

---

### §4.9 Subtype Boundary Rules

The table below resolves the most common overlap cases. Apply it when authoring a new asset to determine the correct subtype.

| Situation | Correct subtype |
|---|---|
| "Always do X when Y" — rule the user taught you | `feedback` |
| "Usually do X when Y" — heuristic the LLM inferred from outcomes | `agent` |
| Team-wide rule like "all files must carry an SPDX header" | `feedback` + `scope: team` + `enforcement: mandatory` |
| External doc URL you will want to consult again | `reference` |
| Ongoing project decision like "we are using Go 1.23 for this release" | `project` |
| Who the user is, their role, how they like to work | `user` |
| Lightweight pointer to a full Workflow procedure | `workflow_ptr` |
| Personal style preference the user mentioned once | `feedback` + `enforcement: hint` |
| LLM-observed pattern that worked N times but the user has not confirmed | `agent` |
| URL to an internal dashboard the team uses for observability | `reference` + `scope: team` |

**Note on `team` as scope, not subtype.** v0.1 had no scope model; team-level conventions were a category ambiguity. In v0.2, `team` is a scope label (`scope: team`), never a subtype. A team-wide mandatory rule is `feedback` + `scope: team` + `enforcement: mandatory`. The v0.1 four subtypes (`user`, `feedback`, `project`, `reference`) are carried forward; v0.2 adds `workflow_ptr` and `agent`.

**On `limitations`.** When an `agent` or `feedback` asset is known to not apply in certain conditions, declare `limitations:` rather than embedding caveats in the body prose. The Consistency Engine uses `limitations` to avoid false positives when evaluating assets against contradicting evidence from contexts where the limitation applies.

---

### §4.10 Quick-Reference Summary

| Subtype | File prefix | Author | Additional required frontmatter | Body convention |
|---|---|---|---|---|
| `user` | `user_` | Human | — | Free prose |
| `feedback` | `feedback_` | Human | `enforcement` | Rule statement + **Why** + **How to apply** |
| `project` | `project_` | Human | — | Fact / decision + **Why** + **How to apply**; absolute dates only |
| `reference` | `reference_` | Human | — | Free prose with resource pointer, access notes, and when-to-use guidance |
| `workflow_ptr` | `workflow_ptr_` | Human | `workflow_ref` | 1–3 paragraphs: what the workflow does, when to use it, expected outcome |
| `agent` | `agent_` | LLM | `source` (must identify origin); `confidence` effectively required | Rule statement + **Why** (with concrete outcome reference) + **How to apply** |

---

---

## 5. Workflow Asset Format

### §5.0 Overview

A Workflow is engram's answer to procedural knowledge — knowledge of **how to do something** reliably and repeatably. Memory captures atomic assertions: facts, rules, preferences, pointers. Workflow captures executable procedures: a spine that actually runs, fixtures that validate it, metrics that measure it, and a revision history that records how it improved.

Two design traditions inform this format:

- **Agent Factory** (Karpathy): experience should be stored as executable code, not narrative prose. A plain-text procedure degrades silently; an executable spine fails loudly, is testable, and can be improved mechanically.
- **autoresearch** (Karpathy): self-improvement loops need fixed budgets, single-file mutation boundaries, append-only result logs, a simplicity criterion, and human-reviewable phase gates. The autolearn ratchet (see §5.6) applies these disciplines directly.

The three asset classes complement each other. A Memory asserts a fact. A Workflow executes a procedure. A Knowledge Base articles explains a domain. Each loads at a different point in the LLM's task lifecycle and occupies a distinct cost tier in the context budget.

§5 defines the **on-disk format contract** for Workflow assets: directory layout, frontmatter schema, spine requirements, fixture format, metrics schema, and revision lifecycle. The Autolearn Engine that evolves workflows round-by-round is specified in `DESIGN.md §5.3`; this document does not implement the algorithm, only the data contracts the algorithm must respect.

---

### §5.1 Directory Layout

Every Workflow lives in a `workflows/<name>/` directory under its scope root. The complete layout:

```
<scope-root>/workflows/<name>/
├── workflow.md                    # human-readable doc (required)
├── spine.<ext>                    # executable entry point (required)
├── fixtures/                      # validation scenarios (required)
│   ├── success-case.yaml          # at least one success fixture
│   └── failure-case.yaml          # at least one failure fixture
├── metrics.yaml                   # metric definitions and aggregation rules (required)
├── rev/                           # copy-on-write revision history
│   ├── r1/
│   │   ├── spine.<ext>
│   │   ├── workflow.md
│   │   ├── fixtures/
│   │   ├── metrics.yaml
│   │   └── outcome.tsv            # per-fixture outcomes for this rev
│   ├── r2/
│   │   └── ...
│   └── current -> rN/             # symlink to active revision
└── journal/
    ├── evolution.tsv              # append-only; one row per autolearn round
    └── runs.jsonl                 # append-only; one row per invocation
```

**Scope roots** for the `workflows/<name>/` directory:

| Scope | Root path |
|---|---|
| `project` | `<project>/.memory/` |
| `team` | `~/.engram/team/<team>/` |
| `org` | `~/.engram/org/<org>/` |
| `user` | `~/.engram/user/` |
| `pool` | `~/.engram/pools/<pool>/` |

**The `rev/current` symlink.** Each autolearn round creates a new `rev/rN/` directory (N = max existing index + 1) containing a complete snapshot: `spine.<ext>`, `workflow.md`, `fixtures/`, `metrics.yaml`, and `outcome.tsv`. On success the `current` symlink moves atomically to point at `rev/rN/`. On ratchet-revert (the new rev does not improve the primary metric beyond tolerance) the symlink stays at its previous target and `rev/rN/` is retained on disk as an audit entry. Failed revisions are never deleted; they are evidence.

**`journal/evolution.tsv`** is strictly append-only. Every autolearn round appends one row regardless of outcome. Its schema is specified in `DESIGN.md §5.3`; the invariant that no tool may truncate or rewrite it is fixed here.

**`journal/runs.jsonl`** records every invocation of `engram workflow run <name>` — one JSON object per line, append-only, containing timestamp, inputs hash, outcome status, and the metrics values emitted by the spine.

**No size cap.** The Workflow format imposes no line-count or byte-count ceiling on any file. Size is a content concern; the format contract does not encode it.

---

### §5.2 `workflow.md` Format

`workflow.md` is the human-readable entry point. It is also what the LLM loads when a `workflow_ptr` resolves: it provides enough context to understand what the spine does, when it applies, and what success and failure look like.

**Required frontmatter:**

| Field | Type | Semantics |
|---|---|---|
| `name` | string | Short human-readable title. Displayed in `MEMORY.md` via the referencing `workflow_ptr`. |
| `description` | string | ≤150 char summary. Used by the Relevance Gate. |
| `type` | literal `workflow` | Always `workflow`. |
| `scope` | enum | `org / team / user / project / pool`. |
| `spine_lang` | enum | `python3 / bash / toml`. Declares which executor the runtime uses to invoke the spine. |
| `spine_entry` | string | Relative path to the spine file from the workflow directory root (e.g. `spine.py`). |
| `inputs_schema` | string | Relative path to a JSON Schema file that the runtime uses to validate spine inputs before invocation (e.g. `schemas/inputs.json`). |
| `outputs_schema` | string | Relative path to a JSON Schema file that the runtime uses to validate spine output before recording (e.g. `schemas/outputs.json`). |
| `metric_primary` | string | Name of the metric that drives the autolearn ratchet. Must match a `name` entry in `metrics.yaml`. |
| `lifecycle_state` | enum | `draft / active / stable / deprecated / archived`. |
| `created` | ISO 8601 | |
| `updated` | ISO 8601 | |

Optional frontmatter fields follow the same rules as Memory assets (see §4.1): `tags`, `references`, `side_effects`, `expires`, and any unknown fields, which MUST be preserved on rewrite.

**`side_effects`** is a YAML list. A spine that has no side effects omits this field. A spine that writes files, makes network calls, or commits to git MUST declare it:

```yaml
side_effects: [fs_write, network, git_commit]
```

The runtime displays a prompt before invoking any spine with declared side effects. A spine that has side effects but does not declare them is non-compliant.

**Required body sections** (in order):

1. **Purpose** — what problem this workflow solves; why it exists as a workflow rather than a Memory.
2. **When to use** — specific trigger conditions; what context signals indicate this workflow is relevant.
3. **Expected outcome** — the success criteria, expressed in terms of `metric_primary`; what the caller should observe when the spine returns `status: success`.
4. **Failure modes** — known failure patterns and their escape hatches; what the caller should do when the spine returns `status: failure` or exits with a non-zero code.
5. **Why this approach** — design rationale; what the spine encodes and why it encodes it that way. This section is load-bearing for the autolearn engine: it documents what must not be mutated away.

---

### §5.3 Spine Contract

The spine is the only artifact that actually executes. Every other file in the workflow directory is declarative. The spine must satisfy the following requirements regardless of `spine_lang`.

**General requirements (all `spine_lang` values):**

1. **Deterministic on same input.** Given the same `inputs`, the spine produces the same `outputs` and same side effects. If the workflow is inherently time-sensitive, the current time must be included in the declared `inputs_schema` — the caller provides it explicitly rather than letting the spine read it from the clock.
2. **Side-effect-free by default.** A spine that writes files, makes network calls, or commits to git MUST declare `side_effects:` in `workflow.md` frontmatter (see §5.2). Undeclared side effects are a compliance violation.
3. **Memory reads through the CLI only.** The spine MUST read Memory assets through `engram memory read <id>`. Direct filesystem reads on `.memory/` paths are non-compliant (see §3.3 MUST 2).
4. **Structured outcome.** The spine MUST emit output that conforms to `outputs_schema`. The minimum valid output contains `status` (`success` or `failure`) and `metrics` (a map of metric names to values).

**Python spine (`spine_lang: python3`):**

```python
# spine.py
def main(inputs: dict) -> dict:
    """
    Entry function. `inputs` is validated against inputs_schema before this call.
    Return value is validated against outputs_schema after this call.
    """
    # ... workflow logic ...
    return {
        "status": "success",     # or "failure"
        "metrics": {
            "merge_time_seconds": 42.1,
        },
        "artifacts": [],         # optional list of produced file paths
        "trace": [],             # optional list of step-log strings
    }
```

The runtime calls `main(inputs)` directly. No `if __name__ == "__main__"` guard is required (though it may be present). The runtime does not exec the file as a subprocess — it imports and calls the function.

**Bash spine (`spine_lang: bash`):**

```bash
#!/usr/bin/env bash
# spine.sh
# Reads JSON inputs from stdin.
# Emits JSON output to stdout.
# exit 0 = success; exit 1 = failure; exit 2 = blocked (precondition unmet)
set -euo pipefail

inputs=$(cat)
# ... workflow logic ...
echo '{"status":"success","metrics":{"merge_time_seconds":38}}'
```

The runtime pipes the serialized `inputs` JSON to the spine's stdin and reads the output JSON from stdout. Exit code determines the primary status; the JSON output provides metric values.

**TOML spine (`spine_lang: toml`, declarative only):**

Permitted for pure declarative workflows that chain CLI invocations with parameter templating. The engram runtime reads the TOML and executes the declared steps in order. No general-purpose computation is available; use Python or bash for logic. TOML spines are always side-effect-free unless they invoke commands that have side effects, which must still be declared.

---

### §5.4 Fixtures Format

Fixtures are the test suite for a workflow. The runtime executes them via `engram workflow test <name>`. A workflow that has no passing fixture cannot transition from `draft` to `active`.

**Minimum required:** at least one `success-case.yaml` and at least one `failure-case.yaml`. Additional fixtures are encouraged; name them descriptively (e.g. `success-concurrent.yaml`, `failure-rebase-conflict.yaml`).

**Fixture file format:**

```yaml
# success-case.yaml
name: typical merge request without conflicts
inputs:
  repo_url: git@github.com:acme/service-a.git
  source_branch: feature/add-widget
  target_branch: main
expected:
  status: success
  metrics:
    merge_time_seconds:
      max: 120
    conflicts_resolved_manually:
      max: 0
assertions:
  - type: metric_threshold
    metric: merge_time_seconds
    op: le
    value: 120
  - type: no_exception
```

```yaml
# failure-case.yaml
name: unresolvable rebase conflict
inputs:
  repo_url: git@github.com:acme/service-a.git
  source_branch: feature/conflicting-rename
  target_branch: main
expected:
  status: failure
  failure_mode: rebase_conflict
assertions:
  - type: status_equals
    value: failure
  - type: no_dirty_state
    description: spine must leave repo in clean state on failure (no detached HEAD, no partial merge)
```

**Assertion types** (minimum required set; tools may define additional types):

| Type | Semantics |
|---|---|
| `metric_threshold` | Asserts that `metrics.<metric>` satisfies `<op>` `<value>` (ops: `le`, `ge`, `eq`, `lt`, `gt`). |
| `no_exception` | Asserts the spine returned without raising an uncaught exception. |
| `status_equals` | Asserts `outputs.status == value`. |
| `no_dirty_state` | Asserts the execution environment is clean post-run (workflow-defined; the `description` field is human-readable justification). |

A fixture run records one row in `rev/<rev>/outcome.tsv`: timestamp, fixture name, status (pass/fail), and the metric values the spine returned. The `outcome.tsv` is append-only within a revision.

---

### §5.5 `metrics.yaml` Format

`metrics.yaml` defines which outcome measurements the workflow tracks, how they aggregate across runs, and which metric drives the autolearn ratchet.

```yaml
# metrics.yaml
metrics:
  - name: merge_time_seconds
    aggregation: p95         # p50, p95, p99, mean, sum, max, min
    unit: seconds
    source: outcome_field
    field: metrics.merge_time_seconds

  - name: conflicts_resolved_manually
    aggregation: sum
    unit: count
    source: outcome_field
    field: metrics.conflicts_resolved_manually

primary: merge_time_seconds

ratchet_rule:
  direction: minimize        # minimize | maximize
  tolerance: 0.02            # fractional; regression beyond this triggers revert

complexity_budget:
  max_lines_factor: 1.5      # new spine must not exceed 1.5× the current spine's line count
```

**Field semantics:**

- `metrics[].aggregation` — how individual run values are combined when computing the metric over a revision window. `p95` is appropriate for latency metrics; `sum` for cumulative counts; `mean` for rates.
- `metrics[].source` — `outcome_field` means the value is read directly from the spine's `outputs.metrics.<field>` map. Future sources (e.g. `journal_aggregate`) may be defined in later sections.
- `primary` — the metric that the Autolearn Engine optimizes. Must match one `name` in the `metrics` list. The ratchet compares the `primary` metric of the new revision against the `primary` metric of the current revision; if the comparison fails the `ratchet_rule`, the new revision is rejected.
- `ratchet_rule.direction` — `minimize` means a lower value is better (latency, error count); `maximize` means a higher value is better (success rate, coverage).
- `ratchet_rule.tolerance` — fractional slack. A regression of ≤2% (`tolerance: 0.02`) is accepted; anything worse triggers revert. This prevents metric noise from being misread as regression during incremental improvement.
- `complexity_budget.max_lines_factor` — the Autolearn Engine rejects a proposed spine that exceeds `current_spine_lines × max_lines_factor`. This implements the autoresearch simplicity criterion: reject changes that multiply complexity for marginal metric gain.

---

### §5.6 Revision (`rev/`) Lifecycle

The `rev/` directory is the append-only record of every state the workflow has been in. No revision is ever deleted by engram.

**Rules:**

1. Every autolearn round creates `rev/rN/` where N = max(existing revision numbers) + 1.
2. `rev/rN/` is a complete snapshot: `spine.<ext>`, `workflow.md`, `fixtures/`, `metrics.yaml`, and `outcome.tsv`.
3. `rev/<rev>/outcome.tsv` is append-only within a revision. One row per fixture run in that revision; rows accumulate across multiple passes of the test suite against that revision.
4. The `current` symlink moves atomically to `rev/rN/` only when the new revision passes dual evaluation: static score ≥ 60/100 (SPEC compliance + fixtures parseable + no secrets) and performance score ≥ threshold/40 (fixtures pass + primary metric improves beyond `tolerance`). The dual-evaluation rubric is specified in `DESIGN.md §5.3`.
5. Failed revisions remain on disk. The `current` symlink does not point to them. They are audit evidence that can be inspected with `engram workflow history <name>`.
6. Manual rollback: `engram workflow rollback <name> --to=rN` re-points `current` to `rev/rN/`. No files are deleted.
7. Revisions are never deleted by `engram`. Physical removal to `~/.engram/archive/workflows/<name>/rev/rN/` requires an explicit operator action (`engram workflow archive-rev <name> --rev=rN`).

**The ratchet invariant.** The primary metric at `current` is monotonically non-degrading in the direction declared by `ratchet_rule.direction`. If autolearn cannot produce a revision that improves the metric within tolerance, `current` stays at its existing revision. The metric at `current` never regresses beyond `tolerance` as a result of automated action; only an explicit manual rollback can move `current` to a revision with a worse metric.

**Phase gate.** After K=5 consecutive autolearn rounds (successful or not), the engine pauses and writes a diff summary to the review queue (`engram review`). A human must confirm before the next phase begins. This is the autoresearch phase gate applied to workflow evolution.

---

### §5.7 Lifecycle States

Workflows participate in the same lifecycle as Memory assets:

```
draft → active → stable → deprecated → archived → tombstoned
```

**Workflow-specific transition rules:**

| Transition | Trigger |
|---|---|
| `draft → active` | `engram workflow validate <name>` passes: structure is correct and at least one fixture runs to completion (not necessarily passing). |
| `active → stable` | Primary metric is within a 5% band for N=10 consecutive autolearn rounds. The metric has stopped improving — the workflow has converged. |
| `active → deprecated` | Explicit operator action (`engram workflow deprecate <name>`), **or** the spine fails all fixtures after a dependency upgrade. In the second case, engram auto-flags the workflow as `needs-attention`; it does not auto-demote. Demotion requires operator confirmation. |
| `stable → deprecated` | Same as `active → deprecated`. |
| `deprecated → archived` | N=180 days without any invocation (`runs.jsonl` shows no entries in 180 days) and operator confirmation. |
| `archived → tombstoned` | 6 months in `archived` state with zero referrers (no `workflow_ptr` Memory assets pointing to it) and operator confirmation. |

**`needs-attention` flag.** This is not a lifecycle state — it is a boolean frontmatter flag (`needs_attention: true`) added by engram when the spine fails fixtures after an external change (dependency upgrade, environment change). It does not demote the lifecycle state; it signals that the workflow requires human review before the next autolearn round runs.

---

### §5.8 Complete Example: `git-merge` Workflow

A complete minimal example. File paths are relative to `<project>/.memory/workflows/git-merge/`.

**`workflow.md`:**

```markdown
---
name: git merge (squash, changelog, notify)
description: squash-merge a feature branch into main with changelog entry and release notification
type: workflow
scope: team
spine_lang: python3
spine_entry: spine.py
inputs_schema: schemas/inputs.json
outputs_schema: schemas/outputs.json
metric_primary: merge_time_seconds
lifecycle_state: active
created: 2026-03-01
updated: 2026-04-18
tags: [git, merge, release]
---

## Purpose

Encodes the platform team's standard merge procedure: pre-merge checks, squash-merge with a conventional commit message, CHANGELOG.md entry generation, and release notification. Replaces the informal checklist that was previously stored as a `feedback` Memory.

## When to use

When merging any feature branch into `main` on a platform service repository. Do not use for documentation-only branches or hotfix branches (those have separate workflows).

## Expected outcome

Branch is squash-merged into `main`. A CHANGELOG.md entry is appended. A release summary is posted to the configured notification channel. `merge_time_seconds` is recorded in the metrics tracker. Target: p95 merge time ≤ 90 seconds.

## Failure modes

- **Rebase conflict**: spine exits with `status: failure`, `failure_mode: rebase_conflict`. Repo is left in a clean state (no partial merge, no detached HEAD). Caller resolves the conflict manually and re-runs.
- **Coverage gate failure**: spine exits with `status: failure`, `failure_mode: coverage_gate`. No merge is attempted. Caller fixes coverage and re-runs.
- **Notification timeout**: spine exits with `status: success` but `warnings` includes `notification_timeout`. Merge succeeded; caller checks the notification channel manually.

## Why this approach

Squash merge is mandatory on this team because a linear `main` history simplifies bisect. The CHANGELOG step is inlined (not a separate workflow) because merge and changelog are atomic: a merge without a CHANGELOG entry is a partial completion. The simplicity criterion (see `metrics.yaml`) prevents the autolearn engine from adding additional steps without a significant metric improvement.
```

**`spine.py`:**

```python
# spine.py
import subprocess

def main(inputs: dict) -> dict:
    repo_url = inputs["repo_url"]
    source_branch = inputs["source_branch"]
    target_branch = inputs["target_branch"]

    t_start = inputs["invocation_time_epoch"]

    result = subprocess.run(
        ["git", "merge", "--squash", source_branch],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"status": "failure", "failure_mode": "rebase_conflict", "metrics": {}}

    t_end = _now_epoch()
    return {
        "status": "success",
        "metrics": {"merge_time_seconds": t_end - t_start},
        "artifacts": [],
        "trace": [f"squash-merged {source_branch} into {target_branch}"],
    }

def _now_epoch() -> float:
    import time
    return time.time()
```

**`fixtures/success-case.yaml`:**

```yaml
name: clean merge without conflicts
inputs:
  repo_url: git@github.com:acme/service-a.git
  source_branch: feature/add-widget
  target_branch: main
  invocation_time_epoch: 1714000000
expected:
  status: success
  metrics:
    merge_time_seconds:
      max: 120
assertions:
  - type: metric_threshold
    metric: merge_time_seconds
    op: le
    value: 120
  - type: no_exception
```

**`metrics.yaml`:**

```yaml
metrics:
  - name: merge_time_seconds
    aggregation: p95
    unit: seconds
    source: outcome_field
    field: metrics.merge_time_seconds

primary: merge_time_seconds

ratchet_rule:
  direction: minimize
  tolerance: 0.02

complexity_budget:
  max_lines_factor: 1.5
```

---

### §5.9 Relationship to `workflow_ptr` Memory

The `workflow_ptr` Memory subtype (§4.6) is the lightweight discoverable surface for a Workflow. `MEMORY.md` loads into every LLM session and must stay small; the full `workflow.md` and spine are loaded only when a task actually matches. The `workflow_ptr` bridges this: it gives the LLM just enough information — what the workflow does, when to use it, expected outcome — to decide whether to load the full procedure.

In practice: `MEMORY.md` contains a reference to `[[local/workflow_ptr_git_merge]]`. The LLM reads the `workflow_ptr` body during startup. When the task involves merging a branch, the LLM loads the full `workflow.md` from `workflows/git-merge/`. When the task is ready to execute, it invokes `engram workflow run git-merge --inputs='{"repo_url":...}'`, which calls `main(inputs)` in `spine.py` and records the outcome in `journal/runs.jsonl`.

The `workflow_ptr` is the entry point; the Workflow directory is the implementation. Neither is complete without the other.

---

---

## 6. Knowledge Base Asset Format

### §6.0 Overview

A Knowledge Base (KB) article is engram's format for **extended domain material** — the kind of reference a developer reads deliberately, navigates by section, and returns to when the domain touches their work. Unlike Memory, which is a single atomic assertion, and unlike Workflow, which is an executable procedure, KB is multi-chapter prose: architecture guides, migration runbooks, onboarding references, design rationale documents.

**Authorship model:** Humans write the primary material (chapters). The engram tool periodically compiles a compact `_compiled.md` digest that the Relevance Gate loads quickly without reading every chapter in full. The digest is a **cached derivation** — always reproducible from the chapters, never authoritative on its own. The chapters are the source of truth.

**Inspiration:** Karpathy's LLM Wiki pattern — write-side synthesis that compounds over time. Each time a chapter is updated, the digest is recompiled; cross-references are already resolved; the LLM arrives with synthesis in hand rather than rediscovering it from raw documents on every query.

**Where KB fits:** if a topic needs chapters, it belongs in KB, not Memory. Use Memory for a single rule or fact. Use KB when the material is the kind of thing you'd open in a browser and scroll through. The `_compiled.md` digest is the KB's contribution to quick-recall; it replaces the pattern of creating a "summary Memory" for a complex domain.

---

### §6.1 Directory Layout

A KB article is a **directory**, not a single file. The layout inside `<scope-root>/kb/<topic>/` is:

```
<scope-root>/kb/<topic>/
├── README.md                       # article entry point (required)
├── 01-overview.md                  # first chapter (at least one required)
├── 02-architecture.md              # additional chapters (numbered for stable ordering)
├── 03-migration-guide.md
├── assets/                         # binary attachments (images, PDFs, diagrams)
│   ├── arch-diagram.svg
│   └── flowchart.png
├── _compiled.md                    # LLM-generated digest (auto-maintained)
└── _compile_state.toml             # compilation metadata (source hashes, timestamp)
```

`<scope-root>` is one of:

| Scope | Root path |
|-------|-----------|
| `project` | `<project>/.memory/` |
| `team` | `~/.engram/team/<name>/` |
| `org` | `~/.engram/org/<name>/` |
| `pool` | `~/.engram/pools/<name>/` |
| `user` | `~/.engram/user/` |

Chapter files are named `NN-slug.md` where `NN` is a zero-padded two-digit sequence number. The numbering creates a stable, human-predictable read order. New chapters are appended at the end; gaps are allowed (e.g., `01`, `02`, `05`) but MUST be reflected in `README.md`'s `chapters` list.

The `assets/` directory MUST be a direct child of the article directory. No `../` escapes are permitted in asset references. Binary attachments are stored by reference — never inlined as base64 in markdown bodies.

---

### §6.2 `README.md` Format

Every KB article requires a `README.md` at the article root. It is the discovery surface: the Relevance Gate reads it to decide whether to load the full article.

**Required frontmatter:**

```yaml
---
name: "Platform Observability Runbook"
description: "Reference for metrics pipeline, alert routing, and on-call procedures. ≤150 chars."
type: kb
scope: project
primary_author: "eng-ops@example.com"
chapters:
  - 01-overview.md
  - 02-architecture.md
  - 03-runbooks.md
compiled_from:
  - README.md
  - 01-overview.md
  - 02-architecture.md
  - 03-runbooks.md
compiled_at: "2026-04-18T12:00:00Z"
lifecycle_state: active
---
```

**Frontmatter field reference:**

| Field | Type | Semantics |
|-------|------|-----------|
| `name` | string | Article title; used in graph and UI display |
| `description` | string | ≤150 characters; loaded by Relevance Gate without opening chapters |
| `type` | literal `kb` | Identifies this directory as a KB article |
| `scope` | enum | `org` / `team` / `user` / `project` / `pool` |
| `primary_author` | string | Handle or email of the human primary author |
| `chapters` | list[string] | Ordered chapter filenames; authoritative read order |
| `compiled_from` | list[string] | Files included in the last `_compiled.md` generation (auto-maintained by `engram kb compile`) |
| `compiled_at` | ISO 8601 | Timestamp of the last `_compiled.md` generation (auto-maintained) |
| `lifecycle_state` | enum | `draft` / `active` / `stable` / `deprecated` / `archived` |

**Body structure:** The `README.md` body contains three parts:

1. **Abstract** (1–3 paragraphs): what the article covers, its scope, who the audience is.
2. **Table of contents**: links to each chapter file. May be auto-generated by `engram kb toc`.
3. **`## When to read this`** section: trigger conditions written for the LLM — "Load this article when the task involves X or Y." This is the primary signal the Relevance Gate uses to decide whether to surface the full article.

---

### §6.3 Chapter Files

Each `NN-slug.md` is a self-contained chapter with optional frontmatter and a free-form markdown body.

**Optional frontmatter:**

```yaml
---
title: "Architecture Overview"
updated: "2026-04-18"
sources:
  - "https://internal-wiki.example.com/observability/v2"
---
```

**Body conventions:**

- Standard markdown with wiki-links supported.
- Cross-links to sibling chapters use relative paths: `[See architecture details](02-architecture.md)`.
- References to engram Memory assets use `@memory:<id>` (e.g., `@memory:local/feedback_alerting_policy`).
- References to Workflow assets use `@workflow:<name>` (e.g., `@workflow:deploy-canary`).
- Mermaid diagrams are written inline in fenced code blocks (`\`\`\`mermaid`). External diagrams go in `assets/`.

---

### §6.4 `assets/` Directory

The `assets/` directory holds binary or large-file attachments referenced by chapter bodies.

- **Supported types:** image formats (`png`, `svg`, `jpg`, `webp`), PDFs, code snippets (`.py`, `.ts`, `.sh`), and other static files.
- **Mermaid is inline:** mermaid diagrams belong in chapter bodies as fenced code blocks, not in `assets/`.
- **Reference by path:** chapters reference assets with relative paths — `![Arch diagram](assets/arch-diagram.svg)` — never as inline base64.
- **No escapes:** all asset references MUST be relative to the article directory. Paths containing `../` are a validation error.

---

### §6.5 `_compiled.md` Contract

The compiled digest is a **cached derivation**. It is NOT the authoritative source. `README.md` and the chapter files are authoritative. The `_compiled.md` exists solely to give the Relevance Gate a fast, high-density summary that loads without fetching every chapter.

**Required header block at the top of `_compiled.md`:**

```
<!-- AUTO-GENERATED from chapters. DO NOT EDIT DIRECTLY. -->
<!-- compile-tool: engram kb compile -->
<!-- compiled_at: 2026-04-18T12:00:00Z -->
<!-- compiled_from: README.md, 01-overview.md, 02-architecture.md, 03-runbooks.md -->
<!-- source_hashes: sha256(README.md)=abc123... sha256(01-overview.md)=def456... sha256(02-architecture.md)=789abc... sha256(03-runbooks.md)=fed321... -->
```

**Body constraints:**

- Optimized for LLM retrieval: hierarchical headings aligned with chapter structure, dense but navigable.
- No fixed line cap. The digest is typically a small fraction of the combined chapter length — a synthesis, not a mirror.
- Every chapter MUST have at least one corresponding section heading in the digest. No chapter may be silently omitted.
- Cross-links to source chapters are required where depth is available: `[See chapter 02](02-architecture.md)`. When the LLM needs depth, it follows the link rather than reading the digest further.

**`_compile_state.toml` format:**

```toml
[source]
files = ["README.md", "01-overview.md", "02-architecture.md", "03-runbooks.md"]

[source.hashes]
"README.md"           = "sha256:abc123..."
"01-overview.md"      = "sha256:def456..."
"02-architecture.md"  = "sha256:789abc..."
"03-runbooks.md"      = "sha256:fed321..."

[compile]
at           = "2026-04-18T12:00:00Z"
tool_version = "engram 0.2.0"
model        = "local/none"   # or "anthropic/claude-3-5-sonnet", etc.

[stale]
is_stale   = false
detected_at = null
```

The `model` field records what compiled the digest. `"local/none"` indicates a rule-based (non-LLM) compile. Any Anthropic or third-party model identifier is also valid.

**Staleness detection:** `engram kb compile --check` walks all chapter files listed in `_compile_state.toml`, computes sha256 of each, and compares against `[source.hashes]`. Any mismatch sets `is_stale = true` and records the detection timestamp in `detected_at`. A stale `_compiled.md` is NOT deleted — the previous version still provides value. It is flagged in `engram review` output with a warning.

**Recompile triggers:**

1. **Manual:** `engram kb compile <topic>` — regenerates digest and updates `_compile_state.toml`.
2. **Watcher:** engram's file-mtime watcher (see DESIGN §7.4) detects chapter changes and schedules a recompile.
3. **On-stale-load:** if the Relevance Gate loads `_compiled.md` and detects it is stale, it emits a warning annotation to the LLM context ("this digest is stale as of `<detected_at>`") but does not fail or skip the asset.

---

### §6.6 Complete Example

The following shows a plausible KB article for a billing migration project. All values are illustrative.

**`kb/acme-billing-migration/README.md`**

```markdown
---
name: "ACME Billing Migration Guide"
description: "End-to-end reference for migrating from legacy billing to the v2 payment API. Covers data model changes, rollback procedures, and cutover checklist."
type: kb
scope: project
primary_author: "billing-eng@acme.example.com"
chapters:
  - 01-overview.md
  - 02-data-model.md
  - 03-cutover-runbook.md
compiled_from:
  - README.md
  - 01-overview.md
  - 02-data-model.md
  - 03-cutover-runbook.md
compiled_at: "2026-04-15T09:30:00Z"
lifecycle_state: active
---

## Abstract

The ACME billing system is migrating from the v1 charge API to the v2 payment API. This guide covers the full migration arc: why the migration is happening, the changed data model, and the step-by-step cutover runbook for each environment.

Target audience: engineers on the billing team and on-call SREs who may need to roll back mid-migration.

## Table of Contents

- [01 Overview](01-overview.md) — background, goals, and non-goals
- [02 Data Model](02-data-model.md) — schema diffs, field renames, nullability changes
- [03 Cutover Runbook](03-cutover-runbook.md) — pre-flight, cutover, rollback

## When to read this

Load this article when the task involves:
- Any change to billing charge flows, subscription renewal, or invoice generation
- Debugging payment failures that may stem from v1/v2 API version mismatch
- Planning a deployment that touches `billing-service` or `payment-gateway`
- On-call triage for billing-related alerts
```

**`kb/acme-billing-migration/01-overview.md`**

```markdown
---
title: "Overview"
updated: "2026-04-15"
sources:
  - "https://internal.acme.example.com/billing/v2-migration-rfc"
---

## Why we are migrating

The v1 charge API was built in 2019 and does not support idempotency keys, making retries unsafe. The v2 payment API requires an idempotency key on every charge call and returns structured error codes instead of HTTP status only.

## Goals

- Zero revenue loss during cutover (shadow-mode validation before cutover)
- Rollback achievable within 5 minutes for any environment
- All charge events in `payments.jsonl` for audit

## Non-goals

- Changing pricing logic (separate project)
- Migrating historical invoice PDFs (out of scope)

See [data model changes](02-data-model.md) for the field-level diff.
Reference the org-level retry policy at @memory:org/feedback_payment_retry_policy.
```

**`kb/acme-billing-migration/_compiled.md`**

```markdown
<!-- AUTO-GENERATED from chapters. DO NOT EDIT DIRECTLY. -->
<!-- compile-tool: engram kb compile -->
<!-- compiled_at: 2026-04-15T09:30:00Z -->
<!-- compiled_from: README.md, 01-overview.md, 02-data-model.md, 03-cutover-runbook.md -->
<!-- source_hashes: sha256(README.md)=1a2b3c... sha256(01-overview.md)=4d5e6f... sha256(02-data-model.md)=7a8b9c... sha256(03-cutover-runbook.md)=0d1e2f... -->

# ACME Billing Migration Guide — Digest

**Scope:** migration from v1 charge API to v2 payment API. Load full chapters for procedures.

## Overview [→ 01-overview.md](01-overview.md)

Migrating to v2 for idempotency key support and structured error codes. Goals: zero revenue loss, 5-min rollback, full audit trail. Non-goals: pricing logic, historical PDFs.

## Data Model [→ 02-data-model.md](02-data-model.md)

Key renames: `charge_id` → `payment_id`; `amount_cents` → `amount` (decimal). New required field: `idempotency_key` (UUID). `status` enum extended with `pending_capture`. Nullability: `description` now nullable in v2.

## Cutover Runbook [→ 03-cutover-runbook.md](03-cutover-runbook.md)

Three phases: (1) shadow mode — v2 calls shadow v1, responses compared; (2) cutover — route 100% to v2 per environment (staging → prod); (3) rollback — feature flag flip, drain in-flight v2 requests, re-enable v1 path. Rollback target: ≤5 min.
```

**`kb/acme-billing-migration/_compile_state.toml`**

```toml
[source]
files = ["README.md", "01-overview.md", "02-data-model.md", "03-cutover-runbook.md"]

[source.hashes]
"README.md"              = "sha256:1a2b3c..."
"01-overview.md"         = "sha256:4d5e6f..."
"02-data-model.md"       = "sha256:7a8b9c..."
"03-cutover-runbook.md"  = "sha256:0d1e2f..."

[compile]
at           = "2026-04-15T09:30:00Z"
tool_version = "engram 0.2.0"
model        = "anthropic/claude-3-5-sonnet"

[stale]
is_stale    = false
detected_at = null
```

---

### §6.7 Relationship to Memory and Workflow

KB occupies the space between Memory's single-fact assertions and Workflow's executable procedures. The table below guides the decision:

| Scenario | Choose |
|----------|--------|
| One fact, rule, preference, or pointer | Memory |
| Executable procedure with runnable steps | Workflow |
| Multi-chapter reference the LLM would read when a task touches the domain | KB |
| Quick lookup of what a KB article covers | Use the KB's `_compiled.md` — do NOT create a summary Memory |

**The compile vs. supersede distinction** is important:

- `_compiled.md` is **derived** — always recomputable from the chapter sources. A stale digest is a lag, not a lie; the chapters are still correct. Staleness is surfaced as a warning, not an error.
- Memory `supersedes` is an **authoritative replacement** — the superseded asset is genuinely wrong or outdated and must not be acted on. Supersession is permanent; recompilation is routine.

Avoid creating a Memory asset whose body is a summary of a KB article. That summarization role belongs to `_compiled.md`. A `workflow_ptr` Memory (§4.6) may reference a KB article with a cross-link in its body, but the digest itself stays in the KB.

---

### §6.8 Lifecycle

KB articles follow the same lifecycle state machine as Memory and Workflow assets (§4.4): `draft → active → stable → deprecated → archived`. KB-specific transitions:

| Transition | Condition |
|------------|-----------|
| `draft → active` | `README.md` is present, `chapters` list has ≥1 file, that file exists, and an initial `_compiled.md` has been generated |
| `active → stable` | No substantive chapter edits for 30 days AND the article is referenced by ≥1 Memory or Workflow asset |
| `active/stable → deprecated` | Operator explicitly sets `lifecycle_state: deprecated`, OR all chapter files are deleted |
| `deprecated → archived` | `engram kb archive <topic>` moves the article directory to `~/.engram/archive/kb/<topic>/`; tombstone entry recorded in journal |

A deprecated KB article remains readable and indexable. It is flagged in `engram review` with a deprecation notice. A stale `_compiled.md` in an active article does not change the article's lifecycle state — stale compilation is a maintenance concern, not a lifecycle event.

---

---

## 7. MEMORY.md Hierarchical Landing Index

### §7.0 Overview

Every engram session begins with one file: `.memory/MEMORY.md`. This is the **landing index** — the single document the LLM reads at startup before any other memory asset is considered. Everything else loads on demand via the Relevance Gate.

**Design constraint:** startup context injection must complete in <100ms (performance budget, §20 of glossary). The injected content targets 600–900 tokens, leaving 95% or more of the LLM's context window free for actual work — matching MemPalace's wake-up cost target for L0+L1 content.

**Core idea:** MEMORY.md does not contain every memory. It contains top-level pointers. Rich detail lives in topic sub-indexes (`index/<topic>.md`) and individual asset files, which load only when the Relevance Gate scores them as relevant to the current task.

**v0.1 compatibility note:** v0.1 imposed `MEMORY.md ≤ 200 lines`, forcing all memory references into one capped file. This cap became unworkable as stores grew — a user accumulating thousands of memories over years cannot meaningfully organize them in 200 lines. v0.2 replaces this with a three-level hierarchy that scales without bound while keeping startup cost constant.

The MEMORY.md file remains small not because of a hard cap, but because it holds pointers rather than content. The file can grow as needed; the `engram review` tool surfaces bloat via the percentile length signal (§16 of glossary) when the file outlier-grows relative to its own history.

---

### §7.1 Three-Level Hierarchy

The hierarchy is modeled on MemPalace's 4-layer wake-up stack (L0 identity always loaded / L1 essentials always loaded / L2 on-demand topic / L3 deep search), adapted to engram's markdown filesystem. engram collapses L0 and L1 into a single MEMORY.md landing index and maps L2 and L3 to topic sub-indexes and individual asset files respectively.

| Level | What | Size target | Load timing |
|-------|------|-------------|-------------|
| **L1 — MEMORY.md** | Top-level landing index: scope overview + pointers to topic sub-indexes + inline high-frequency items | ~100 entries or ~150 lines | Always loaded at startup (<100ms) |
| **L2 — `index/<topic>.md`** | Per-topic sub-index listing all assets in one topic area, grouped by asset class | No fixed cap | Loaded when the Relevance Gate selects the topic |
| **L3 — individual assets** | Full Memory, Workflow, and KB files | Any size | Loaded when the Relevance Gate selects the asset |

**Navigation rules:**

1. Every asset is reachable from L1 in at most 2 hops (L1 → L2 → L3) or 1 hop (L1 → L3 for high-frequency items).
2. L1 stays compact; the startup cost target is under 900 tokens of L1 content.
3. L1 MAY pin specific assets inline — promoting them to one-hop reach — for items the LLM needs on every session, such as user identity or critical behavioral rules.
4. L2 topic files are optional. A small store with fewer than 50 assets works correctly with only L1 + L3, omitting the `index/` directory entirely.
5. The Relevance Gate operates at L2 and L3 independently: selecting a topic sub-index does not unconditionally load all its assets.

---

### §7.2 MEMORY.md Format

MEMORY.md uses a fixed section structure. Tools that read or write MEMORY.md MUST preserve this structure. Unknown sections MUST be preserved on rewrite.

**Required top-level sections** (in order):

```markdown
# MEMORY.md

<!-- engram v0.2 landing index. See SPEC.md §7. -->

## Identity

- [User profile](local/user_profile.md) — <one-line hook>

## Always-on rules

- [Push requires explicit confirmation](local/feedback_push_confirm.md) — <hook>
- [No destructive git operations](local/feedback_no_destructive.md) — <hook>

## Topics

### Active work → [index](index/active-work.md) — 12 entries
- [Acme checkout service migration](local/project_acme_checkout_migration.md) — <hook>

### Platform conventions → [index](index/platform.md) — 23 entries

### Reference material → [index](index/reference.md) — 8 entries

## Subscribed pools

- [pool/design-system](pools/design-system/MEMORY.md) — Design System conventions (team-level)
- [pool/kernel-work](pools/kernel-work/MEMORY.md) — Linux kernel development knowledge (user-level)

## Recently added

- [2026-04-18 new rule](local/feedback_recent.md) — 3 days ago
```

**Formatting rules:**

- Top-level sections use `## Identity`, `## Always-on rules`, `## Topics`, `## Subscribed pools`, `## Recently added`.
- Individual entry format: `- [Title](relative-path.md) — one-line hook`
- Topic section headers: `### <name> → [index](index/<topic>.md) — N entries`
- One-line hooks MUST be ≤ 150 characters. The Relevance Gate uses these hooks for scoring before deciding whether to load the full asset.
- The `N entries` count in a topic header is informational and updated by `engram index rebuild`.
- Sections MAY be empty. Empty sections are still required to be present so that tools can locate their insertion points.
- **No 200-line cap.** MEMORY.md should remain compact, but engram does not refuse to write or validate a longer file. The percentile length signal (§16 of glossary) surfaces review candidates without blocking writes.
- Relative paths are resolved from the `.memory/` directory root. All paths MUST be relative — no absolute paths.

**Protected sections:** any content placed inside `<!-- engram:preserve-begin -->` and `<!-- engram:preserve-end -->` markers is never modified or removed by `engram index rebuild`. See §7.4 for details.

---

### §7.3 Topic Sub-Indexes (`index/<topic>.md`)

A topic sub-index (L2) lists all assets belonging to one topic area. It is an optional but strongly recommended intermediate layer for stores with more than 50 assets.

**Format:**

```markdown
# index/platform.md

<!-- Topic: Platform conventions. Auto-generated by `engram index rebuild --topic=platform`. -->

## Memory

- [TypeScript config convention](../local/feedback_ts_config.md) — always use strict mode; tsconfig extends base
- [Monorepo versioning policy](../local/project_monorepo_versioning.md) — packages use independent semver; no lockstep

## Workflows

- [Dependency upgrade procedure](../workflows/dep-upgrade/workflow.md) — run audit, bump patch first, then minor

## Knowledge Base

- [Platform architecture overview](../kb/platform-arch/README.md) — five-layer diagram; data flow from ingestion to API

## Recently modified

- 2026-04-16 [TypeScript config convention](../local/feedback_ts_config.md)
- 2026-04-12 [Monorepo versioning policy](../local/project_monorepo_versioning.md)
```

**Rules for topic sub-indexes:**

- The topic slug (`platform`, `data-pipelines`, `security-review`, etc.) is free-form and convention-based. engram does not enforce a controlled vocabulary.
- Content is grouped by asset class: `## Memory`, `## Workflows`, `## Knowledge Base`. Sections MAY be omitted if a topic has no assets in that class.
- Cross-references use relative paths from the `index/` directory (`../local/...`, `../workflows/...`, `../kb/...`).
- The `## Recently modified` section lists the 5 most recently changed assets in this topic, for quick orientation.
- One-line hooks follow the same ≤ 150 character rule as MEMORY.md entries.
- Sub-indexes have no size cap. A topic with 200 assets simply has a 200-entry index file.

---

### §7.4 Generation and Maintenance

**Auto-generation commands:**

- `engram index rebuild` — regenerate MEMORY.md and all `index/*.md` files from the current asset set. Preserves user-edited "pinned" items via preserve markers. Running this command is idempotent.
- `engram index rebuild --topic=<topic>` — rebuild just one topic sub-index. Useful when a topic has changed but a full rebuild is not needed.
- `engram index check` — validate that all entries in MEMORY.md and topic sub-indexes point to existing files. Reports missing targets as `E-IDX-001` errors (§12 validation).

**Auto-trigger:** when the engram watcher detects an asset add, remove, or rename, it regenerates the affected L1 section and any affected L2 topic sub-indexes. The watcher does not regenerate the full MEMORY.md on every change — only the sections that need updating.

**Preserved user customization:**

MEMORY.md and `index/*.md` files MAY be partially hand-edited. engram's rebuild preserves any content enclosed in preserve markers:

```markdown
<!-- engram:preserve-begin -->
## My custom dashboard
- [My personal notes on onboarding](local/my_onboarding_notes.md) — hand-curated section
- [Active experiments](local/active_experiments.md) — not in any topic bucket
<!-- engram:preserve-end -->
```

Content between `<!-- engram:preserve-begin -->` and `<!-- engram:preserve-end -->` is **never modified or removed** by `engram index rebuild`. The markers themselves are preserved verbatim. Multiple preserve blocks are allowed; each is treated independently.

**Topic classification heuristics (used by `engram index rebuild`):**

1. **Primary:** group by `tags:` frontmatter field. An asset with `tags: [platform, typescript]` appears in both the `platform` and `typescript` topic sub-indexes.
2. **Secondary:** if no `tags:` field, group by Memory subtype (`user` → identity topic, `feedback` → rules topic, `project` → active-work topic, `reference` → reference topic).
3. **Fallback:** alphabetical within the default topic.
4. **Manual override:** define explicit topic assignments in `.engram/topics.toml`. This file is optional; when present, its assignments take precedence over heuristics.

`.engram/topics.toml` example:

```toml
[assignments]
"local/feedback_ts_config.md"   = "platform"
"local/feedback_no_destructive.md" = "always-on"
"local/project_checkout_migration.md" = ["active-work", "platform"]
```

An asset listed in `topics.toml` can belong to multiple topics by providing an array.

---

### §7.5 v0.1 → v0.2 Compatibility

v0.1 stores have a flat `.memory/*.md` layout with `MEMORY.md ≤ 200 lines`. They contain no `index/` subdirectory and no topic sub-indexes.

**Migration path (`engram migrate --from=v0.1`):**

1. All existing `.memory/*.md` asset files are moved to `.memory/local/*.md`, preserving filenames.
2. MEMORY.md is regenerated using v0.2 format, replacing the flat list with the structured `## Identity / ## Always-on rules / ## Topics / ...` sections.
3. If the v0.1 MEMORY.md contained hand-edited sections not recognizable as auto-generated content, the migration tool wraps them in `<!-- engram:preserve-begin -->` / `<!-- engram:preserve-end -->` markers to prevent future rebuild from discarding them.
4. Topic sub-indexes (`index/`) are created only if the store has more than 50 assets. Smaller stores retain flat L1-only navigation.
5. No data is deleted. Migration is strictly additive: new directories, new index files, restructured MEMORY.md. Original asset content is unchanged.

**Read-only v0.1 compatibility window: 6 months from v0.2 release.** During this window, `engram` reads v0.1-format stores and issues a migration warning but does not refuse to operate. After the compatibility window closes, `engram` requires migration before any write operation on a v0.1-format store.

Stores are identified by the `~/.engram/version` file. A v0.1 store has no version file or contains `0.1`. A v0.2 store contains `0.2`.

---

### §7.6 Complete Example

The following example shows a mid-size project store (~500 assets) for a fictional `acme-checkout-service`. This illustrates realistic MEMORY.md density, topic organization, and the L1 → L2 → L3 navigation path.

**`.memory/MEMORY.md`** (~120 lines):

```markdown
# MEMORY.md

<!-- engram v0.2 landing index. See SPEC.md §7. -->

## Identity

- [User profile](local/user_profile.md) — senior full-stack engineer; prefers TypeScript + Go; direct communication style

## Always-on rules

- [No destructive git](local/feedback_no_destructive.md) — never force-push main; never run reset --hard without confirmation
- [Push confirmation required](local/feedback_push_confirm.md) — always ask before git push, even for non-main branches
- [Prefer immutability](local/feedback_immutable.md) — always create new objects; never mutate in place
- [Small files over large](local/feedback_file_size.md) — 200–400 lines typical; 800 max; extract utilities from large files

## Topics

### Active work → [index](index/active-work.md) — 18 entries
- [Checkout migration: phase 2](local/project_checkout_migration_p2.md) — migrating cart service to new pricing engine; ETA 2026-04-25
- [Auth refactor](local/project_auth_refactor.md) — replacing JWT library; blocked on security review

### Platform conventions → [index](index/platform.md) — 31 entries
- [TypeScript strict mode](local/feedback_ts_config.md) — always extend base tsconfig; strict: true required
- [API response format](local/feedback_api_response.md) — always use ApiResponse<T> wrapper with success/data/error fields

### Testing → [index](index/testing.md) — 14 entries
- [Min 80% coverage required](local/feedback_coverage.md) — enforced via CI; no merge below threshold

### Data pipelines → [index](index/data-pipelines.md) — 22 entries

### Reference → [index](index/reference.md) — 12 entries
- [Internal API docs](local/reference_internal_api.md) — https://internal.acme.example/api/v3/docs

## Subscribed pools

- [pool/acme-platform](pools/acme-platform/MEMORY.md) — Acme platform-wide engineering conventions (team-level)
- [pool/security-baseline](pools/security-baseline/MEMORY.md) — Security team mandatory rules (org-level)

## Recently added

- [2026-04-18 immutability rule](local/feedback_immutable.md) — added after code review; applies to all JS/TS code
- [2026-04-16 phase 2 migration](local/project_checkout_migration_p2.md) — phase 1 shipped; phase 2 started
- [2026-04-14 auth refactor](local/project_auth_refactor.md) — new work item

<!-- engram:preserve-begin -->
## My debug notes
- [Flaky test investigation](local/project_flaky_test_notes.md) — personal notes; not tied to a topic
<!-- engram:preserve-end -->
```

**`.memory/index/platform.md`** (~35 lines):

```markdown
# index/platform.md

<!-- Topic: Platform conventions. Auto-generated by `engram index rebuild --topic=platform`. -->

## Memory

- [TypeScript strict mode](../local/feedback_ts_config.md) — always extend base tsconfig; strict: true required
- [API response format](../local/feedback_api_response.md) — always use ApiResponse<T> with success/data/error/meta
- [Monorepo versioning](../local/feedback_monorepo_versioning.md) — independent semver per package; no lockstep releases
- [ESLint baseline](../local/feedback_eslint.md) — extends @acme/eslint-config; no overrides without review
- [Error handling pattern](../local/feedback_error_handling.md) — try/catch with structured logging; never swallow errors silently

## Workflows

- [Dependency upgrade](../workflows/dep-upgrade/workflow.md) — audit first; bump patch; run tests; then minor
- [PR review checklist](../workflows/pr-review/workflow.md) — immutability + types + error handling + coverage

## Knowledge Base

- [Platform architecture](../kb/platform-arch/README.md) — five-layer diagram; ingestion to API; updated 2026-03
- [Deployment runbook](../kb/deployment-runbook/README.md) — blue-green deploy steps; rollback procedure

## Recently modified

- 2026-04-18 [API response format](../local/feedback_api_response.md)
- 2026-04-14 [ESLint baseline](../local/feedback_eslint.md)
```

**Runtime navigation (L1 → L2 → L3):**

When the LLM begins a task involving TypeScript configuration, the Relevance Gate scores MEMORY.md entries and selects the `platform conventions` topic pointer. It loads `index/platform.md` (L2), which lists TypeScript-related assets with their one-line hooks. The Relevance Gate scores those hooks and loads only the assets with the highest relevance scores — for example, `feedback_ts_config.md` and `feedback_error_handling.md` — leaving the remaining 29 platform assets unloaded. This is the L1 → L2 → L3 path in practice.

For tasks involving push behavior, the LLM does not navigate to a topic at all: `feedback_push_confirm.md` is pinned directly in the `## Always-on rules` section (L1 → L3 in one hop).

---

### §7.7 Performance Budgets and Validation

**Performance targets:**

- Startup parse (reading and parsing MEMORY.md) must complete in <100ms. This matches the `Startup context injection` budget in §20 of the glossary.
- MEMORY.md content SHOULD total under 900 tokens of L1 content (soft guidance; not machine-enforced). This leaves 95%+ of a 128k-token context window free for actual work.
- Topic sub-index files (`index/<topic>.md`) have no token cap. They are loaded on demand, not at startup.

**Validation rules:**

- `engram validate` reports `E-IDX-001` for any MEMORY.md entry whose relative path does not resolve to an existing file.
- `engram validate` reports `E-IDX-002` for any topic sub-index entry whose relative path does not resolve to an existing file.
- `engram validate` reports `E-IDX-003` if a topic header in MEMORY.md references an `index/<topic>.md` file that does not exist.
- `engram review` flags MEMORY.md with a length warning if its line count is at or above the 95th percentile of its own rolling history (percentile length signal, §16 of glossary). This is advisory, not a validation error.
- The `N entries` count in a topic header is validated by `engram validate` against the actual count in the corresponding sub-index. A mismatch is reported as a `W-IDX-001` warning (not an error — counts go stale between rebuilds).

---

---

## 8. Scope Model — Two-Axis: Hierarchy + Subscription

### §8.0 Overview

engram's scope model is built on **two orthogonal axes**. Understanding this two-axis structure is the prerequisite for understanding conflict resolution, enforcement, and pool subscriptions.

**Axis 1 — Hierarchy (membership, inherited automatically):**
Four positions ordered from highest generality to most specific: `org > team > user > project`. Membership at each position is determined by the user's real-world affiliations — which organization they belong to, which teams they belong to, who they are, which project they are working in. Higher positions are inherited automatically through membership; no explicit subscription is required.

**Axis 2 — Subscription (topic pools, opt-in, orthogonal):**
`pool` is a fifth label that is not a hierarchy position. A pool is a topic-shared asset store that any subscriber can opt into. The subscriber declares, via `subscribed_at`, at which hierarchy level the pool's content should be treated for conflict resolution purposes. The same pool can be subscribed at different levels by different subscribers.

The five labels used in the `scope:` frontmatter field are: `org / team / user / project / pool`.

**Contrast with v0.1:** v0.1 had two levels — `local` (project) and `shared` (symlink-based pool, undifferentiated). v0.2 extends this to 4 hierarchy positions plus orthogonal pool subscription, enabling team and org-level collaboration without sacrificing project-level specificity. A rule that must apply to every engineer in the company is now expressible as `scope: org` + `enforcement: mandatory`, rather than requiring a separate out-of-band mechanism.

---

### §8.1 Hierarchy Axis

**Four positions — highest generality to most specific:**

| Label | Filesystem location | Who writes | Typical content |
|---|---|---|---|
| `org` | `~/.engram/org/<org-name>/` | Org maintainer (CODEOWNERS) | Company-wide compliance, security policies, mandatory conventions |
| `team` | `~/.engram/team/<team-name>/` | Team maintainer | Team workflows, review conventions, technical standards |
| `user` | `~/.engram/user/` | The user themselves | Personal cross-project preferences, identity, working style |
| `project` | `<project>/.memory/local/` | Project owner | This project only — facts, overrides, project-specific rules |

**Inheritance rule.** Every project automatically sees the union of:
1. All assets in `~/.engram/org/<org-name>/` (if the user belongs to an org)
2. All assets in `~/.engram/team/<team-name>/` for every team the user belongs to
3. All assets in `~/.engram/user/`
4. All assets in `<project>/.memory/local/`

This inheritance is through membership — a user does not subscribe to their own org or teams. Membership is declared once (e.g., `engram org join`, `engram team join`) and applies everywhere.

**Specificity order for conflict resolution (within the same `enforcement` level):**
`project > user > team > org` (project is most specific and wins; org is least specific).

**Cardinality constraints:**
- A user belongs to **0 or 1** `org`. Single org membership is enforced by the filesystem layout: `~/.engram/org/` holds exactly one subdirectory for the active org. (A user who switches employers migrates their org directory.)
- A user may belong to **0 or N** `team`s. Multiple team directories coexist under `~/.engram/team/`. Conflict resolution between two teams' assets at the same enforcement level follows §8.4.
- `user` scope is **always present** and implicit — `~/.engram/user/` always exists.
- A project is always project-scoped to itself — `<project>/.memory/local/` is the project's private namespace.

**Note on the `local/` directory name vs. the `project` scope label.** The folder is named `local/` for brevity; the `scope:` frontmatter value for assets in that folder is `project`, not `local`. These are different identifiers: one is a path, the other is a conflict-resolution label.

---

### §8.2 Subscription Axis

**Pool is orthogonal to hierarchy.** A pool is not between any two hierarchy positions. It is a separate concept: a topic-shared asset store identified by name.

**Storage.** The canonical location for pool assets is `~/.engram/pools/<pool-name>/`. Projects access pool assets via symlinks in `<project>/.memory/pools/<pool-name>/` (the symlink points into the canonical pool directory).

**Subscription declaration.** A subscriber declares its pool subscriptions in `.memory/pools.toml` (for project-level subscriptions) or in `~/.engram/org/<name>/pools.toml` / `~/.engram/team/<name>/pools.toml` / `~/.engram/user/pools.toml` for subscriptions at higher levels:

```toml
[subscribe.design-system]
subscribed_at = "team"
propagation_mode = "notify"   # auto-sync / notify / pinned; see §9
pinned_revision = null

[subscribe.my-dotfiles-notes]
subscribed_at = "user"
propagation_mode = "auto-sync"

[subscribe.acme-checkout-playbook]
subscribed_at = "project"
propagation_mode = "auto-sync"
```

**`subscribed_at` values and their meaning:**

| Value | Meaning |
|---|---|
| `org` | Pool behaves as org-level content for every project in the org. Org maintainer subscribes on behalf of all org members. |
| `team` | Pool behaves as team-level content for every project belonging to that team. Team maintainer subscribes. |
| `user` | Pool behaves as user-level content for all of this user's projects. The user subscribes individually. |
| `project` | Pool behaves as project-level content for this one project only. Project owner subscribes. |

**Frontmatter in pool assets.** Each asset file inside `~/.engram/pools/<name>/` declares `scope: pool` and `pool: <name>`. The `scope: pool` label is fixed in the file itself. The **effective hierarchy level** used in conflict resolution is read from the subscribing consumer's `pools.toml` (`subscribed_at`), not from the asset file. This separation is deliberate: the same pool file can be subscribed at `org` level by one subscriber and at `user` level by another. Their conflict resolution operates independently.

**Cardinality.** A project may subscribe to any number of pools, at any combination of hierarchy levels. There is no limit on the number of pool subscriptions.

**Examples of subscription positioning:**
- Org subscribes to `pool: compliance-checklists` at `subscribed_at: org` → every project in the org sees those assets as org-level mandatory (if `enforcement: mandatory` is set on them).
- Team subscribes to `pool: design-system` at `subscribed_at: team` → every project in that team sees the pool as team-level content.
- Individual user subscribes to `pool: my-dotfiles-notes` at `subscribed_at: user` → only that user's projects see it, at user level.
- Single project subscribes to `pool: acme-checkout-playbook` at `subscribed_at: project` → only that project sees it, as project-level content.

---

### §8.3 Enforcement Levels

**Three levels** govern whether a rule at a higher scope can be overridden by a lower scope.

| Level | Meaning | Override | Typical usage |
|---|---|---|---|
| `mandatory` | Cannot be overridden by a lower scope | `engram validate` errors on any conflicting lower-scope asset | Company security policies, compliance requirements, non-negotiable conventions |
| `default` | May be overridden, but the overriding asset must declare `overrides: <higher-asset-id>` | Missing `overrides:` declaration is a `engram validate` warning | Team conventions, recommended practices, technology standards |
| `hint` | Freely overridable | No declaration needed | Personal preferences, loose suggestions, starting points |

**Frontmatter.** `enforcement:` is required on the `feedback` subtype (§4.3). For all other subtypes, it is optional and defaults to `hint`.

**Override declaration format.** When a lower-scope asset overrides a `default`-enforcement higher-scope asset, the lower asset MUST declare the `overrides:` field:

```yaml
---
type: feedback
scope: project
enforcement: hint
overrides: team/feedback_tabs_over_spaces
---

Use 2-space indents in this project instead of tabs (which the team default prefers).

**Why:** This project's legacy codebase was established with 2-space convention before the team standard was set. Migrating all files would generate noise in blame history.

**How to apply:** All new files and edits in this project use 2-space indentation.
```

The value of `overrides:` is the ID (relative path or canonical ID) of the asset being overridden. `engram validate` checks that:
1. The referenced asset exists.
2. The referenced asset has `enforcement: default` (not `mandatory` — overriding mandatory is always an error regardless of `overrides:` declaration).
3. The overriding asset's scope is more specific than the overridden asset's scope.

**Invariant: a `mandatory`-enforcement asset at any scope level cannot be overridden by any lower scope.** No `overrides:` declaration unlocks this. The only way to change a mandatory rule is to modify it at the scope that owns it.

---

### §8.4 Conflict Resolution Decision Tree

When multiple assets address the same topic or rule, the Relevance Gate and `engram validate` apply the following algorithm in order:

**Decision algorithm:**

1. **`enforcement` level wins absolutely.** `mandatory` beats `default`, which beats `hint`. An asset with `enforcement: mandatory` at any scope wins over any conflicting asset with `enforcement: default` or `hint` at any scope — regardless of specificity. This is an absolute priority, not a tiebreaker.

2. **Within the same `enforcement` level, hierarchy specificity wins.** `project > user > team > org`. The more specific scope wins.

3. **Pool content participates using its `subscribed_at` as the effective hierarchy position.** A pool subscribed at `team` level competes with native team-level assets at team specificity. A pool subscribed at `project` level competes with native project assets at project specificity — and native project still wins over pool-at-project because native assets are resolved first.

4. **Same enforcement level, same hierarchy position, different sources → LLM arbitrates.** Both assets are loaded into context, and the LLM selects the most applicable one given the task. `engram review` flags this situation as a warning, recommending a human set `overrides:` on one asset to make the resolution deterministic.

5. **Same pool, internal conflict → `engram validate` error.** Pool assets must not contradict each other internally. The pool maintainer must resolve the conflict before the pool can be used. This is enforced at pool publish time.

**Worked examples:**

**Example 1: Org-level mandatory vs. project-level hint (mandatory always wins)**
- `~/.engram/org/acme/feedback_no_push_to_main.md` — `scope: org`, `enforcement: mandatory`
- `<project>/.memory/local/feedback_bypass_main_protection.md` — `scope: project`, `enforcement: hint`
- Result: `engram validate` ERROR. The project asset conflicts with a mandatory org-level rule. The project asset cannot override a mandatory rule. The project engineer must remove or modify the project asset.

**Example 2: Team-level default vs. project-level hint with explicit overrides (correct override)**
- `~/.engram/team/platform/feedback_tabs_over_spaces.md` — `scope: team`, `enforcement: default`
- `<project>/.memory/local/feedback_two_space_indent.md` — `scope: project`, `enforcement: hint`, `overrides: team/feedback_tabs_over_spaces`
- Result: OK. The project override is explicit and valid. The Relevance Gate loads the project asset. When both are available, the LLM uses the project's 2-space rule for this project.

**Example 3: Pool (subscribed at team) vs. native project asset**
- Pool asset in `~/.engram/pools/kernel-work/feedback_rebase_before_merge.md` — `scope: pool`; subscriber's `pools.toml` declares `subscribed_at: team`
- `<project>/.memory/local/feedback_merge_commit_preferred.md` — `scope: project`, `enforcement: hint`
- Result: The pool asset acts at team specificity; the project asset acts at project specificity. Project wins (more specific than team). The LLM sees both assets, uses the project's merge-commit preference, and may note the team pool's rebase preference as an alternative.

**Example 4: Two pools at the same hierarchy level (LLM arbitrates)**
- `~/.engram/pools/pool-A/feedback_prefer_tabs.md` — subscribed by user with `subscribed_at: user`
- `~/.engram/pools/pool-B/feedback_prefer_spaces.md` — also subscribed by user with `subscribed_at: user`, conflicts with pool-A's rule
- Result: Both at user specificity, both presumably `enforcement: hint` (or both `default`). LLM arbitrates with both in context; `engram review` flags a warning. Recommended resolution: set `overrides:` on one of them, or unsubscribe from the conflicting pool.

**Invariant.** Given the same asset set and the same `pools.toml`, the decision algorithm always produces the same result. No randomness or session state enters the resolution. Same input → same output.

---

### §8.5 Git-Sync for Org, Team, and Pools

**`~/.engram/org/<org-name>/` and `~/.engram/team/<team-name>/` are git repositories.**

Each is cloned from an upstream remote (a GitHub / GitLab / Gitea repository maintained by the org or team). This makes org and team memories:
- **Versioned:** every change is a commit with a message, author, and timestamp.
- **Auditable:** `git log` shows who changed which rule and when.
- **CODEOWNERS-enforced:** mandatory assets require approval from designated owners before merging.
- **Offline-capable:** all data lives on local disk after initial clone; no network required for day-to-day use.

**Typical workflow for team-level memories:**

```bash
# Join a team (clone the team memory repo to the local machine)
engram team join git@github.com:acme/platform-team-engram.git

# Pull updates from the upstream remote (all teams)
engram team sync

# Pull updates for one specific team
engram team sync platform-team

# Publish local changes to the upstream remote (requires write access)
engram team publish

# Show all team memberships and pending sync status
engram team status
```

The same subcommands exist for org: `engram org join`, `engram org sync`, `engram org publish`, `engram org status`. Because a user belongs to at most one org, `engram org status` shows 0 or 1 entry.

**Pool sync uses the same mechanism:**

```bash
# Subscribe to a pool (clone the pool repo, register in pools.toml)
engram pool subscribe github:acme/design-system-pool

# Pull updates for all subscribed pools
engram pool sync

# Pull updates for one specific pool
engram pool sync design-system

# Publish local pool contributions to the upstream remote
engram pool publish design-system

# Show all pool subscriptions and sync status
engram pool status
```

`engram pool subscribe` clones the pool repository to `~/.engram/pools/<pool-name>/` and writes the subscription entry to the appropriate `pools.toml` (project, user, team, or org depending on who is subscribing).

**CODEOWNERS enforcement for mandatory assets:**

For `org/` and `team/` repositories, the git platform's CODEOWNERS mechanism controls who can commit assets with `enforcement: mandatory`. Attempts to merge a new mandatory asset without approval from the designated maintainers are rejected by the platform's branch protection. Changes to `default` or `hint` assets may be proposed by any team member via pull request; maintainers review and merge.

**Offline operation.** After initial `join` or `subscribe`, all org, team, and pool data resides on local disk. The Relevance Gate and `engram validate` operate fully offline. Network access is required only for `sync` and `publish` operations.

---

### §8.6 Typical Content Distribution

The following table gives a mental model of what content lives at each scope and with what typical enforcement level.

| Content type | Typical scope | Typical enforcement |
|---|---|---|
| "No credentials in code" — company security policy | `org` | `mandatory` |
| Company-wide coding standards | `org` | `default` |
| "Double approval required for main branch merges" — team review rule | `team` | `mandatory` |
| Team-specific technology stack choice | `team` | `default` |
| Shared workflow from an expert team (distributed as a pool) | `pool` (subscribed by team at `team` level) | `default` |
| Personal terminal and editor preferences | `user` | `hint` |
| Personal identity and working style description | `user` | — (not a rule; `user` subtype) |
| Topic knowledge base (e.g., engram design docs, for reference) | `pool` (subscribed by user or project) | — (reference, not a rule) |
| This project's merge strategy | `project` | `hint` or `default` |
| This project's explicit override of a team default | `project` with `overrides:` | any level ≤ the overridden asset's level |

**Minimum viable scope.** A new user working alone needs only `user` and `project`. They do not need an org, any teams, or any pool subscriptions. The two-axis model degrades gracefully: with no org, no teams, and no pools, the resolution logic simplifies to `project > user`.

**Maximum scope.** In a large organization, all five labels can be in use simultaneously. The two-axis model handles this without special cases: the same decision tree (§8.4) applies at any combination of levels.

---

### §8.7 Frontmatter Contract Summary

The following table consolidates which frontmatter fields are required by scope value. This is a rollup view of §4.1's field definitions, organized by scope rather than by field.

| Scope value | Required frontmatter (in addition to common required fields) | Required in `pools.toml` |
|---|---|---|
| `org` | `org: <org-name>` | — |
| `team` | `team: <team-name>` | — |
| `user` | — (no scope-conditional extras) | — |
| `project` | — (no scope-conditional extras) | — |
| `pool` (in pool asset itself) | `pool: <pool-name>` | — |
| — (consumer subscribing to a pool) | — | `subscribed_at: org \| team \| user \| project` |

**Common required fields** (all assets, all scopes): `name`, `description`, `type`, `scope`, `enforcement` (required on `feedback` subtype; optional elsewhere, defaults to `hint`).

**Key invariants enforced by `engram validate`:**
- An asset with `scope: pool` MUST have a `pool:` field matching a known pool directory.
- An asset with `scope: org` MUST have an `org:` field matching the single active org directory.
- An asset with `scope: team` MUST have a `team:` field matching one of the team directories under `~/.engram/team/`.
- An asset declaring `overrides:` MUST reference an asset with `enforcement: default` (not `mandatory`).
- An asset with `enforcement: mandatory` MUST reside at `org`, `team`, or `pool` scope (project-level mandatory is technically allowed but flagged as a `W-SCO-001` warning, since it has no downstream scope to enforce against).

---

---

## 9. Pool Propagation

### §9.0 Overview

When a pool maintainer updates a shared pool — adding new memories, modifying existing assets, or deprecating something — subscriber projects need to learn about and integrate those changes. Pool propagation is the mechanism that governs this flow: who is notified, how updates arrive, and what decisions subscribers must make.

engram v0.2 defines three propagation modes, declared per subscription in `pools.toml`:

- **`auto-sync`** — the subscriber's symlink always points to the pool's `current` revision. When the pool maintainer publishes a new revision, the subscriber automatically sees updated content on the next session start. No approval step is required. This is the default for new subscriptions.

- **`notify`** — the subscriber's symlink still follows the pool's `current` revision, but an event is appended to `~/.engram/journal/propagation.jsonl` for each new revision. The subscriber (human or LLM) reviews the pending notification via `engram review` and explicitly decides: accept, reject, or override-locally. The change is visible in-session immediately, but the notification must be dismissed.

- **`pinned`** — the subscriber's symlink is fixed to a specific revision directory (`rev/rN/`) rather than the pool's `current`. Pool updates do NOT propagate until the subscriber explicitly runs `engram pool update <name> --to=rM`. Used for long-term stability requirements such as release branches or compliance snapshots.

§9.1 defines the revision directory structure. §9.2 gives the full `pools.toml` schema. §9.3 specifies each mode's exact semantics. §9.4 documents the `propagation.jsonl` event format. §9.5 addresses conflict resolution when a new pool revision conflicts with downstream overrides. §9.6 covers reference graph integrity checks. §9.7 provides a complete end-to-end example.

---

### §9.1 Pool Revision Model

Each pool under `~/.engram/pools/<pool-name>/` maintains an immutable revision history in a `rev/` subdirectory:

```
~/.engram/pools/<pool-name>/
├── MEMORY.md
├── rev/
│   ├── r1/
│   │   ├── feedback_rule_a.md
│   │   └── workflow_onboarding.md
│   ├── r2/
│   │   ├── feedback_rule_a.md   # updated content
│   │   ├── feedback_rule_b.md   # new in r2
│   │   └── workflow_onboarding.md
│   └── current -> r2/           # symlink to active revision
├── local/
│   ├── user_*.md
│   ├── feedback_*.md
│   └── ...
├── workflows/<name>/
├── kb/<topic>/
└── .engram-pool.toml            # pool metadata
```

`current` is a relative symlink inside `rev/` that always points to the most recently published revision directory. Subscriber symlinks at `<project>/.memory/pools/<pool-name>` resolve through this chain.

**Publishing a new revision.** The pool maintainer runs:

```bash
engram pool publish <pool-name>
```

The tool performs these steps atomically:

1. Creates `rev/r(N+1)/` as a full snapshot of the pool's working assets.
2. Updates the `current` symlink to point to `r(N+1)/`.
3. Appends a `revision_published` event to `~/.engram/journal/propagation.jsonl`.
4. Commits and pushes to the pool's git remote, if one is configured in `.engram-pool.toml`.

**Immutability invariant.** Once a revision directory is created, its contents are never modified. Corrections and additions go into a subsequent revision. This guarantees that subscribers locked to a specific revision always see identical content across machines.

**`last_synced_rev`.** Each subscription entry in `pools.toml` carries a `last_synced_rev` field. The tool updates this field after each successful sync operation. It is informational — used by `engram pool status` to show how far behind a subscriber is — and is never used in conflict resolution.

---

### §9.2 `pools.toml` Schema

Subscription configuration lives in one of four locations depending on who is subscribing:

```
<project>/.memory/pools.toml    # project-level subscription
~/.engram/user/pools.toml       # user-level subscription
~/.engram/team/<name>/pools.toml  # team-level subscription
~/.engram/org/<name>/pools.toml   # org-level subscription
```

Full schema with all fields:

```toml
# Example: <project>/.memory/pools.toml

[subscribe.design-system]
subscribed_at = "team"          # org | team | user | project
propagation_mode = "notify"     # auto-sync | notify | pinned
pinned_revision = null          # required when propagation_mode = "pinned"; null otherwise
last_synced_rev = "r7"          # tool-maintained; last revision consumer has seen

[subscribe.kernel-work]
subscribed_at = "user"
propagation_mode = "auto-sync"
pinned_revision = null
last_synced_rev = "r12"

[subscribe.acme-checkout-playbook]
subscribed_at = "project"
propagation_mode = "pinned"
pinned_revision = "r3"          # symlink points to rev/r3/ not rev/current
last_synced_rev = "r3"
```

**Field semantics:**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `subscribed_at` | string | yes | Effective hierarchy level for conflict resolution (§8.2). One of `org`, `team`, `user`, `project`. |
| `propagation_mode` | string | yes | One of `auto-sync`, `notify`, `pinned`. Default for new subscriptions: `auto-sync`. |
| `pinned_revision` | string or null | conditional | REQUIRED when `propagation_mode = "pinned"`. MUST be a revision identifier that exists in the pool's `rev/` directory (e.g., `"r3"`). MUST be null when mode is `auto-sync` or `notify`. |
| `last_synced_rev` | string | no | Informational. The tool writes this after each sync. Do not edit manually. |

**Validation.** `engram validate` errors on:
- `propagation_mode = "pinned"` with `pinned_revision = null`
- `propagation_mode != "pinned"` with a non-null `pinned_revision`
- `pinned_revision` referencing a revision directory that does not exist in the pool

---

### §9.3 Mode Semantics

#### Mode 1: `auto-sync` (default for new subscriptions)

The subscriber's symlink at `<project>/.memory/pools/<pool-name>` (or equivalent for user/team/org subscriptions) always resolves through the pool's `rev/current` symlink to the most recent published revision.

When the pool maintainer runs `engram pool publish <pool-name>`:

1. The pool's `rev/current` symlink is updated to `r(N+1)/`.
2. Because the subscriber's symlink ends at `rev/current`, it now resolves to `r(N+1)/` on the next filesystem resolution — which happens at every session start when the Relevance Gate loads context.
3. No approval step. The subscriber receives the new content passively.

**Use for:** low-risk shared resources — reference memory banks, stable workflow templates, broadly-applicable knowledge bases. Assets where the downstream risk of a bad update is low and fast propagation is desirable.

**Failure mode — mandatory conflict.** If a new pool revision introduces an asset with `enforcement: mandatory` that conflicts with an existing subscriber override, `engram validate` in the subscriber's project errors on the next run. The subscriber must: (a) remove the conflicting override, (b) ask the pool maintainer to lower the enforcement to `default`, or (c) switch their subscription to `pinned` at the pre-update revision:

```bash
engram pool subscribe-mode --pool=<name> --mode=pinned --at=r<N>
```

#### Mode 2: `notify` (recommended for rule-heavy pools)

The subscriber's symlink follows the pool's `rev/current` symlink, so updated content is visible in-session immediately after the pool maintainer publishes. However, a `subscriber_notified` event is also appended to `~/.engram/journal/propagation.jsonl` for each new revision that the subscriber has not yet acknowledged.

`engram review` surfaces pending propagation notifications. For each notification, the subscriber decides:

- **accept** — dismiss the notification. No structural change; the subscriber was already seeing the new content. Records a `subscriber_decision` event with `decision: accept`.
- **reject** — dismiss the notification AND switch the subscription to `pinned` at the revision immediately before the update. The subscriber's symlink is re-pointed to the pre-update revision directory. The pool's ongoing updates stop flowing until the subscriber explicitly advances. Records a `subscriber_decision` event with `decision: reject` and the new pinned revision.
- **override-locally** — copy the specific conflicting assets to the subscriber's local scope and edit them with `overrides: pool/<asset-id>` in frontmatter. The subscriber continues to track `current` for other assets. Records a `subscriber_decision` event with `decision: override-locally` and lists the copied assets.

**Notifications batch.** One `subscriber_notified` event is appended per revision bump (not per asset changed). The event includes a diff summary (`added`, `modified`, `removed` counts).

**Mandatory conflict in notify mode.** If the new revision introduces an `enforcement: mandatory` asset that conflicts with a subscriber override, the notification is flagged `"mandatory_conflict": true` in `propagation.jsonl`. `engram review` presents it with an explicit action-required label. The subscriber cannot silently accept a mandatory conflict — the tool requires selecting either reject or override-locally (which must fully resolve the conflict).

**Use for:** rule-heavy pools, feedback pools, workflow pools where downstream subscribers may want to vet changes before fully committing to them. Any pool where a bad update could meaningfully disrupt active work.

#### Mode 3: `pinned`

The subscriber's symlink at `<project>/.memory/pools/<pool-name>` points directly to a specific revision directory — `rev/r<N>/` — rather than to `rev/current`. Pool updates do NOT propagate to this subscriber until they explicitly request an advance.

**Advancing a pinned subscription:**

```bash
# See what revisions are available and what changed
engram pool diff <pool-name> --from=r3 --to=current

# Advance to a specific revision
engram pool update <pool-name> --to=r5

# Advance to the latest available revision
engram pool update <pool-name> --to=current
```

After `engram pool update`, the `pinned_revision` field in `pools.toml` is updated to the new target, and `last_synced_rev` is written.

**Use for:** long-term stability requirements — release branches that must not have their shared rules change mid-release, compliance snapshots that must be audited before any update, or any context where the subscriber needs explicit control over every change.

**Use `engram pool diff` proactively** to monitor what changes have accumulated in a pool while pinned:

```bash
engram pool diff design-system --from=r3 --to=current
# → Shows assets added, modified, removed across r4, r5, r6, ... current
```

---

### §9.4 `propagation.jsonl` Format

`~/.engram/journal/propagation.jsonl` is an append-only JSON Lines file. Each line is a self-contained JSON object. Lines are never modified in place.

**File location:** `~/.engram/journal/propagation.jsonl`

**Event types** and their schemas:

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"revision_published","pool":"design-system","from_rev":"r7","to_rev":"r8","changes":{"added":2,"modified":1,"removed":0},"publisher":"alice@acme.com"}
{"timestamp":"2026-04-18T10:31:15Z","event":"subscriber_notified","pool":"design-system","subscriber":"/home/alice/projects/billing-service","subscriber_scope":"team","pending_since":"r7","mandatory_conflict":false}
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"accept","reviewer":"alice@acme.com","rev":"r8"}
{"timestamp":"2026-04-18T12:00:00Z","event":"propagation_completed","pool":"design-system","subscriber":"/home/alice/projects/billing-service","from_rev":"r7","to_rev":"r8"}
{"timestamp":"2026-04-18T12:05:00Z","event":"override_declared","pool":"design-system","subscriber":"/home/alice/projects/billing-service","asset_id":"pool/feedback_accessibility_review","local_copy":"local/feedback_accessibility_review_local.md"}
```

**Event type reference:**

| Event | When appended | Key fields |
|---|---|---|
| `revision_published` | Pool maintainer runs `engram pool publish` | `pool`, `from_rev`, `to_rev`, `changes`, `publisher` |
| `subscriber_notified` | A `notify`-mode subscriber detects a new revision on sync | `pool`, `subscriber`, `subscriber_scope`, `pending_since`, `mandatory_conflict` |
| `subscriber_decision` | Subscriber acts via `engram review` | `pool`, `subscriber`, `decision` (`accept`/`reject`/`override-locally`), `reviewer`, `rev` |
| `propagation_completed` | Subscription symlink is successfully updated (any mode) | `pool`, `subscriber`, `from_rev`, `to_rev` |
| `override_declared` | Subscriber copies a pool asset locally via override-locally decision | `pool`, `subscriber`, `asset_id`, `local_copy` |

**Retention.** The default retention policy is 2 years. Entries older than the retention period are moved to `~/.engram/journal/archive/propagation-<year>.jsonl` by `engram journal compact`. The active file is never truncated in place; compaction is always an append-and-truncate-archive operation, never a modify-in-place operation.

**Append-only invariant.** Tools MUST only append to `propagation.jsonl`. No line is ever deleted or modified. This makes the file trivially auditable with `git log` and safe to ship to a central logging system without coordination.

---

### §9.5 Conflict Resolution on Propagation

When a new pool revision introduces a change, conflicts may arise with downstream local content. The §8.4 decision tree governs all cases. The following scenarios describe how each propagation mode handles the most common conflict patterns.

**Scenario A: Pool adds a new `mandatory` rule that conflicts with an existing subscriber override**

The pool maintainer adds a new `feedback` asset with `enforcement: mandatory` to a pool that a subscriber previously overrode locally.

- **`auto-sync` mode:** `engram validate` in the subscriber's project errors on the next run. Error code: `E-ENF-001`. The subscriber must do one of: (a) remove the conflicting local override, (b) ask the pool maintainer to lower enforcement to `default`, or (c) run `engram pool subscribe-mode --pool=<name> --mode=pinned --at=<pre-update-rev>` to freeze at the last known-good revision.
- **`notify` mode:** The `subscriber_notified` event has `"mandatory_conflict": true`. `engram review` displays the notification with an `[ACTION REQUIRED]` banner. The subscriber must pick `reject` or `override-locally` (which, for mandatory rules, means the local copy must not conflict — it must complement or extend the rule, not contradict it). Silent `accept` is blocked by the tool.
- **`pinned` mode:** No effect until the subscriber explicitly advances the pinned revision. When they do advance past the revision that introduced the mandatory rule, the conflict check runs at that point.

**Scenario B: Pool modifies an existing `default` rule that a subscriber overrode with `overrides:`**

The pool's `feedback_tabs_over_spaces.md` (enforcement: `default`) changes its body text, but the subscriber's local `feedback_two_space_indent.md` still declares `overrides: pool/feedback_tabs_over_spaces`.

- **All modes:** The subscriber's override remains structurally valid — `overrides:` references the rule ID, not the specific text content of the rule. The override continues to take effect.
- **`notify` and `auto-sync` modes:** `engram review` shows an informational flag: "Pool rule `feedback_tabs_over_spaces` was updated in r8; your override may be stale. Review whether your local override still reflects your intent." This is a warning, not an error.
- **`pinned` mode:** The warning appears only when the subscriber advances past the revision that modified the rule.

**Scenario C: Pool removes a rule that a subscriber's asset `references:`**

A pool asset that another subscriber asset points to via a `references:` frontmatter field is removed in a new pool revision.

- **All modes:** `engram validate` emits a `W-REF-001 reference_rot` warning on the asset that holds the dangling `references:` field. The subscriber's asset is NOT auto-deleted or auto-modified. The downstream owner must decide: update the `references:` field to point to a replacement, mark the asset as deprecated, or remove the reference if it is no longer relevant.
- **`auto-sync` and `notify` modes:** Warning appears on next `engram validate` run after the pool update is resolved.
- **`pinned` mode:** Warning appears only once the subscriber advances past the revision that removed the referenced asset.

**Scenario D: Two pools modify the same topic independently, both subscribed at the same level**

Two pools both contain `feedback` assets addressing the same coding practice (e.g., indentation), both subscribed at `team` level.

- **All modes:** `engram review` flags as a warning: "Potential conflict between `pool-A/feedback_prefer_tabs` and `pool-B/feedback_prefer_spaces` at team scope. Both assets will be loaded; LLM arbitrates." This is §8.4 rule 4 in action.
- Recommended resolution: set `overrides:` on one of the two assets, or unsubscribe from the less-preferred pool for this topic.

---

### §9.6 Reference Graph Integrity

engram v0.2 maintains a reference graph across all assets in `~/.engram/graph.db` (SQLite). The graph tracks every `references:` frontmatter field across org, team, user, project, and pool assets.

**When a pool asset is removed or superseded in a new revision**, the reference graph check runs as part of `engram pool publish` (on the maintainer side) and `engram pool sync` (on the subscriber side):

1. Query `graph.db` for all downstream assets (org, team, user, project, and other pools) that have a `references:` entry pointing to the removed or superseded asset.
2. For each such downstream asset, add a `W-REF-001 reference_rot` warning to the `engram review` queue.
3. DO NOT auto-delete or auto-modify any downstream asset. The reference graph check is read-only with respect to assets.
4. The downstream asset owner decides: update the `references:` field to point to a replacement asset, mark their asset deprecated using `deprecated: true` in frontmatter, or remove the `references:` field if the dependency no longer applies.

**Why read-only.** Automatic modification of subscriber assets based on upstream changes violates the principle that each scope owns its own assets. A pool update cannot reach into a subscriber's `local/` directory and modify files. Only the subscriber can modify their own assets.

**Reference graph update cadence.** `graph.db` is updated on every `engram validate` run, every `engram pool sync`, and every time an asset is written by `engram edit`. It is safe to delete and rebuild: `engram index rebuild --graph` recomputes the full reference graph from the current asset set.

**Primary protection against silent-override.** The reference graph integrity check is the primary mechanism that prevents a pool update from silently invalidating downstream work. Without it, a pool maintainer could rename or delete an asset that dozens of downstream assets depend on, and those dependencies would silently become dangling references, causing inconsistent LLM behavior.

---

### §9.7 Complete Propagation Example

This section walks through a complete end-to-end propagation scenario using generic organization names.

**Setup:**
- Organization `acme` with a shared pool `design-system` currently at revision `r7`
- Team `platform` subscribes to `design-system` at `subscribed_at: team` with `propagation_mode: notify`
- Project `acme-billing-service` belongs to team `platform` and inherits the pool subscription via `~/.engram/team/platform/pools.toml`

**Event:** The `design-system` maintainer (`alice@acme.com`) publishes `r8`, which adds one new `feedback` asset: `feedback_accessibility_review_in_pr.md` with `enforcement: default` — "Always include an accessibility review checklist in pull requests for UI-facing changes."

**Propagation sequence:**

**Step 1 — Publish:**
```bash
# Maintainer's machine
engram pool publish design-system
# → Creates rev/r8/ with full snapshot
# → Updates rev/current → r8/
# → Commits and pushes to git remote
```
Journal entry appended:
```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"revision_published","pool":"design-system","from_rev":"r7","to_rev":"r8","changes":{"added":1,"modified":0,"removed":0},"publisher":"alice@acme.com"}
```

**Step 2 — Subscriber detects new revision:**
```bash
# Subscriber machine (or CI), run periodically or at session start
engram pool sync design-system
# → Detects that pool remote is at r8; local last_synced_rev = r7
# → Because mode = notify, appends subscriber_notified event
# → Does NOT block the symlink update; current already points to r8/
```
Journal entry appended:
```jsonl
{"timestamp":"2026-04-18T10:31:15Z","event":"subscriber_notified","pool":"design-system","subscriber":"/home/alice/projects/billing-service","subscriber_scope":"team","pending_since":"r7","mandatory_conflict":false}
```

**Step 3 — Notification surfaces at session start:**

On the next `engram` session in `acme-billing-service`, the session banner shows:
```
[notify] design-system updated r7 → r8 (1 asset added). Run `engram review` to dismiss.
```

**Step 4 — Subscriber reviews:**
```bash
engram review
# → Shows: design-system r8 notification
# →   Added: feedback_accessibility_review_in_pr.md (enforcement: default)
# →   No mandatory conflicts.
# → Options: [a]ccept  [r]eject  [o]verride-locally
```

**Step 5a — Decision: accept:**
```bash
# Subscriber accepts the update
engram review --pool=design-system --rev=r8 --decision=accept
```
Journal entry appended:
```jsonl
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"accept","reviewer":"alice@acme.com","rev":"r8"}
{"timestamp":"2026-04-18T11:45:01Z","event":"propagation_completed","pool":"design-system","subscriber":"/home/alice/projects/billing-service","from_rev":"r7","to_rev":"r8"}
```
`last_synced_rev` in `pools.toml` is updated to `r8`. The new accessibility rule is now active in all future sessions.

**Step 5b — Counter-example: decision: reject (switch to pinned):**

Suppose the `acme-billing-service` team decides they don't want any pool updates to flow automatically until the next quarterly review. They reject and pin:

```bash
engram review --pool=design-system --rev=r8 --decision=reject
# → Internally runs: engram pool subscribe-mode --pool=design-system --mode=pinned --at=r7
# → Repoints symlink from rev/current to rev/r7/
# → Updates pools.toml: propagation_mode = "pinned", pinned_revision = "r7"
```
Journal entry appended:
```jsonl
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"reject","reviewer":"alice@acme.com","rev":"r8","new_mode":"pinned","pinned_at":"r7"}
```
The project now stays on `r7`. The `r8` accessibility rule is NOT active. Future `engram pool sync` runs note the divergence but do not update the symlink. To advance in the future:
```bash
engram pool diff design-system --from=r7 --to=current
engram pool update design-system --to=r9
```

---

## 10. Cross-Repo Inbox Message Protocol

### §10.0 Overview

When multiple LLM agents work concurrently on related repositories — for example, `acme/service-a` consumes a client SDK published by `acme/service-b` — an agent working in repo A may discover a bug, design flaw, or breaking change that originates in repo B. There must be a structured, point-to-point way for that agent to signal repo B's maintainers and agents, and for B's agents to report resolution back to A.

This mechanism is the **Cross-Repo Inbox**: a directory at `~/.engram/inbox/<repo-id>/` that holds structured messages sent to a repository. Inbox messages are:

- **Point-to-point.** A message goes from one specific sender repo to one specific recipient repo.
- **Transient.** Messages have a lifecycle (`pending → acknowledged → resolved` or `rejected`) and are eventually archived rather than living forever.
- **LLM-authored by default.** The sender is typically an LLM agent that discovered an issue during its normal work. Humans can also send messages via the CLI.

**Vs. pool propagation (§9) — crucial distinction:**

| | Pool propagation | Cross-repo inbox |
|---|---|---|
| Direction | Broadcast (1 publisher → N subscribers) | Point-to-point (A → B) |
| Content | Permanent assets (memories, workflows) | Transient messages (bug reports, questions, update-notifications) |
| Typical author | Human / pool maintainer | LLM agent (discovers during work) |
| Lifecycle | Lives forever (with supersede/archive) | `pending → acknowledged → resolved → archived` |
| Storage | `~/.engram/pools/<name>/` | `~/.engram/inbox/<repo-id>/` |

At session start, the recipient's LLM loads any `pending` inbox messages alongside its memory context: "You have 2 pending cross-repo messages." This is the only place in the format spec where one repository's data enters another repository's context load path — everything else in the scope model is either local or explicitly subscribed via pools.

§10.1 specifies the directory layout. §10.2 defines the message format. §10.3 documents intent semantics. §10.4 specifies the lifecycle state machine. §10.5 covers deduplication and rate limiting. §10.6 defines repo identifier resolution. §10.7 documents the `inter_repo.jsonl` journal format. §10.8 provides a complete end-to-end example. §10.9 covers privacy and security.

---

### §10.1 Directory Layout

```
~/.engram/inbox/<repo-id>/
├── pending/
│   ├── 20260418-103000-from-acme-service-a-bug-001.md
│   └── 20260418-114500-from-acme-service-c-q-002.md
├── acknowledged/
│   └── 20260417-152200-from-acme-service-c-q-004.md
├── resolved/
│   └── 20260416-091100-from-acme-service-a-bug-001.md
└── rejected/
    └── 20260415-083000-from-acme-service-d-spam.md

~/.engram/journal/inter_repo.jsonl            # cross-repo event journal (global)
```

`<repo-id>` is a stable identifier resolved according to §10.6. The four subdirectories under each inbox correspond to the four terminal/transitional states in the lifecycle (§10.4). Messages are never deleted in place; they are moved between subdirectories as their state transitions.

**File naming convention:**

```
<timestamp>-from-<sender-id-slug>-<short-topic>.md
```

Where `<timestamp>` is `YYYYMMDD-HHmmss` (UTC), `<sender-id-slug>` is the sender's repo-id with `/` replaced by `-`, and `<short-topic>` is a 1–4 word slug derived from the message intent and first line of content. Example: `20260418-103000-from-acme-service-a-bug-users-404.md`.

**Archive path.** Resolved messages older than 180 days and rejected messages older than 30 days auto-move to `~/.engram/archive/inbox/<repo-id>/<state>/`. The archive path mirrors the inbox path and is governed by the same no-auto-delete invariant (§3.2).

---

### §10.2 Message Format

Each inbox message is a single `.md` file with YAML frontmatter followed by a structured body.

**Required frontmatter fields:**

| Field | Type | Semantics |
|---|---|---|
| `from` | string | Sender repo-id (resolved per §10.6) |
| `to` | string | Recipient repo-id (resolved per §10.6) |
| `intent` | enum | `bug-report` / `api-change` / `question` / `update-notify` / `task` — see §10.3 |
| `status` | enum | `pending` / `acknowledged` / `resolved` / `rejected` — must match the subdirectory the file lives in |
| `created` | ISO 8601 | When the sender composed the message (UTC) |
| `message_id` | string | Globally unique ID: `<sender-repo-id>:<YYYYMMDD-HHmmss>:<4-char-nonce>`. Used for dedup and reply threading. |

**Optional frontmatter fields:**

| Field | Type | Semantics |
|---|---|---|
| `severity` | enum | `info` / `warning` / `critical` — default `info`. Affects ordering in `engram review`. |
| `deadline` | ISO 8601 | When the sender needs resolution by. Shown in `engram review` with a countdown. |
| `related_memory_ids` | list[string] | Memory IDs in the sender's store that provide context. Recipient can request these IDs if repos share a network-accessible engram export endpoint (future; not in v0.2). |
| `related_code_refs` | list[string] | Code locations in the form `path/to/file.py:L42@<git-blob-sha>`. The git blob sha pins the exact version the sender observed. |
| `dedup_key` | string | Override auto-dedup hash. Two messages with the same `dedup_key`, `to`, and `intent` are considered duplicates (§10.5). |
| `reply_to` | string | `message_id` of a previous message this message responds to. Creates a thread visible in `engram inbox list --thread=<id>`. |
| `duplicate_count` | integer | Auto-incremented by engram when a duplicate is merged (§10.5). Not set by senders; managed by the CLI. |
| `acknowledged_at` | ISO 8601 | Set by `engram inbox acknowledge` when transitioning to `acknowledged`. |
| `resolved_at` | ISO 8601 | Set by `engram inbox resolve` when transitioning to `resolved`. |
| `resolution_note` | string | Free-text note added by `engram inbox resolve --note="..."`. |
| `rejected_at` | ISO 8601 | Set by `engram inbox reject`. |
| `rejection_reason` | string | Reason added by `engram inbox reject --reason="..."`. |

**Body structure:**

```markdown
<one-line summary — the LLM-visible headline>

**What:** <the specific observation, request, or report>

**Why:** <why this matters to the recipient — impact on them>

**How to resolve (if actionable):** <concrete suggestion or request>
```

All four body sections are expected for `bug-report`, `api-change`, and `task` intents. The "How to resolve" section MAY be omitted for `question` and `update-notify` intents where no specific action is expected.

**Complete example message file:**

```markdown
---
from: acme/service-a
to: acme/service-b
intent: bug-report
status: pending
created: 2026-04-18T10:30:00Z
message_id: "acme/service-a:20260418-103000:7f3a"
severity: warning
related_code_refs:
  - "src/api/users.py:L42@abc123def456"
deadline: 2026-04-25T00:00:00Z
---

GET /api/users returns empty array instead of 404 for missing IDs

**What:** When calling `GET /api/users?id=nonexistent-id`, the endpoint returns
`200 OK` with an empty array `[]` instead of `404 Not Found`. This is observable
at `src/api/users.py:L42` (git blob `abc123def456`).

**Why:** `acme/service-a` treats an empty-array response as "no results found" and
silently skips further processing. When the actual user ID is valid but temporarily
unavailable, `service-a` loses the data without any error logged. This causes silent
data loss in our order pipeline.

**How to resolve:** Return `404 Not Found` with a JSON body
`{"error": "user not found", "id": "<queried-id>"}` when the user does not exist.
Empty array should only be returned for collection endpoints with zero results, not
for by-ID lookups.
```

---

### §10.3 Intent Semantics

The five `intent` values are not merely labels: they carry expectations about how the recipient should respond and in what timeframe.

| Intent | Meaning | Recipient action expectation |
|---|---|---|
| `bug-report` | Sender encountered a reproducible defect in the recipient's code or API while consuming it | Investigate; confirm whether it is a bug or intentional; if a bug, fix and `resolve` with a commit reference; if intentional, `resolve` with an explanation or `reject` with rationale |
| `api-change` | Sender needs or proposes a change to the recipient's public interface | Triage; either accept (reply with a plan or a PR reference via `resolve`) or `reject` with a design rationale |
| `question` | Sender needs information that only the recipient's maintainers / agents know | Answer in a reply message (`reply_to`); mark original as `resolved` with the answer in `resolution_note` |
| `update-notify` | Sender informs the recipient of an upstream change already made that affects them | Acknowledge receipt; take action if needed; `resolve` when the recipient has adapted to the change |
| `task` | Sender asks the recipient to perform a specific, bounded action | Triage; accept or `reject` with an explicit rationale; `resolve` when done |

**Priority ordering in `engram review`.** When multiple pending messages exist, `engram review` orders them by: `severity` (critical → warning → info), then `intent` (bug-report and task before question and update-notify), then `deadline` (earliest first), then `created` (oldest first). This ordering is defined here so that all compliant implementations produce the same review queue.

**Effect on context loading.** At session start, the recipient's memory context loader includes all `pending` inbox messages in the context pack under a dedicated `## Pending Cross-Repo Messages` heading. Only `pending` messages are loaded; `acknowledged`, `resolved`, and `rejected` messages are not loaded into context automatically (they are available via `engram inbox list`).

---

### §10.4 Lifecycle

**States:**

- **`pending`** — the message has been sent and lives in the recipient's `pending/` subdirectory. It is visible in `engram review` and loaded into the recipient's session context.
- **`acknowledged`** — the recipient (LLM or human) has confirmed receipt and taken responsibility for acting on it. The message is moved to `acknowledged/`. The sender sees a `message_acknowledged` event in `inter_repo.jsonl` on their next `engram review`.
- **`resolved`** — the recipient has completed the requested or implied action. The message is moved to `resolved/` with a `resolution_note`. The sender sees a `message_resolved` event on their next `engram review`.
- **`rejected`** — the recipient has explicitly declined to act, with a reason. The message is moved to `rejected/`. The sender sees a `message_rejected` event on their next `engram review`.

**State transition diagram:**

```
pending ──► acknowledged ──► resolved
   │              │
   └──────────────┴──────────► rejected
```

Transitions are one-way: a `resolved` or `rejected` message cannot be re-opened. If the same issue recurs, the sender should compose a new message with `reply_to` pointing to the original `message_id`.

**Transition actions (CLI):**

```bash
# Recipient acknowledges receipt
engram inbox acknowledge <message-id>

# Recipient resolves with a note
engram inbox resolve <message-id> --note="Fixed in commit abc123; GET /api/users now returns 404 for missing IDs."

# Recipient rejects with a reason
engram inbox reject <message-id> --reason="Intentional behavior: empty array is our documented contract for collection endpoints."
```

Each transition appends an event to `~/.engram/journal/inter_repo.jsonl` (§10.7).

**Reverse notification.** The sender does not poll for resolution. Instead, on their next `engram review` or `engram status` call, the CLI scans `inter_repo.jsonl` for events on messages the sender composed and surfaces any transitions since the last session. This produces output like:

```
Cross-repo inbox — updates since last session:
  ✓ RESOLVED  acme/service-b: GET /api/users 404 fix (msg acme/service-a:20260418-103000:7f3a)
              Note: Fixed in commit abc123; GET /api/users now returns 404 for missing IDs.
```

**Auto-archive.** Resolved messages older than 180 days are automatically moved to `~/.engram/archive/inbox/<repo-id>/resolved/` on the next `engram review` run. Rejected messages older than 30 days are moved to `~/.engram/archive/inbox/<repo-id>/rejected/`. Auto-archive appends a `message_archived` event to `inter_repo.jsonl`. No message is ever deleted by the auto-archive process.

---

### §10.5 Deduplication and Rate Limiting

**Deduplication rule.** Two messages are considered duplicates if they share the same `to` repo-id and `intent`, AND at least one of:

1. Same `dedup_key` (if explicitly set by the sender).
2. Same SHA-256 hash of the sorted `related_code_refs` list (if non-empty in both messages).
3. Same SHA-256 hash of `<from>:<first-line-of-body>` (fallback when neither `dedup_key` nor `related_code_refs` is available).

When `engram inbox send` detects a duplicate in the recipient's `pending/` subdirectory, it does **not** create a new file. Instead:

1. The new message body is appended to the existing file as a new paragraph with a `<!-- duplicate received <timestamp> -->` HTML comment.
2. The `duplicate_count` frontmatter field is incremented by 1.
3. A `message_duplicated` event is appended to `inter_repo.jsonl`.
4. `engram inbox send` exits with a `0` status but prints: `Duplicate detected — merged into existing message <message-id> (now duplicate_count=N).`

This approach preserves all information while preventing inbox flooding from repeated identical observations.

**Rate limiting.** To prevent misbehaving or runaway LLM agents from flooding a recipient's inbox:

- **Pending cap:** At most 20 `pending` messages from the same sender may exist in the same recipient's inbox at any time (configurable per-user in `~/.engram/config.toml` as `inbox.max_pending_per_sender`; default 20).
- **24h window:** At most 50 messages total (including duplicates that were merged) may be sent from the same sender to the same recipient within any 24-hour UTC window (configurable as `inbox.max_per_sender_per_day`; default 50).

Rate limits are per `(sender, recipient)` pair. When a limit is exceeded, `engram inbox send` exits with a non-zero status and prints:

```
Rate limit exceeded: acme/service-a → acme/service-b
  Pending: 20/20  |  24h window: 47/50
  Either wait for the recipient to process messages, or use 'engram inbox list --to=acme/service-b' to review and deduplicate.
```

The `rate_limit_hit` event is appended to `inter_repo.jsonl` regardless.

---

### §10.6 Repo Identifier Resolution

`<repo-id>` is resolved in the following order:

1. **Explicit config.** If the project's `.engram/config.toml` contains `repo_id = "acme/service-b"`, that string is used verbatim. Explicit repo-id is strongly recommended for long-lived projects: it survives repository renames, host migrations, and remote URL changes.

2. **Git remote hash.** If no explicit `repo_id` is configured, engram computes `sha256(git remote get-url origin)[:12]` (lowercase hex). This is stable as long as the git remote URL does not change.

3. **Path hash (fallback).** If there is no git remote (e.g., a local-only project), engram computes `sha256(realpath(<project-root>))[:12]`. This is stable as long as the project directory does not move.

**Configuring repo_id.** Add the following to `.engram/config.toml` in the project root:

```toml
[project]
repo_id = "acme/service-b"    # stable human-readable identifier; no spaces; slashes allowed
```

**Discovery.** `engram inbox list-repos` shows all repos that have sent or received messages on this machine, derived from `inter_repo.jsonl`. This is a journal-derived view, not a directory listing — repos that have been archived out of the active inbox still appear in the history.

**Recipient address book.** The CLI maintains a local address book (`~/.engram/inbox/.address_book.toml`) populated from `inter_repo.jsonl` that maps known repo-ids to their last-known config-specified names. This makes tab-completion for `--to=` work without a network call.

---

### §10.7 `inter_repo.jsonl` Format

`~/.engram/journal/inter_repo.jsonl` is a global, append-only JSON Lines file at the user level. It records every inbox event across all repos on the machine.

**Event schema:**

Every line is a JSON object. Required fields on every event:

| Field | Type | Present on |
|---|---|---|
| `timestamp` | ISO 8601 string | All events |
| `event` | string (event type) | All events |
| `message_id` | string | All events except `rate_limit_hit` |
| `from` | string (repo-id) | All events |
| `to` | string (repo-id) | All events |

**Event types and their additional fields:**

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"message_sent","from":"acme/service-a","to":"acme/service-b","intent":"bug-report","severity":"warning","message_id":"acme/service-a:20260418-103000:7f3a"}
{"timestamp":"2026-04-18T14:15:00Z","event":"message_acknowledged","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","acknowledged_by":"bob@acme.com"}
{"timestamp":"2026-04-19T09:00:00Z","event":"message_resolved","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","resolution_note":"Fixed in PR #123","commit_sha":"abc123def456"}
{"timestamp":"2026-04-20T11:00:00Z","event":"message_rejected","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","rejection_reason":"Intentional behavior per API contract v2."}
{"timestamp":"2026-04-18T10:35:00Z","event":"message_duplicated","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","duplicate_count":2}
{"timestamp":"2026-04-18T10:40:00Z","event":"rate_limit_hit","from":"acme/service-a","to":"acme/service-b","limit_type":"pending_cap","current":20,"limit":20}
{"timestamp":"2026-09-20T00:00:00Z","event":"message_archived","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","archive_path":"~/.engram/archive/inbox/acme-service-b/resolved/20260418-103000-from-acme-service-a-bug-users-404.md"}
```

**Complete event-type reference:**

| Event type | When | Additional fields |
|---|---|---|
| `message_sent` | Sender calls `engram inbox send` | `intent`, `severity` |
| `message_acknowledged` | Recipient calls `engram inbox acknowledge` | `acknowledged_by` |
| `message_resolved` | Recipient calls `engram inbox resolve` | `resolution_note`, `commit_sha` (optional) |
| `message_rejected` | Recipient calls `engram inbox reject` | `rejection_reason` |
| `message_duplicated` | Sender sends a duplicate; merged into existing | `duplicate_count` (new total) |
| `rate_limit_hit` | Send attempted but rate limit exceeded | `limit_type` (`pending_cap` or `daily_window`), `current`, `limit` |
| `message_archived` | Auto-archive runs and moves a file | `archive_path` |

All timestamps are UTC. The file is append-only; no tool may edit or delete lines.

---

### §10.8 Complete Example

**Setup:**
- Agent A works on `acme/service-a` (an order-processing service).
- Agent B works on `acme/service-b` (provides a `/api/users` endpoint that A calls to validate customer IDs).
- Both repos are on the same developer machine.
- `acme/service-a` has `repo_id = "acme/service-a"` in `.engram/config.toml`.
- `acme/service-b` has `repo_id = "acme/service-b"` in `.engram/config.toml`.

**Step 1 — Agent A discovers the bug.**

While running `acme/service-a`'s test suite, Agent A observes that `GET /api/users?id=nonexistent` returns `200 []` instead of `404`. Agent A composes a message:

```bash
engram inbox send \
  --to=acme/service-b \
  --intent=bug-report \
  --severity=warning \
  --deadline=2026-04-25 \
  --code-ref="src/api/users.py:L42@abc123def456" \
  --message="GET /api/users returns empty array instead of 404 for missing IDs"
```

**Step 2 — Message file created.**

engram writes `~/.engram/inbox/acme-service-b/pending/20260418-103000-from-acme-service-a-bug-users-404.md` with the frontmatter and body shown in §10.2.

**Step 3 — Journal entry appended.**

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"message_sent","from":"acme/service-a","to":"acme/service-b","intent":"bug-report","severity":"warning","message_id":"acme/service-a:20260418-103000:7f3a"}
```

**Step 4 — Agent B's next session.**

When Agent B starts a new engram session, `engram review` shows:

```
Pending cross-repo inbox messages (1):
  ⚠ WARNING  [bug-report]  from acme/service-a
             GET /api/users returns empty array instead of 404 for missing IDs
             Deadline: 2026-04-25  |  Code ref: src/api/users.py:L42@abc123def456
             ID: acme/service-a:20260418-103000:7f3a
```

The message is also injected into Agent B's session context under `## Pending Cross-Repo Messages`.

**Step 5 — Agent B acknowledges and investigates.**

```bash
engram inbox acknowledge acme/service-a:20260418-103000:7f3a
```

The file moves from `pending/` to `acknowledged/`. Journal entry:

```jsonl
{"timestamp":"2026-04-18T14:15:00Z","event":"message_acknowledged","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","acknowledged_by":"bob@acme.com"}
```

**Step 6 — Agent B fixes the bug and resolves.**

Agent B finds the bug at `src/api/users.py:L42`, fixes it, and commits `abc123def456` → new commit `def789`. Then:

```bash
engram inbox resolve acme/service-a:20260418-103000:7f3a \
  --note="Fixed in commit def789abc. GET /api/users now returns 404 Not Found for missing IDs. Released in service-b v1.4.2."
```

The file moves from `acknowledged/` to `resolved/`. Journal entry:

```jsonl
{"timestamp":"2026-04-19T09:00:00Z","event":"message_resolved","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","resolution_note":"Fixed in commit def789abc. GET /api/users now returns 404 Not Found for missing IDs. Released in service-b v1.4.2.","commit_sha":"def789abc"}
```

**Step 7 — Agent A's next session sees the resolution.**

On Agent A's next `engram review`:

```
Cross-repo inbox — updates since last session:
  ✓ RESOLVED  acme/service-b: GET /api/users 404 fix (msg acme/service-a:20260418-103000:7f3a)
              Note: Fixed in commit def789abc. GET /api/users now returns 404 Not Found for
              missing IDs. Released in service-b v1.4.2.
```

Agent A can now update its own code to handle the `404` response correctly, knowing the upstream fix is in place.

---

### §10.9 Privacy and Security

**Inbox is local.** Messages in `~/.engram/inbox/` never leave the user's machine automatically. There is no automatic sync, forwarding, or relay in v0.2. Future versions may introduce opt-in network sync (e.g., via a shared git remote for a team's inbox), but that is explicitly out of scope for v0.2.

**Path information in `related_code_refs`.** Code references include local file paths (e.g., `src/api/users.py:L42`). Organizations with strict information classification policies should be aware that these paths may reveal internal directory structure or module names if inbox content is ever exported or shared. In v0.2 there is no automatic export; this is a human-to-consider note, not an engram-enforced restriction.

**Append-only transitions.** Messages are never edited after composition. State transitions (pending → acknowledged → resolved / rejected) move the file to a new subdirectory and append fields (`acknowledged_at`, `resolved_at`, `resolution_note`, etc.), but do not modify the original `from`, `to`, `intent`, `created`, or `message_id` fields. This preserves a tamper-evident record of what was sent and when.

**No automatic forwarding.** Agent A's message to `acme/service-b` is never auto-routed to `acme/service-c` or any other repo. Cross-repo messages require explicit addressing; there is no broadcast mode and no CC field. Any forwarding is a manual human action.

**`inter_repo.jsonl` is user-global.** The journal at `~/.engram/journal/inter_repo.jsonl` records all inbox events across all repos on the machine. Tools that export or sync this file should treat it with the same sensitivity as commit history or personal productivity logs.

---

---

## 11. Consistency Contract

### §11.0 Overview

An engram store grows without bound over time. This is by design: quality maintenance is achieved through the Consistency Engine, not through capacity caps. Without active monitoring, however, an unbounded store will accumulate contradictions — facts that disagree, rules that conflict, references to resources that no longer exist, workflows that call tools that have changed, and assets that silently supersede one another without acknowledgment. Left unaddressed, these inconsistencies degrade the LLM's ability to reason reliably from the store.

The Consistency Engine solves this problem without auto-deletion and without auto-mutation. It scans the store, classifies every detected issue into one of seven canonical conflict classes, and produces a **proposal** — a structured, journaled record of the issue and its suggested remediations. All execution is left to the operator.

**Core principles:**

1. **Detect, don't mutate.** The Consistency Engine only proposes. It never modifies an asset's content, moves a file, or changes any frontmatter field without an explicit operator command.
2. **Every proposal is journaled.** All detection events and all resolution decisions are appended to `~/.engram/journal/consistency.jsonl`. The audit trail is complete and tamper-evident.
3. **Seven canonical conflict classes.** Any inconsistency the system detects falls into exactly one of the seven classes defined in §11.1. The taxonomy is exhaustive for v0.2; new classes require a spec revision.
4. **Evidence-driven, not heuristic.** Classifications are grounded in the confidence fields defined in §4.8, the reference graph maintained in `graph.db`, and the temporal validity fields (`valid_from:`, `valid_to:`, `expires:`). No classification is made purely from word-matching.

This chapter specifies the **contract** the Consistency Engine must honor. **DESIGN §5.2** specifies the four-phase scan algorithm (static analysis, semantic clustering, LLM-assisted review, fixture execution), the embedding strategy, and the LLM prompts used to evaluate clusters. Tools implementing this contract may vary their detection algorithms, but MUST produce proposal objects that conform to the schema in §11.2 and MUST never auto-mutate assets.

---

### §11.1 Seven Conflict Classes

The seven classes below form the canonical taxonomy of consistency issues in an engram store. Each class has a fixed `class` identifier used in proposal objects, a default severity, a detection signal summary, and one example (using generic names).

#### 1. `factual-conflict`

**Definition.** Two or more assets assert different facts about the same subject. Neither has declared `supersedes:` on the other; neither is in `deprecated` or `archived` state. Both are active and both would be loaded into LLM context for the same topic.

**Detection signal.** Semantic clustering (DBSCAN on embeddings) identifies assets with high topic similarity. Within each cluster, LLM-assisted review identifies pairs or groups that make contradictory factual assertions. Detection occurs during the semantic clustering phase of the four-phase scan (DESIGN §5.2).

**Default severity.** `warning`

**Example.** Memory A (`local/project_billing_db_choice`) says "the billing service uses MySQL." Memory B (`pool/design-system/feedback_postgres_only`) says "all services in the platform use Postgres." Both are `active`. Neither references the other.

**Resolution options.** `update` (correct one asset) / `supersede` (declare one supersedes the other) / `merge` (combine into a single asset) / `archive` (move one or both to archive) / `dismiss` (mark as false positive).

---

#### 2. `rule-conflict`

**Definition.** Two `feedback`, `agent`, or team-scoped assets prescribe contradictory actions for the same situation. This differs from `factual-conflict` in that the assets are normative (rules about what to do) rather than descriptive (facts about what is true). Note: §8.4's decision tree resolves rule conflicts at load time by hierarchy and enforcement level; `rule-conflict` proposals surface the unresolved conflict when the decision tree cannot produce a deterministic result or when two `mandatory` rules contradict each other.

**Detection signal.** Same-topic LLM review on clustered `feedback` and `agent` assets. Detection checks for logical contradiction between the rule bodies. Flagged when: (a) both assets are at the same enforcement level and same hierarchy position, (b) neither declares `overrides:` pointing to the other, and (c) LLM review confirms contradictory prescriptions.

**Default severity.** `warning` for same-scope conflicts at `default` or `hint` enforcement / `error` for conflicts involving two `mandatory` assets at the same scope.

**Example.** Feedback A (`user/feedback_rebase_before_merge`) prescribes "always rebase before merging a feature branch." Feedback B (`user/feedback_merge_commit_preferred`) prescribes "always use merge commits, never rebase." Both are `scope: user`, `enforcement: default`. Neither declares `overrides:`.

**Resolution options.** Add `supersedes:` to the newer asset pointing to the older / add `overrides:` on the more-specific asset / `merge` into one rule with conditional application / `archive` the outdated rule.

---

#### 3. `reference-rot`

**Definition.** An asset with a `references:` frontmatter field, or a `reference`-subtype asset whose body points to an external resource, contains a reference that no longer resolves. The target may be a URL, a file path, a git SHA, or another asset ID.

**Detection signal.** Periodic crawl run during the static analysis phase (DESIGN §5.2). For each `references:` field and each URL/path in `reference`-subtype bodies: validate URL reachability (HTTP 2xx), file path existence, git SHA existence in the declared repository, and asset ID resolution in `graph.db`.

**Default severity.** `info` if the reference is declared in an optional `references:` field / `warning` if the reference is in a required frontmatter field (e.g., `workflow_ref:` in a `workflow_ptr` asset) / `error` if a workflow spine's `memory read` call targets a non-existent asset ID.

**Example.** A `reference`-subtype memory (`local/reference_upstream_monitoring_tool`) was written six months ago pointing to a GitHub repository at `github.com/acme-internal/monitor-v2`. The repository has since been deleted. The asset remains `active`.

**Resolution options.** `update` (replace the URL/path with a current one) / `archive` (the resource is gone; retire the reference asset) / `supersede` (a new reference asset has already been written; link the old to the new).

---

#### 4. `workflow-decay`

**Definition.** A Workflow asset's `spine.*` calls a tool, invokes a path, or depends on an external service that no longer works as expected. The workflow's `fixtures/` test cases fail or produce unexpected output when executed.

**Detection signal.** Fixture execution during the fixture execution phase (DESIGN §5.2). The Consistency Engine runs the workflow's fixture suite in a sandboxed environment (`~/.engram/workspace/consistency-run-<id>/`). A fixture failure triggers a `workflow-decay` proposal. Partial failures (some fixtures pass, some fail) produce `warning`; total failure produces `error`.

**Default severity.** `error` if all fixtures fail / `warning` if some fixtures fail.

**Example.** A workflow for container deployment calls `kubectl v1.29 rollout status`. The host machine has been upgraded to `kubectl v1.31`, which removed a flag the spine uses. The fixture that validates the rollout check now exits non-zero.

**Resolution options.** `update` (revise the spine and fixtures to match the current environment, then re-run autolearn) / `archive` (the workflow is obsolete) / `escalate` (the workflow owner must decide if the environmental change is temporary or permanent).

---

#### 5. `time-expired`

**Definition.** An asset carries a `valid_to:` or `expires:` date in its frontmatter that has passed, but the asset is still in `active` state and is still referenced by other active assets or workflows. The asset is effectively stale by its own declaration.

**Detection signal.** Date comparison in the static analysis phase. For every asset with `valid_to:` or `expires:` present: compare the declared date to today's date. If today > declared date and the asset is not already `deprecated` or `archived`, check whether any other active asset references it (via `graph.db`).

**Default severity.** `info` if the asset is not referenced by any active asset / `warning` if the asset is referenced by one or more active assets or active workflows.

**Example.** A project memory (`local/project_sprint_q1_requirements`) was written in January 2026 with `valid_to: 2026-03-31`. It is now April 18, 2026. Three active workflow `workflow_ptr` assets reference it via their `references:` field.

**Resolution options.** `update` (replace the content with current requirements and extend or remove `valid_to:`) / `supersede` (create a new asset for the current sprint and add `supersedes: local/project_sprint_q1_requirements`) / `archive` (the sprint is over; nothing new should reference the asset).

---

#### 6. `silent-override`

**Definition.** A newer asset (by `created:` or `updated:` date) covers the same topic as an older asset and effectively supersedes it in practice — but the newer asset does not declare `supersedes:` pointing to the older one. The older asset remains `active` and would be loaded alongside the newer one into LLM context, creating an implicit redundancy or contradiction.

**Detection signal.** Semantic clustering identifies the pair (both in the same cluster, high similarity). Comparison of `created:` / `updated:` timestamps identifies which is newer. Absence of `supersedes:` on either asset confirms the silent nature. LLM review within the cluster confirms the newer one covers or contradicts the older one.

**Default severity.** `warning`

**Example.** In January 2026, a feedback asset (`user/feedback_naming_snake_case`) prescribes "prefer snake_case for all variable names." In April 2026, a new feedback asset (`user/feedback_naming_kebab_case`) is written, prescribing "prefer kebab-case for all identifiers." No `supersedes:` link exists on either.

**Resolution options.** Add `supersedes: user/feedback_naming_snake_case` to the newer asset / `merge` both into a single asset with explicit applicability conditions / `archive` the older asset if the newer one is authoritative / `dismiss` if both are intentionally in force in different contexts (and add `limitations:` to each to clarify).

---

#### 7. `topic-divergence`

**Definition.** Multiple assets on the same topic reach inconsistent conclusions that do not add up to a coherent picture. This is a generalization of `factual-conflict`: rather than a binary "A says X, B says not-X," `topic-divergence` captures the case where three or more perspectives on the same topic are individually plausible but collectively incoherent. No single pair is necessarily a direct contradiction; the whole cluster fails to converge.

**Detection signal.** Cluster-level LLM review (DESIGN §5.2) assigns a `divergence_score` to each semantic cluster. A cluster with three or more assets and a divergence score above the configured threshold triggers a `topic-divergence` proposal. The threshold is configurable (default: 0.6 on a 0–1 scale).

**Default severity.** `info` if the divergence may be intentional (e.g., assets represent multiple valid design trade-offs) / `warning` if the divergence is likely unintentional (assets on a topic where a single canonical answer is expected).

**Example.** Three project memories address "best way to structure integration tests": Memory A says "co-locate tests with source in `*_test.go`"; Memory B says "keep tests in a top-level `tests/` directory"; Memory C says "use a `testdata/` directory per package." All three are `active`. None references or supersedes another.

**Resolution options.** Promote the cluster to a KB article (§6) that synthesizes the trade-offs into a single, coherent policy / keep the assets as intentional distinct perspectives and add `limitations:` to each clarifying when each applies / `archive` the weaker alternatives if consensus exists / `supersede` with a new single-source-of-truth asset.

---

### §11.2 Detection Output Format

Every consistency detection produces a **proposal object**. Proposals are the unit of communication between the Consistency Engine and the operator. They are stored in the journal (§11.3), returned by `engram consistency scan`, and displayed in `engram review`.

**Proposal schema:**

```json
{
  "proposal_id": "cp-2026041809321500-a1b2c3",
  "detected_at": "2026-04-18T09:32:15Z",
  "class": "factual-conflict",
  "severity": "warning",
  "involved_assets": [
    "local/project_billing_db_choice",
    "pool/design-system/feedback_postgres_only"
  ],
  "summary": "Billing service database choice conflicts with team-wide Postgres-only rule",
  "evidence": {
    "semantic_cluster_id": "cluster-7",
    "confidence_scores": {
      "local/project_billing_db_choice": 0.82,
      "pool/design-system/feedback_postgres_only": 0.95
    },
    "contradiction_text": "project says 'MySQL'; team feedback says 'Postgres-only mandatory'"
  },
  "suggested_resolutions": [
    {
      "action": "update",
      "target": "local/project_billing_db_choice",
      "rationale": "team rule is mandatory; project must comply"
    },
    {
      "action": "supersede",
      "target": "local/project_billing_db_choice",
      "with": "pool/design-system/feedback_postgres_only"
    },
    {
      "action": "dismiss",
      "rationale": "false positive; proposal was overly broad"
    }
  ],
  "status": "open"
}
```

**Field semantics:**

| Field | Type | Required | Semantics |
|---|---|---|---|
| `proposal_id` | string | MUST | Format: `cp-<YYYYMMDDHHmmssSSS>-<6-hex>`. Globally unique. |
| `detected_at` | ISO 8601 UTC | MUST | Timestamp when the proposal was created. |
| `class` | string enum | MUST | One of the seven class identifiers from §11.1. |
| `severity` | string enum | MUST | `info` / `warning` / `error`. See §11.1 per-class defaults. |
| `involved_assets` | string[] | MUST | List of asset IDs (relative to store root). At least one asset. |
| `summary` | string | MUST | Single human-readable sentence describing the conflict. |
| `evidence` | object | MUST | Detection evidence. Required sub-fields depend on class (see below). |
| `suggested_resolutions` | object[] | MUST | At least one resolution suggestion. |
| `status` | string enum | MUST | Initial value always `open`. |

**`evidence` sub-fields by class:**

| Class | Required evidence fields |
|---|---|
| `factual-conflict` | `semantic_cluster_id`, `confidence_scores`, `contradiction_text` |
| `rule-conflict` | `semantic_cluster_id`, `confidence_scores`, `contradiction_text` |
| `reference-rot` | `broken_reference` (the exact URL/path/ID that failed), `check_type` (`url`/`path`/`sha`/`asset-id`), `last_checked_at` |
| `workflow-decay` | `fixture_run_id`, `failed_fixtures` (list), `exit_codes` |
| `time-expired` | `declared_expiry` (the `valid_to:` or `expires:` value), `active_referrers` (list of asset IDs still referencing this asset) |
| `silent-override` | `semantic_cluster_id`, `older_asset`, `newer_asset`, `date_delta_days` |
| `topic-divergence` | `semantic_cluster_id`, `divergence_score`, `asset_count` |

**`suggested_resolutions[].action` enumeration:**

| Action | Semantics |
|---|---|
| `update` | Edit the named asset's content. Operator supplies the new text; LLM may draft. |
| `supersede` | Add `supersedes:` frontmatter to the newer asset pointing to the older. Older transitions to `deprecated`. |
| `merge` | Combine two or more assets into one new asset; originals transition to `deprecated`. |
| `archive` | Move the named asset to `archive/` (retention policy applies; minimum 6-month floor). |
| `dismiss` | Mark the proposal as a false positive. The same evidence pair will not trigger a new proposal for 90 days. |
| `escalate` | Defer to a human with ownership of the scope; remove the proposal from the LLM's attention queue. |

**Status transitions:**

```
open → in_review → resolved
                 → dismissed
                 → expired   (if proposal age > 90 days without resolution)
```

A proposal in `expired` state is moved to the archive journal section; the operator receives a final reminder in `engram review`.

---

### §11.3 `consistency.jsonl` Journal Format

All Consistency Engine events are recorded in append-only JSONL at `~/.engram/journal/consistency.jsonl`. This is the audit trail for all proposals, reviews, and resolutions.

**File location:** `~/.engram/journal/consistency.jsonl`

**Format:** One JSON object per line. Each line is a single event record.

**Event records:**

```jsonl
{"timestamp":"2026-04-18T09:32:15Z","event":"proposal_created","proposal_id":"cp-20260418093215-a1b2c3","class":"factual-conflict","severity":"warning","involved":["local/project_billing_db_choice","pool/design-system/feedback_postgres_only"]}
{"timestamp":"2026-04-18T14:10:00Z","event":"proposal_reviewed","proposal_id":"cp-20260418093215-a1b2c3","reviewer":"alice@acme.com","decision":"update","resolution_asset":"local/project_billing_db_choice"}
{"timestamp":"2026-04-18T14:10:30Z","event":"proposal_resolved","proposal_id":"cp-20260418093215-a1b2c3","applied_action":"update","resolved_by":"alice@acme.com"}
```

**Event types:**

| Event | When written |
|---|---|
| `proposal_created` | When the Consistency Engine creates a new proposal |
| `proposal_reviewed` | When an operator (human or LLM) selects an action from `suggested_resolutions` |
| `proposal_resolved` | When the chosen action has been applied and the proposal transitions to `resolved` |
| `proposal_dismissed` | When an operator marks the proposal as a false positive (`action: dismiss`) |
| `proposal_expired` | When a proposal reaches 90 days old without resolution; status set to `expired` |

**Required fields per event:**

| Event | Required fields |
|---|---|
| `proposal_created` | `timestamp`, `event`, `proposal_id`, `class`, `severity`, `involved` |
| `proposal_reviewed` | `timestamp`, `event`, `proposal_id`, `reviewer`, `decision` |
| `proposal_resolved` | `timestamp`, `event`, `proposal_id`, `applied_action`, `resolved_by` |
| `proposal_dismissed` | `timestamp`, `event`, `proposal_id`, `dismissed_by`, `reason` |
| `proposal_expired` | `timestamp`, `event`, `proposal_id`, `age_days` |

**Append-only invariant.** Lines in `consistency.jsonl` are never modified or deleted. Resolved and dismissed proposals retain their full history indefinitely in the live journal. Compaction — moving old resolved/dismissed entries to `~/.engram/archive/journal/consistency-<YYYY>.jsonl` — occurs after 2 years. Compaction is a copy-then-truncate operation; the original entries exist in the archive before the live journal is shortened.

**Re-detection.** If the Consistency Engine detects the same evidence pair (same `involved_assets` + same `class`) as an existing `open` or `in_review` proposal, it does NOT create a duplicate. Instead, it appends a `proposal_re_detected` event to the journal and updates the existing proposal's `detected_at` to the new timestamp. If the matching proposal is in `dismissed` state and fewer than 90 days have passed since dismissal, no new proposal is created. After 90 days, dismissal expires and a new `proposal_created` event is written.

---

### §11.4 Confidence and Evidence

The Consistency Engine's classifications are evidence-driven. This section explains how the confidence fields from §4.8 feed into detection decisions and how confidence values are updated through the system's use.

**Confidence score formula** (canonical definition in §4.8; restated here for §11 context):

```
confidence_score = (validated_count - 2 × contradicted_count - staleness_penalty)
                   / max(1, total_events)

where:
  total_events     = validated_count + contradicted_count
  staleness_penalty = 0.0  if last_validated is within 90 days of today
                   | 0.3  if last_validated is within 365 days of today
                   | 0.7  if last_validated is older than 365 days
```

**How confidence scores feed the Consistency Engine:**

- A high-confidence asset (`score > 0.7`) involved in a `factual-conflict` increases the proposal severity: the LLM has repeatedly confirmed the high-confidence asset, making the contradiction more actionable.
- A low-confidence asset (`score < 0`) involved in a `factual-conflict` or `rule-conflict` reduces the proposal severity to `info`: the asset may already be unreliable; the conflict may not matter.
- `evidence.confidence_scores` in the proposal object (§11.2) reports the scores of all `involved_assets` at detection time.

**When confidence updates:**

An LLM invocation that uses asset X in its context may trigger a confidence update depending on the outcome:

- **Positive outcome** (task completes successfully; user confirms): `validated_count++`, `last_validated = now`, `usage_count++`
- **Negative outcome** (reality contradicts the asset; user explicitly corrects): `contradicted_count++`, `usage_count++`
- **Neutral** (asset was loaded but outcome is not tracked): `usage_count++` only

**Who reports outcomes:**

- **LLM agents** via `engram memory validate-use <id> --outcome=success|failure` (called from a workflow spine's post-run hook or from an adapter's completion hook).
- **Humans** via `engram review` (thumbs-up / thumbs-down on assets surfaced in recent session).
- **Consistency Engine itself** via outcome heuristics: if an asset is involved in a proposal that is dismissed as a false positive, this is a weak positive signal (the asset's content was valid; the proposal was wrong). The engine may increment `validated_count` by 1 with a note in the evidence. This is the only case where the engine touches an asset's frontmatter — and only the `confidence` sub-fields, never the body or any other frontmatter.

**Staleness-driven proposals:**

Assets with `confidence_score < 0` AND `last_validated` older than 365 days are candidates for automatic proposal generation:
- If the asset has `valid_to:` set and the date has passed: propose `time-expired`.
- If newer assets on the same topic exist in the semantic cluster: propose `topic-divergence`.

**Safety invariant: NEVER auto-archive on low confidence.** A negative confidence score surfaces the asset in `engram review` for human decision. The engine creates a proposal and stops. It does not move the file, does not change `state:` in frontmatter, and does not suppress the asset from future LLM contexts.

---

### §11.5 Remediation Workflow

This section describes the end-to-end lifecycle of a proposal from detection to resolution, as experienced by the operator.

**Step 1 — Detection (background).**

The Consistency Engine runs its four-phase scan as a background process (see DESIGN §5.2 for scheduling and phase sequence). When a conflict is detected, a proposal object (§11.2) is created and written to `consistency.jsonl` as a `proposal_created` event. No asset is touched.

**Step 2 — Surface (`engram review`).**

The `engram review` command aggregates all open proposals from `consistency.jsonl` and displays them ordered by severity (`error` first, then `warning`, then `info`), then by `detected_at` (oldest first within each severity group). The summary line and the `involved_assets` list give the operator a quick read on each issue.

**Step 3 — Review.**

The operator selects a proposal to inspect. `engram consistency report <proposal-id>` shows the full proposal object including evidence details.

**Step 4 — Resolve.**

The operator issues a resolution command:

```bash
# Correct one asset to match the other
engram consistency resolve <proposal-id> --action=update \
  --asset=local/project_billing_db_choice

# Declare the newer asset supersedes the older
engram consistency resolve <proposal-id> --action=supersede \
  --older=local/project_billing_db_choice \
  --newer=pool/design-system/feedback_postgres_only

# Merge two assets into a new one
engram consistency resolve <proposal-id> --action=merge \
  --assets=user/feedback_naming_snake_case,user/feedback_naming_kebab_case \
  --into=user/feedback_naming_convention

# Archive a stale or outdated asset
engram consistency resolve <proposal-id> --action=archive \
  --asset=local/project_sprint_q1_requirements \
  --reason="Sprint Q1 is over; requirements superseded by Q2 planning doc"

# Mark as false positive
engram consistency resolve <proposal-id> --action=dismiss \
  --reason="Assets apply to different contexts; conflict is not real"

# Escalate to scope owner
engram consistency resolve <proposal-id> --action=escalate
```

**Step 5 — Apply.**

The chosen action is executed: relevant assets are modified (for `update`, `supersede`, `merge`), moved to `archive/` (for `archive`), or the proposal is marked `dismissed` / `escalated`. A `proposal_reviewed` event and a `proposal_resolved` (or `proposal_dismissed`) event are appended to `consistency.jsonl`.

**Step 6 — Audit trail.**

The proposal's full history — evidence at detection time, operator decision, and resolution — is permanently recorded in `consistency.jsonl`. Post-resolution queries (`engram consistency report <proposal-id>`) continue to return the complete record.

**Auto-expire rule (backlog management without auto-mutation):**

A proposal that remains `open` for more than 90 days is automatically transitioned to `expired`. The operator receives a final reminder in `engram review`. The `proposal_expired` event is written to `consistency.jsonl`. An expired proposal is no longer shown in the default `engram review` view but is accessible via `engram review --include-expired`.

**Re-detection behavior.** If the same conflict is detected again after a proposal for it has `expired` or after a `dismiss` expiry of 90 days, the Consistency Engine creates a new `proposal_created` event (new `proposal_id`). The previous expired/dismissed proposal is referenced in the new proposal's `evidence` field as `prior_proposal_id`.

---

### §11.6 Non-Goals and Safety Invariants

This section states explicitly what the Consistency Engine does not do. These are non-negotiable invariants. A tool that violates any of them is not a conforming implementation.

**What the Consistency Engine does NOT do:**

- **Never auto-deletes.** Archive operations happen only when an operator explicitly issues `--action=archive` in a resolution command. The engine has no autonomous archive capability.
- **Never auto-edits asset content.** The `update` action in a resolution command causes the operator (or an LLM acting under operator instruction) to supply new content. The engine itself does not write new body text to any asset file.
- **Never auto-applies proposals.** No proposal transitions from `open` to `resolved` without an explicit operator resolution command. Background processing does not consume its own proposals.
- **Never runs during session-critical paths.** Consistency scans are scheduled as background processes. The engine does not run inline during a `Relevance Gate` evaluation, an LLM context pack, or any path where the LLM is waiting for a response.
- **Does not optimize for zero false positives.** The engine errs toward surfacing more proposals (higher recall) rather than suppressing uncertain detections (higher precision). A missed real conflict is more harmful than a noisy proposal that an operator dismisses.

**Safety invariants:**

- An asset's physical file is **never modified** by the Consistency Engine without an explicit operator command. This applies to body content, frontmatter fields, filename, and directory location.
- The only exception is the `confidence` sub-fields in frontmatter (§11.4): the engine may increment `validated_count` by 1 when a proposal for an asset is dismissed as a false positive. This exception is strictly bounded: no other frontmatter field may be modified by the engine.
- The engine runs in a **sandboxed workspace** (`~/.engram/workspace/consistency-run-<id>/`) per DESIGN §3.6. Fixture execution for `workflow-decay` detection occurs in this sandbox, never in the live workflow directory.
- Proposals for assets with `enforcement: mandatory` are routed to the **scope maintainer** (the identity declared in the scope's CODEOWNERS or equivalent), not consumed by subscribers. A subscriber cannot resolve a proposal against a mandatory asset they do not own.
- Archive retention floor: any asset moved to `archive/` via a consistency resolution command retains its full content for a minimum of **6 months** before physical removal is permitted. This is the same retention floor applied to all archive operations across the system.

---

### §11.7 Integration Points

The Consistency Engine intersects with the following parts of the engram system. This table is a cross-reference guide; each row names the integration and the SPEC section governing the counterpart.

| Integration point | What the engine uses / produces | SPEC chapter |
|---|---|---|
| Asset confidence fields | `validated_count`, `contradicted_count`, `last_validated`, `usage_count` from frontmatter feed into evidence scoring | §4.8 |
| Reference graph (`graph.db`) | Engine queries the graph to detect `reference-rot` and to check inbound reference counts before proposing `archive` | §3.3, §4.1 |
| Inbound reference guard | Assets with inbound references cannot be proposed for deletion (archive); MUST 4 of §3.3 applies to consistency proposals as well | §3.3 |
| Scope model enforcement | An asset's `enforcement:` level affects the severity assigned to proposals (mandatory conflicts escalate to `error`) | §8.3 |
| Temporal validity fields | `valid_from:` / `valid_to:` / `expires:` trigger `time-expired` proposals | §4.1, §4.8 |
| Pool propagation | Cross-pool asset sets are included in semantic clustering; divergence between pool and subscriber can surface as `factual-conflict` or `topic-divergence` | §9.5 |
| Inbox | For `update-notify` intent messages, the engine can surface a related `silent-override` or `topic-divergence` proposal via the inbox mechanism | §10.3 |
| Autolearn Engine (workflow) | Fixture failures that Autolearn cannot automatically fix are escalated to `workflow-decay` proposals | §5 / DESIGN §5.2 |
| Validation layer | `engram validate` errors on mandatory override violations (§8); the Consistency Engine catches silent inconsistencies that validate does not flag as hard errors | §12 |
| Consistency journal | All proposals and resolutions append to `consistency.jsonl`; the journal is the single source of truth for all engine activity | §11.3 |
| Web UI (`engram review`) | Open proposals surface in the Dashboard and Consistency view; resolution actions trigger the same resolution commands described in §11.5 | DESIGN §7 |

---

### §11.8 Forward-Looking Notes

The following capabilities are intentionally deferred. They are recorded here so that implementors do not re-discover scope boundaries by trial and error.

**Deferred to DESIGN §5.2 (algorithms, not contract):**

- **Four-phase scan algorithm.** The sequence of static analysis → semantic clustering → LLM-assisted review → fixture execution, including the exact DBSCAN parameters, cluster thresholds, LLM prompt templates, and fixture execution harness, is specified in DESIGN §5.2. The contract here (what proposals must look like, what the engine must never do) is fixed; the algorithms implementing the contract are not.
- **Severity ranking and noise tuning.** Production deployments may want to suppress `info`-level proposals below a configurable threshold or to weight `error`-class proposals for paging. These are operational configuration concerns belonging to DESIGN §5.2.

**Deferred to future spec versions:**

- **ML-driven severity ranking.** Automatically promoting or demoting proposal severity based on historical operator behavior (e.g., "this class of proposal is always dismissed → downgrade to info") requires a feedback loop not yet specified. Future work.
- **Cross-repo conflict detection.** When two agents in different repos have contradictory proposals in their inboxes (Agent A proposes to update Asset X; Agent B proposes to delete Asset X), a coordination protocol is needed. This exceeds the scope of the v0.2 per-repo consistency model. Future work.
- **Bulk resolution workflows.** Large stores may generate hundreds of `time-expired` proposals at once. Batch resolution commands (`engram consistency resolve-all --class=time-expired --action=archive --older-than=180d`) are deferred to a future UX iteration; the resolution protocol in §11.5 handles the single-proposal case only.

---

---

## 12. Validation Rules and Error Code Registry

### §12.0 Overview

§12 is the machine-readable contract for `engram validate`. It lists every structural and schema validation rule an engram-compliant tool MUST enforce, and assigns each rule a stable, addressable error code. Codes appear in CLI output, JSON reports, CI logs, and cross-references throughout this document.

**Scope.** §12 covers structural and schema correctness — file existence, frontmatter syntax, required fields, type constraints, referential integrity, and lifecycle states — all checkable at read or write time without LLM assistance. Semantic conflicts between assets that are individually valid but mutually inconsistent are the domain of §11 (Consistency Contract).

**Error code scheme.** Each code is `{severity}-{category}-{number}`:

- **Severity** — `E` (error, exit 2) / `W` (warning, exit 1) / `I` (info, exit 0 with note)
- **Category** — three-letter scope abbreviation (see §12.14 for the full table)
- **Number** — three-digit, zero-padded, within each category

**Categories:**

| # | Category | Prefix | Covers |
|---|---|---|---|
| 1 | Structural | STR | File/directory existence and layout |
| 2 | Frontmatter | FM | Required/optional fields, types, formats |
| 3 | Memory subtypes | MEM | Per-subtype content rules |
| 4 | Workflow | WF | Spine, fixtures, metrics, revision rules |
| 5 | Knowledge Base | KB | Chapters, compiled digest rules |
| 6 | MEMORY.md index | IDX | Index format and coverage |
| 7 | Scope | SCO | Scope-hierarchy consistency |
| 8 | Enforcement | ENF | Mandatory/default/hint override rules |
| 9 | References | REF | Reference-graph integrity |
| 10 | Pool | POOL | Pool propagation and subscription rules |
| 11 | Inbox | INBOX | Inbox message format and lifecycle |
| 12 | Consistency | CONS | Consistency proposal integrity |

**CLI integration:**

```
engram validate                        # all validators; exit 0 / 1 / 2
engram validate --category=STR,FM      # scoped run
engram validate --json                 # machine-readable output (§12.13)
```

---

### §12.1 Structural (STR-*)

Structural rules check that the mandatory directories and files exist at the expected paths before any content parsing begins.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-STR-001` | error | `.memory/` directory exists at project root | §3.2 |
| `E-STR-002` | error | `.memory/MEMORY.md` exists | §7 |
| `E-STR-003` | error | `.memory/local/` directory exists for project-scope assets | §3.2 |
| `W-STR-001` | warning | `.memory/` exists but contains no assets | §3 |
| `W-STR-002` | warning | Unexpected top-level entry in `.memory/` — not one of: `MEMORY.md`, `local/`, `pools/`, `workflows/`, `kb/`, `index/`, `pools.toml` | §3.2 |
| `E-STR-004` | error | User-global `~/.engram/version` file missing (tool requires it for spec version check) | §13 |
| `W-STR-003` | warning | `~/.engram/version` exists but its major version mismatches the installed tool's major version | §13 |

**Notes.** `E-STR-001` through `E-STR-003` are prerequisites for all subsequent validators. If any of them fails, validators in other categories may report spurious results and SHOULD be skipped until the structural errors are resolved.

---

### §12.2 Frontmatter (FM-*)

Frontmatter rules apply to every asset file (Memory, Workflow doc, KB chapter, inbox message). A file that fails `E-FM-001` or `E-FM-002` cannot be further validated and all remaining FM checks are skipped for that file.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-FM-001` | error | Asset file has no YAML frontmatter block (no opening `---`) | §4.1 |
| `E-FM-002` | error | YAML frontmatter is malformed (parse error) | §4.1 |
| `E-FM-003` | error | Required field `name` missing | §4.1 |
| `E-FM-004` | error | Required field `description` missing | §4.1 |
| `E-FM-005` | error | Required field `type` missing | §4.1 |
| `E-FM-006` | error | `type` value not one of the 6 valid subtypes: `user`, `feedback`, `project`, `reference`, `workflow_ptr`, `agent` | §4.1 |
| `E-FM-007` | error | Required field `scope` missing (v0.2+) | §4.1 |
| `E-FM-008` | error | `scope` value not one of 5 valid scope labels: `user`, `project`, `team`, `org`, `pool` | §4.1 |
| `E-FM-009` | error | `scope: pool` asset missing required `pool:` field | §8.2 |
| `E-FM-010` | error | `scope: pool` asset missing `subscribed_at:` entry in the consumer's `pools.toml` | §8.2 |
| `E-FM-011` | error | `scope: org` asset missing required `org:` field | §8.1 |
| `E-FM-012` | error | `scope: team` asset missing required `team:` field | §8.1 |
| `W-FM-001` | warning | Optional field used incorrectly (e.g., `expires:` on a non-expiring subtype) | §4.1 |
| `W-FM-002` | warning | `description` value exceeds 150 characters (MEMORY.md hook display truncates at 150) | §7.2 |
| `W-FM-003` | warning | ISO 8601 date field (`created`, `updated`, `expires`, `valid_from`, `valid_to`) is malformed | §4.1 |

---

### §12.3 Memory Subtypes (MEM-*)

MEM rules apply after FM rules pass. Each rule targets a specific subtype; validators MUST check subtype identity before applying these rules.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-MEM-001` | error | `feedback` subtype missing required `enforcement:` field | §4.3 |
| `E-MEM-002` | error | `enforcement:` value not one of `mandatory`, `default`, `hint` | §8.3 |
| `E-MEM-003` | error | `feedback` body missing `**Why:**` and/or `**How to apply:**` sections | §4.3 |
| `E-MEM-004` | error | `project` body missing `**Why:**` and/or `**How to apply:**` sections | §4.4 |
| `E-MEM-005` | error | `workflow_ptr` subtype missing required `workflow_ref:` field | §4.6 |
| `E-MEM-006` | error | `workflow_ptr` `workflow_ref:` points to a non-existent workflow path | §4.6 |
| `E-MEM-007` | error | `agent` subtype missing required `source:` field | §4.7 |
| `W-MEM-001` | warning | `project` memory body contains a relative date expression (e.g., "next Thursday", "last week") | §4.4 |
| `W-MEM-002` | warning | `agent` memory missing optional `confidence:` field (recommended for evidence scoring) | §4.7, §4.8 |

---

### §12.4 Workflow (WF-*)

WF rules apply to every directory under `.memory/workflows/`. A workflow directory that fails `E-WF-001` through `E-WF-003` is structurally incomplete; downstream validators SHOULD skip that directory.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-WF-001` | error | Workflow directory missing required `workflow.md` | §5.1 |
| `E-WF-002` | error | Workflow directory missing required `spine.*` file | §5.1 |
| `E-WF-003` | error | Workflow directory missing required `fixtures/` directory | §5.1 |
| `E-WF-004` | error | `fixtures/` directory contains no fixture files (at least 1 required) | §5.4 |
| `E-WF-005` | error | Workflow directory missing `metrics.yaml` | §5.5 |
| `E-WF-006` | error | `spine_lang` value in `workflow.md` frontmatter is not a supported language identifier | §5.2 |
| `E-WF-007` | error | `rev/current` symlink exists but is dangling (points to a non-existent revision) | §5.6 |
| `W-WF-001` | warning | `fixtures/` directory has no success-case fixture (at least one recommended) | §5.4 |
| `W-WF-002` | warning | `fixtures/` directory has no failure-case fixture (at least one recommended) | §5.4 |
| `W-WF-003` | warning | `spine.*` file declares side effects not listed in `workflow.md` frontmatter `side_effects:` field | §5.3 |
| `W-WF-004` | warning | `metrics.yaml` has no `metric_primary` defined | §5.5 |

---

### §12.5 Knowledge Base (KB-*)

KB rules apply to every topic directory under `.memory/kb/`.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-KB-001` | error | KB topic directory missing required `README.md` | §6.1 |
| `E-KB-002` | error | KB topic directory has no chapter files (at least 1 required) | §6.1 |
| `E-KB-003` | error | `chapters:` frontmatter list in `README.md` references a non-existent file | §6.2 |
| `W-KB-001` | warning | `_compiled.md` missing — compilation is recommended before active use | §6.5 |
| `W-KB-002` | warning | `_compile_state.toml` hash does not match current chapter content — `_compiled.md` is stale | §6.5 |
| `W-KB-003` | warning | Chapter file exists in the topic directory but is not listed in `chapters:` (orphaned chapter) | §6.2 |

---

### §12.6 MEMORY.md Index (IDX-*)

IDX rules validate the hierarchical landing index (§7). §12 is the canonical definition of these codes; all earlier chapters reference them by the 3-digit form defined here.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-IDX-001` | error | `MEMORY.md` contains a link whose relative path does not resolve to an existing file (dangling link) | §7.2 |
| `E-IDX-002` | error | Asset file exists in `local/` but is not indexed in `MEMORY.md` or any `index/<topic>.md` | §7.2 |
| `E-IDX-003` | error | `MEMORY.md` contains a `## Topics` section header more than once (structural duplicate) | §7.2 |
| `W-IDX-001` | warning | `MEMORY.md` L1 entry count exceeds the 95th-percentile threshold (index density signal — see §16 glossary) | §7, §16 |
| `W-IDX-002` | warning | `index/<topic>.md` file is referenced in `MEMORY.md` but the file does not exist | §7.3 |
| `W-IDX-003` | warning | `MEMORY.md` has an inline entry for an asset that also appears in a topic sub-index (duplicate indexing) | §7.2 |

---

### §12.7 Scope (SCO-*)

SCO rules verify that an asset's declared scope is consistent with its filesystem location and with the existence of the scope directories it claims.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-SCO-001` | error | Asset declares `scope: org` but the `org:` field value does not correspond to an existing `~/.engram/org/<name>/` directory | §8.1 |
| `E-SCO-002` | error | Asset declares `scope: team` but the `team:` field value does not correspond to an existing team directory | §8.1 |
| `E-SCO-003` | error | Asset declares `scope: pool` but the named pool directory does not exist in `~/.engram/pools/` | §8.2 |
| `W-SCO-001` | warning | Asset at `scope: project` has `enforcement: mandatory` — project-level mandatory is unusual; team or higher scope is recommended | §8.7 |
| `W-SCO-002` | warning | Asset's declared `scope` does not match its filesystem location (e.g., `scope: user` but file is under `.memory/local/`) | §3.2 |

**Note.** `W-SCO-001` is the canonical definition of the code previously cited in §8.7.

---

### §12.8 Enforcement (ENF-*)

ENF rules check override-chain validity. `E-ENF-001` is the canonical definition of the code previously cited in §8.3 and §9.6.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-ENF-001` | error | A lower-scope asset conflicts with a higher-scope asset that carries `enforcement: mandatory` (mandatory enforcement cannot be overridden) | §8.3, §8.4 |
| `E-ENF-002` | error | Asset declares `overrides: <id>` but the target asset does not exist | §8.3 |
| `W-ENF-001` | warning | Asset overrides a `default`-enforcement asset without declaring an `overrides:` field | §8.3 |
| `W-ENF-002` | warning | `overrides:` target is not at a higher scope level than the declaring asset (same-scope or lower-scope override is suspicious) | §8.3 |
| `W-ENF-003` | warning | `overrides:` chain is circular (A overrides B overrides A) | §8.3 |

---

### §12.9 References (REF-*)

REF rules validate the reference graph. `W-REF-001` is the canonical definition of the code previously cited in §9.6.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-REF-001` | error | `references:` entry points to a non-existent asset (dangling reference) | §3.3 MUST 4 |
| `E-REF-002` | error | An asset with inbound `references:` entries is being deleted; it must be deprecated (moved to `archive/`) before deletion | §3.3 MUST 4 |
| `E-REF-003` | error | `supersedes:` field points to a target that does not exist | §4.1 |
| `W-REF-001` | warning | Reference rot: `references:` target has moved to `archive/` | §9.6 |
| `W-REF-002` | warning | Circular `supersedes:` chain detected | §4.1 |
| `W-REF-003` | warning | `[[wiki-link]]` in asset body points to a non-existent asset | §3.3 MUST 1 |

---

### §12.10 Pool (POOL-*)

POOL rules apply to subscriber projects and pool directories.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-POOL-001` | error | `pools.toml` declares `propagation_mode: pinned` but `pinned_revision:` is null or missing | §9.2 |
| `E-POOL-002` | error | `pools.toml` references a pool name that does not correspond to a directory under `~/.engram/pools/` | §9.2 |
| `E-POOL-003` | error | Pool's `rev/current` symlink is dangling (points to a non-existent revision) | §9.1 |
| `W-POOL-001` | warning | Subscribed pool has a new revision available and `propagation_mode` is `notify` — pending review | §9.3 |
| `W-POOL-002` | warning | Pool directory is missing `.engram-pool.toml` manifest | §9.1 |
| `W-POOL-003` | warning | `subscribed_at` scope level declared in `pools.toml` does not match the pool's declared publisher scope (possible misuse of hierarchy) | §9.2 |

---

### §12.11 Inbox (INBOX-*)

INBOX rules apply to message files under `~/.engram/inbox/<repo-id>/`.

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-INBOX-001` | error | Inbox message file missing one or more required fields: `from:`, `to:`, `intent:`, `status:` | §10.2 |
| `E-INBOX-002` | error | `intent` value not one of the 5 valid intents: `bug-report`, `api-change`, `question`, `update-notify`, `task` | §10.3 |
| `E-INBOX-003` | error | `status` value not one of the 4 valid states: `pending`, `acknowledged`, `resolved`, `expired` | §10.4 |
| `E-INBOX-004` | error | Inbox message file is in the wrong state directory (e.g., `status: pending` but file is under `resolved/`) | §10.4 |
| `W-INBOX-001` | warning | Pending message has had no acknowledgment for more than 30 days | §10.4 |
| `W-INBOX-002` | warning | Sender has exceeded the rate limit recorded in the delivery journal | §10.5 |
| `W-INBOX-003` | warning | `reply_to:` field references a message ID that does not exist | §10.2 |

---

### §12.12 Consistency (CONS-*)

CONS rules apply to the `consistency.jsonl` journal and its proposals. These rules are checked by `engram validate`; deeper semantic conflict detection is the Consistency Engine's domain (§11).

| Code | Severity | Rule | Chapter |
|---|---|---|---|
| `E-CONS-001` | error | A proposal in `consistency.jsonl` references an asset path that no longer exists | §11.3 |
| `W-CONS-001` | warning | An open proposal has been pending for more than 90 days without resolution (approaching expiry) | §11.5 |
| `W-CONS-002` | warning | A proposal's `involved_assets` list includes an asset that has been moved to `archive/` | §11.2 |
| `I-CONS-001` | info | Proposal creation rate exceeds 10 per day — high volume may indicate a root-cause issue worth investigating | §11.5 |

---

### §12.13 CLI Output Format

**JSON mode (`engram validate --json`):**

```json
{
  "summary": {
    "errors": 2,
    "warnings": 5,
    "info": 0,
    "exit_code": 2
  },
  "issues": [
    {
      "code": "E-FM-003",
      "severity": "error",
      "file": ".memory/local/feedback_example.md",
      "line": null,
      "message": "required field `name` missing",
      "reference": "SPEC §4.1"
    },
    {
      "code": "W-IDX-001",
      "severity": "warning",
      "file": ".memory/MEMORY.md",
      "line": null,
      "message": "MEMORY.md L1 entry count exceeds 95th-percentile threshold",
      "reference": "SPEC §7"
    }
  ]
}
```

**Text mode (`engram validate`):**

```
.memory/local/feedback_example.md:
  E-FM-003 (error) required field `name` missing
    → SPEC §4.1

.memory/MEMORY.md:
  W-IDX-001 (warning) MEMORY.md L1 entry count exceeds 95th-percentile threshold
    → SPEC §7

2 errors, 5 warnings — exit 2
```

**Exit codes:**

| Exit code | Meaning |
|---|---|
| `0` | Clean — no errors, no warnings (info-level notices may still be printed) |
| `1` | Warnings present — no errors |
| `2` | One or more errors present |

---

### §12.14 Category Summary

Full code-space allocation table. Each category owns the range `001–099`; numbers `100–999` are reserved for future expansion.

| Category | Prefix | Range | Primary chapter |
|---|---|---|---|
| Structural | STR | 001–099 | §3 |
| Frontmatter | FM | 001–099 | §4.1 |
| Memory subtypes | MEM | 001–099 | §4.2–§4.7 |
| Workflow | WF | 001–099 | §5 |
| Knowledge Base | KB | 001–099 | §6 |
| MEMORY.md index | IDX | 001–099 | §7 |
| Scope | SCO | 001–099 | §8 |
| Enforcement | ENF | 001–099 | §8.3, §8.4 |
| References | REF | 001–099 | §3.3, §9.6 |
| Pool | POOL | 001–099 | §9 |
| Inbox | INBOX | 001–099 | §10 |
| Consistency | CONS | 001–099 | §11 |

**Allocating new codes.** When adding a validation rule, take the next unused number within the appropriate category. Do not reuse a retired code; retired codes are documented with a `(retired)` annotation in this table and in the changelog.

---

## 13. Versioning and Migration Contract

### §13.0 Overview

engram uses a `MAJOR.MINOR` spec version (no PATCH) with clear rules for what constitutes a breaking change. v0.2 is the first widely-adopted release; it introduces breaking changes from v0.1 in specific, well-documented ways. §13 ensures that no user loses data: the migration contract specifies every changed field, the automated migration steps, the defaults applied when required fields are absent, and a 6-month read-only compatibility window during which v0.1 stores remain usable while users migrate at their own pace.

Readers of §13 fall into two groups:

- **Users migrating a v0.1 store** — follow §13.3 (breaking-change table) and §13.4 (migration command contract).
- **Tool authors implementing `engram migrate`** — read all of §13, paying particular attention to the idempotency and rollback requirements in §13.4.

The version file at `~/.engram/version` (§13.2) is the authoritative record of which spec version a store was written against. Every `engram` CLI command reads it at startup and applies the rules in §13.2.

---

### §13.1 Semantic Versioning

**engram spec versions** use `MAJOR.MINOR` (e.g., `0.1`, `0.2`, `1.0`). Because this is a specification for an on-disk format rather than a library API, no PATCH level is used — documentation clarifications and example additions do not bump any number.

**Breaking changes** trigger a MAJOR bump:

- Removing or renaming a required frontmatter field
- Changing the meaning of an existing enum value (e.g., renaming a scope label or enforcement level)
- Reorganizing the canonical directory layout (e.g., moving `.memory/local/` to a different path)
- Renaming a Memory subtype, Workflow lifecycle state, or error-code prefix

**Additive changes** trigger a MINOR bump:

- Adding a new optional frontmatter field
- Adding a new scope label, Memory subtype, error code, intent value, or event type (existing values unaffected)
- Adding new CLI subcommands
- Adding new pool propagation modes

**Non-changes** (no version bump):

- Fixing typos or clarifying prose
- Adding or improving examples
- Adding new appendix sections

**Implementation version.** The tool's own release version (e.g., `engram-cli 0.2.1`) follows semver independently. A `0.2.1` implementation MUST conform to the `0.2` spec. The patch digit is reserved for bug fixes that do not alter the spec contract.

---

### §13.2 `~/.engram/version` File

`~/.engram/version` is a plain-text file containing a single line: the spec version the store is written against.

```
0.2
```

No trailing whitespace, no trailing newline required, no other fields. A tool MUST write this file atomically (write to a temp file, then rename).

**Write rule.** `engram init` creates `~/.engram/version` containing the tool's embedded spec version. `engram migrate` updates it on successful completion.

**Read rule.** Every `engram` CLI command reads `~/.engram/version` at startup and applies the following logic:

| Condition | Action |
|---|---|
| File missing | Assume `0.1` (grandfather rule). Emit `W-STR-004` once per session. |
| Version matches tool's embedded spec | Proceed normally. |
| Version is older than tool's spec | Emit info-level notice pointing to migration. Read-only operations proceed; writes require migration (§13.5). |
| Version is newer than tool's spec | Emit `W-STR-005`. Tool may not understand newer constructs; user should upgrade the tool. |

**Warning codes assigned here:**

| Code | Severity | Condition |
|---|---|---|
| `W-STR-004` | warning | `~/.engram/version` file missing; assuming v0.1 — run `engram migrate --to=0.2` |
| `W-STR-005` | warning | `~/.engram/version` declares a version newer than this tool supports — upgrade the tool |

---

### §13.3 v0.1 → v0.2 Breaking Changes

The table below enumerates every breaking change introduced in v0.2. Column "Migration default" states the value that `engram migrate` injects when the field is absent; "No action" means the change requires no data transformation.

| # | What changed | v0.1 | v0.2 | Migration default |
|---|---|---|---|---|
| 1 | Memory file location | `.memory/*.md` (flat) | `.memory/local/*.md` | Move all `*.md` → `local/*.md` |
| 2 | Shared pool path | `~/.engram/shared/<name>/` | `~/.engram/pools/<name>/` | `mv` on migrate |
| 3 | `scope` frontmatter field | Absent (implicit local) | Required | `scope: project` |
| 4 | `enforcement` on feedback | Absent | Required | `enforcement: default` |
| 5 | `MEMORY.md` 200-line cap | Enforced | Removed — quality maintained by Consistency Engine | No action |
| 6 | Memory subtypes | 4 (`user`, `feedback`, `project`, `reference`) | 6 (adds `workflow_ptr`, `agent`) | Existing 4 unchanged |
| 7 | Workflow as first-class asset | Absent | Required structure (§5) | No v0.1 workflows to migrate |
| 8 | Knowledge Base as first-class | Absent | Required structure (§6) | No v0.1 KB to migrate |
| 9 | `confidence` field | Absent | Required on `agent`; recommended on others | Added as empty object `{}` for `agent` files |
| 10 | Scope labels | Absent | Five labels: `org`, `team`, `user`, `project`, `pool` | `project` set; others empty |
| 11 | User-global directory | `~/.engram/global/` | `~/.engram/user/` | Rename on migrate |
| 12 | Team and org scope | Absent | Supported via `team/` and `org/` directories | Empty initially; opt-in |

Items 7, 8, 12 require no data migration action — they introduce new asset classes and scope levels that did not exist in v0.1. Items 1–6, 9–11 require concrete file-system and frontmatter transformations, all handled by `engram migrate`.

---

### §13.4 `engram migrate --from=v0.1` Contract

**Command signature:**

```
engram migrate --from=v0.1 [--dry-run] [--target=<path>] [--json] [--rollback]
```

**Preconditions (checked before any write):**

1. Target directory contains `.memory/` (v0.1 format detected).
2. Tool version supports v0.2 spec.
3. No `E-*` validation errors in the v0.1 store (warnings acceptable). Run `engram validate` first if unsure.

If any precondition fails, migrate exits with code 1 and a human-readable explanation. No files are modified.

**Dry-run mode (`--dry-run`):**

Prints a full migration report to stdout. No changes are made to the filesystem. The report lists, for each affected asset:

- Current path → new path
- Frontmatter fields added
- Default values injected
- Any ambiguities requiring user decision

`--json` outputs the same report as a JSON object. Exit code 0 if migration would succeed; exit code 1 if issues are detected.

**Live migration steps (in order):**

1. Read `~/.engram/version` (absence implies `0.1`). Confirm source is v0.1.
2. **Safety backup.** Create `.memory.pre-v0.2.backup/` as a full copy of the current `.memory/` directory. Abort the entire migration if this copy cannot be created.
3. Create the v0.2 target structure: `.memory/local/`, `.memory/pools/`, `.memory/workflows/`, `.memory/kb/`.
4. For each `.memory/*.md` (flat v0.1 files):
   a. Move to `.memory/local/<filename>`.
   b. Parse frontmatter. Add `scope: project` if the `scope` field is absent.
   c. If `type: feedback` and `enforcement` is absent, add `enforcement: default`.
   d. If `type: agent` and `confidence` is absent, add `confidence: {}`.
   e. Preserve all unknown frontmatter fields (forward-compatibility rule, §4.1).
5. If `~/.engram/shared/` exists, move to `~/.engram/pools/`. Update any `subscribed_at` references.
6. If `~/.engram/global/` exists, rename to `~/.engram/user/`.
7. Regenerate `MEMORY.md` using the v0.2 hierarchical format (§7). User content between `<!-- engram:preserve-begin -->` and `<!-- engram:preserve-end -->` markers is preserved verbatim.
8. Write `~/.engram/version` with content `0.2`.
9. Append a structured record to `~/.engram/journal/migration.jsonl`:

```json
{
  "event": "migration",
  "from_version": "0.1",
  "to_version": "0.2",
  "timestamp": "<ISO-8601>",
  "assets_moved": <count>,
  "fields_added": <count>,
  "backup_path": ".memory.pre-v0.2.backup/"
}
```

**Idempotency.** If `~/.engram/version` already contains `0.2` when migrate is invoked, the command prints `store is already at v0.2 — nothing to do` and exits 0. It does not re-run any migration steps.

**Rollback.** `engram migrate --rollback` restores from `.memory.pre-v0.2.backup/` if that directory exists:

1. Remove current `.memory/`.
2. Rename `.memory.pre-v0.2.backup/` → `.memory/`.
3. Write `~/.engram/version` with `0.1` (or remove it if it did not previously exist).

Rollback is a one-time escape hatch. Once rolled back, the backup directory is consumed; run dry-run again before re-migrating.

**Error codes assigned here:**

| Code | Severity | Condition |
|---|---|---|
| `E-STR-005` | error | Write attempted on a v0.1 store; migrate first |
| `E-STR-006` | error | v0.1 compatibility expired (post-6-month); migrate required |

---

### §13.5 6-Month Compatibility Window

For 6 months from the v0.2 release date (recorded as `release_date` in the embedded tool metadata), v0.1-format stores continue to work in **read-only mode**:

**Warnings emitted on every read-only operation:**

| Code | Severity | Condition |
|---|---|---|
| `W-STR-003` | warning | `~/.engram/version` major-version mismatch: store is v0.1, tool targets v0.2 |
| `W-STR-006` | warning | Compatibility mode active: v0.1 store is readable but writes are blocked — run `engram migrate --from=v0.1` |

**Read-only operations that work during the compatibility window:**

- `engram memory read`, `engram memory search` — proceed with warnings
- `engram review` — proceeds with warnings
- `engram validate` — proceeds; reports v0.1-specific issues as warnings, not errors

**Write operations that are blocked:**

- `engram memory add`, `engram memory update`, `engram memory delete` — exit 1 with `E-STR-005`
- `engram init` in an existing v0.1 store — blocked; user must migrate first

**Post-6-months behavior.** Once the compatibility window expires, the tool refuses all operations (read and write) on v0.1 stores:

```
E-STR-006 v0.1 compatibility has expired — run `engram migrate --from=v0.1` to upgrade
```

`engram migrate` itself is never time-limited. A user may migrate a v0.1 store at any time, regardless of the compatibility window.

**Opt-out.** Users who want the post-expiry behavior immediately (e.g., to enforce migration discipline on a team) can set:

```
engram config set compat.v0.1=expired
```

This immediately activates `E-STR-006` for all v0.1 stores, regardless of the release date.

---

### §13.6 Migration from Other Systems

`engram migrate --from=<source>` supports the following sources in addition to v0.1. Each maps external data into v0.2 format, prompting the user for any required decisions (scope, enforcement defaults) that cannot be inferred automatically.

| Source flag | External system | Mapping summary |
|---|---|---|
| `--from=claude-code` | Claude Code memory system | Reads `~/.claude/projects/<slug>/memory/*.md`; maps to v0.2 Memory format; prompts for scope and enforcement defaults |
| `--from=chatgpt` | ChatGPT Memories export (JSON) | Parses ChatGPT JSON export; creates `user_*.md` Memory entries with `type: user` |
| `--from=mem0` | mem0 database export | Reads mem0 export; maps to `user`, `project`, or `reference` subtypes by heuristics; prompts on ambiguous entries |
| `--from=obsidian` | Obsidian daily notes | Interactive: user selects which notes become Memory entries; tags from Obsidian become `tags:` |
| `--from=letta` | Letta / MemGPT archival memory | `core_memory` blocks → `user` subtype; `archival` blocks → `reference` subtype |
| `--from=mempalace` | MemPalace store | Drawers → `reference` memories; Wings → `tags:`; Closets used for metadata only |
| `--from=markdown --dir=<path>` | Generic markdown directory | Scans `<path>`; treats each `.md` as a Memory entry; uses directory structure to infer `tags:` |

For each source, detailed field-by-field mapping rules are documented in `docs/migrate/<source>.md` (not part of this spec). The contract guaranteed here is:

1. No input file is deleted or modified; all writes go into the engram store.
2. On conflict with an existing store entry, migrate prompts rather than overwrites.
3. A dry-run (`--dry-run`) is always available and always safe.
4. The migration journal record (§13.4, step 9) is written with `from_version` set to the source name.

---

### §13.7 Future Migration Compatibility

Design principles that govern all future spec version migrations:

1. **Document every breaking change.** Each MAJOR bump's release notes must enumerate every item in §13.3-style format.
2. **Automated migrate for at least two major versions back.** At the time of v1.0's release, `engram migrate --from=v0.1` and `engram migrate --from=v0.2` must both be supported.
3. **Readable-but-warn mode for 6 months.** Every major version transition ships with the same compatibility window defined in §13.5.
4. **Never destroy user data.** Every live migration creates a `.pre-v{N}.backup/` snapshot before any write. The rollback path must always exist.
5. **Idempotency is required.** Running migrate twice on an already-migrated store must be a no-op.
6. **Additive defaults.** When a new required field is introduced, its migration default must be the least-surprising value — the value a v0.1 author would have chosen had the field existed.

The version file format (`~/.engram/version`) is itself stable across all future versions — a single-line spec version string. If this contract must ever change, it constitutes a MAJOR bump.

---

## 14. Appendices

### §14.0 Overview

This chapter contains three reference appendices that complement the normative specification in §0 through §13:

- **Appendix A** provides a complete, runnable minimum viable engram store for a single developer on a real project. Every asset class is represented and the store validates cleanly against `engram validate`.
- **Appendix B** cites every external project, paper, and idea that shaped v0.2's design, organized by the chapter each source most influenced.
- **Appendix C** reproduces ten frequently asked questions distilled from early-access design discussions, with concise answers cross-referenced to the relevant specification sections.

These appendices are reference material, not normative requirements. Nothing in §14 changes the validation rules or the on-disk format contract defined in §0–§13.

---

### §14.A — Appendix A: Minimum Viable engram Store

A complete `.memory/` directory for a single developer working on `acme-checkout-service` with one team pool subscribed. Every asset class is present. This store validates cleanly against `engram validate`.

**Scenario:** Solo developer, `acme-checkout-service` project, subscribed to the shared `design-system` pool.

#### File tree

```
acme-checkout-service/
├── .memory/
│   ├── MEMORY.md
│   ├── pools.toml
│   ├── local/
│   │   ├── user_developer_profile.md
│   │   ├── feedback_push_requires_confirmation.md
│   │   ├── project_current_sprint.md
│   │   ├── reference_internal_api_docs.md
│   │   ├── workflow_ptr_release_checklist.md
│   │   └── agent_commit_message_style.md
│   ├── pools/
│   │   └── design-system → ~/.engram/pools/design-system/current/
│   ├── workflows/
│   │   └── release-checklist/
│   │       ├── workflow.md
│   │       ├── spine.sh
│   │       ├── fixtures/
│   │       │   ├── success-case.yaml
│   │       │   └── failure-case.yaml
│   │       ├── metrics.yaml
│   │       └── rev/
│   │           ├── r1/
│   │           └── current → r1/
│   └── kb/
│       └── acme-checkout-architecture/
│           ├── README.md
│           ├── 01-overview.md
│           └── _compiled.md
├── .engram/
│   └── version
└── CLAUDE.md
```

#### File contents

**`.memory/MEMORY.md`**

```markdown
---
engram_version: "0.2"
generated_at: "2026-04-18T09:00:00Z"
scope: project
---

# Memory Index — acme-checkout-service

> Landing index for all engram assets in this project.
> Load this file first; follow refs to load individual assets.

## User Identity

- [Developer profile](local/user_developer_profile.md) — role, skills, preferred stack

## Feedback (Rules & Preferences)

- [Push requires confirmation](local/feedback_push_requires_confirmation.md) — `enforcement: hint` — always confirm before `git push`

## Project State

- [Current sprint](local/project_current_sprint.md) — Sprint 7, expires 2026-04-30

## References

- [Internal API docs](local/reference_internal_api_docs.md) — acme internal service catalog URL

## Workflow Pointers

- [Release checklist](local/workflow_ptr_release_checklist.md) → `workflows/release-checklist/`

## Agent-Learned

- [Commit message style](local/agent_commit_message_style.md) — conventional commits, inferred from history

## Pools

- [design-system](pools/design-system/) — team pool, `subscribed_at: user`, `auto-sync`

## Knowledge Bases

- [acme-checkout architecture](kb/acme-checkout-architecture/) — service topology, data flow, ADR index
```

---

**`.memory/pools.toml`**

```toml
[pools.design-system]
path = "~/.engram/pools/design-system/current/"
subscribed_at = "user"
mode = "auto-sync"
subscribed_on = "2026-03-01"
description = "Shared design system tokens and component conventions"
```

---

**`.memory/local/user_developer_profile.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: user
scope: user
title: "Developer Profile"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-18T09:00:00Z"
tags: [identity, skills]
---

# Developer Profile

**Role:** Full-stack engineer, primarily backend (Go, TypeScript).
**Current team:** Checkout Platform.
**Preferred workflow:** TDD, small PRs, conventional commits.
**Tools in daily use:** Claude Code, neovim, tmux, gh CLI.
**Timezone:** UTC+8.
```

---

**`.memory/local/feedback_push_requires_confirmation.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: feedback
scope: user
title: "Push requires explicit confirmation"
created_at: "2026-03-15T11:00:00Z"
updated_at: "2026-04-10T08:30:00Z"
enforcement: hint
tags: [git, safety]
confidence_score: 0.95
validated_count: 12
contradicted_count: 0
---

# Push Requires Explicit Confirmation

**Rule:** Never run `git push` (or any variant that sends commits to a remote) without
first confirming with the developer.

**Why:** Pushing to `main` on `acme-checkout-service` triggers a staging deploy. An
accidental push during a hotfix window can block other teams.

**How to apply:** Before any `git push`, output a summary of the commits about to be
pushed and ask "Confirm push?" Wait for an explicit "yes" before proceeding.

**Exceptions:** `git push --dry-run` is always safe and never requires confirmation.
```

---

**`.memory/local/project_current_sprint.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: project
scope: project
title: "Current Sprint — Sprint 7"
created_at: "2026-04-14T09:00:00Z"
updated_at: "2026-04-14T09:00:00Z"
expires: "2026-04-30T23:59:59Z"
tags: [sprint, planning]
---

# Sprint 7 (2026-04-14 – 2026-04-30)

**Goal:** Ship cart-service v2 integration, close P0 latency regression (issue #412).

**Active tickets:**
- CHECKOUT-881 — Integrate cart-service v2 API
- CHECKOUT-412 — P0: reduce checkout latency p99 from 420 ms to < 200 ms
- CHECKOUT-903 — Update internal API docs after cart-service migration

**Out of scope this sprint:** payment provider retry logic (deferred to Sprint 8).
```

---

**`.memory/local/reference_internal_api_docs.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: reference
scope: project
title: "Internal API Documentation"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-01T14:00:00Z"
tags: [api, reference, internal]
url: "https://internal.acme.example/service-catalog/checkout"
---

# Internal API Docs

**URL:** https://internal.acme.example/service-catalog/checkout

**Access:** Requires VPN + corporate SSO. Token-based auth via `acme-cli login`.

**Context:** Canonical source for all upstream service contracts consumed by
`acme-checkout-service`. Includes cart-service, payment-service, and identity-service
API schemas. Updated on every service release; check the changelog tab before assuming
schema stability.
```

---

**`.memory/local/workflow_ptr_release_checklist.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: workflow_ptr
scope: project
title: "Release Checklist Workflow Pointer"
created_at: "2026-03-20T09:00:00Z"
updated_at: "2026-04-01T09:00:00Z"
workflow_ref: "workflows/release-checklist/"
tags: [release, workflow]
---

# Release Checklist

Points to the `release-checklist` workflow asset at `workflows/release-checklist/`.

**When to invoke:** Before tagging any release on `acme-checkout-service`.
Run via `engram workflow run release-checklist` or open `workflow.md` for manual steps.
```

---

**`.memory/local/agent_commit_message_style.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: agent
scope: project
title: "Commit Message Style"
created_at: "2026-04-05T16:00:00Z"
updated_at: "2026-04-18T09:00:00Z"
source: agent-learned
confidence_score: 0.88
validated_count: 34
contradicted_count: 2
tags: [git, commits, style]
---

# Commit Message Style

**Format:** Conventional Commits (`type(scope): subject`).

**Observed types in this repo:** `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`.

**Subject line rules:**
- Lowercase after the colon.
- Imperative mood ("add X", not "added X").
- No trailing period.
- Max 72 characters.

**Body (when present):** Wrap at 72 chars. Blank line after subject. Describe *why*, not *what*.

**Trailers in use:** `Fixes: #<issue>`, `Co-authored-by:`.

*Inferred from 34 commits in this repo's recent history.*
```

---

**`.memory/workflows/release-checklist/workflow.md`**

```markdown
---
engram_version: "0.2"
type: workflow
title: "Release Checklist"
version: "1.0.0"
created_at: "2026-03-20T09:00:00Z"
updated_at: "2026-04-10T11:00:00Z"
spine: "spine.sh"
tags: [release, checklist]
---

# Release Checklist

## Purpose

Verify that `acme-checkout-service` is ready to tag and deploy. Catches the most
common pre-release failures: missing migration, outdated API docs, red CI, and
missing changelog entry.

## When to Use

Run this workflow before tagging any release (`git tag vX.Y.Z`). It is safe to run
multiple times; each run is idempotent.

## Expected Outcome

On success: all checks pass, release tag is applied, and metrics.yaml is updated.
On failure: the workflow exits at the first failed check and prints a remediation hint.
```

---

**`.memory/workflows/release-checklist/spine.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Release Checklist: acme-checkout-service ==="

echo "[1/5] Checking CI status..."
gh run list --limit 1 --json conclusion -q '.[0].conclusion' | grep -q "success"

echo "[2/5] Checking for uncommitted changes..."
git diff --quiet && git diff --staged --quiet

echo "[3/5] Verifying CHANGELOG.md updated..."
grep -q "## \[Unreleased\]" CHANGELOG.md

echo "[4/5] Running unit tests..."
go test ./... -count=1 -timeout 60s

echo "[5/5] Confirming migration files present..."
ls db/migrations/*.sql 2>/dev/null | wc -l | grep -qv "^0$"

echo "=== All checks passed. Ready to release. ==="
```

---

**`.memory/workflows/release-checklist/fixtures/success-case.yaml`**

```yaml
# success-case.yaml — happy path fixture for release-checklist
fixture: success-case
description: "All pre-release conditions satisfied"
preconditions:
  ci_status: success
  uncommitted_changes: false
  changelog_updated: true
  tests_pass: true
  migrations_present: true
expected_outcome:
  exit_code: 0
  final_message: "All checks passed. Ready to release."
steps_expected:
  - check: ci_status
    result: pass
  - check: uncommitted_changes
    result: pass
  - check: changelog_updated
    result: pass
  - check: tests_pass
    result: pass
  - check: migrations_present
    result: pass
```

---

**`.memory/workflows/release-checklist/fixtures/failure-case.yaml`**

```yaml
# failure-case.yaml — CI red failure fixture
fixture: failure-case
description: "CI is red; workflow must exit at step 1"
preconditions:
  ci_status: failure
expected_outcome:
  exit_code: 1
  failed_at_step: 1
  hint: "Fix failing CI run before tagging a release."
```

---

**`.memory/workflows/release-checklist/metrics.yaml`**

```yaml
# metrics.yaml — outcome tracking for release-checklist workflow
workflow: release-checklist
last_run: "2026-04-17T14:22:00Z"
total_runs: 8
successful_runs: 7
failed_runs: 1
last_failure_step: 3
last_failure_reason: "CHANGELOG.md not updated"
average_duration_seconds: 42
mastery_score: 0.875
```

---

**`.memory/kb/acme-checkout-architecture/README.md`**

```markdown
---
engram_version: "0.2"
type: kb
title: "acme-checkout Architecture"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-15T12:00:00Z"
compiled_at: "2026-04-15T12:30:00Z"
tags: [architecture, checkout, acme]
---

# acme-checkout Architecture

**Abstract:** Service topology, data flow, and key design decisions for
`acme-checkout-service`. Covers the integration points with cart-service,
payment-service, and identity-service.

## Chapters

1. [Overview](01-overview.md) — Service boundaries, primary flows, deployment topology
```

---

**`.memory/kb/acme-checkout-architecture/_compiled.md`**

```markdown
<!-- AUTO-GENERATED by engram compile — do not edit by hand.
     Source: kb/acme-checkout-architecture/
     Compiled: 2026-04-15T12:30:00Z
     Compiler: engram/0.2 -->

# acme-checkout Architecture — Compiled Digest

## Overview

`acme-checkout-service` is the sole owner of the checkout transaction lifecycle.
It orchestrates cart-service (item validation + pricing), payment-service (charge
capture), and identity-service (buyer authentication). The service is deployed as a
single Go binary behind an internal gRPC gateway.

**Key data flows:**
1. Buyer initiates checkout → identity-service validates session token.
2. Cart contents fetched from cart-service v2 API (migrating from v1 in Sprint 7).
3. Payment captured via payment-service; idempotency key = `order_id`.
4. Confirmation event published to `checkout.completed` Kafka topic.

*This digest was synthesized from the chapter files in this KB. For source ADRs and
diagrams, see the individual chapter files.*
```

---

**`.engram/version`**

```
0.2
```

---

**`CLAUDE.md`** (adapter)

```markdown
# engram Adapter — acme-checkout-service

This project uses the engram v0.2 memory system.

**Memory store:** `.memory/MEMORY.md`

When starting a new session:
1. Read `.memory/MEMORY.md` to load the full asset index.
2. Load assets relevant to the current task (follow refs in MEMORY.md).
3. Respect `enforcement: mandatory` rules without exception;
   apply `enforcement: default` rules unless given a specific reason not to;
   treat `enforcement: hint` rules as suggestions.

For validation: `engram validate` (requires engram CLI ≥ 0.2).
```

---

**This store validates cleanly. Run `engram validate` to confirm zero errors.**

---

### §14.B — Appendix B: Design Basis

Every external project, paper, and idea that shaped engram v0.2's design, organized by the chapter each source most influenced.

| Source | Type | Influence on engram v0.2 | Chapters |
|---|---|---|---|
| Karpathy, "LLM Wiki as Personal Knowledge Base" (gist) | Methodology | Knowledge Base class: human-written chapters, LLM-compiled digest; write-side synthesis discipline | §6 |
| Karpathy, `autoresearch` | Open-source system | Workflow Autolearn 8-discipline evaluation loop; `evolution.tsv` append-only history; Phase gate; simplicity criterion | §5, DESIGN §5.3 |
| MemPalace (`milla-jovovich/mempalace`) | Open-source system | Hybrid retrieval (BM25 + vector fusion + temporal boost + two-pass re-rank); 4-layer wake-up stack; `_compile_state.toml` pattern; backend abstraction; PreCompact + Stop hook pattern; BENCHMARKS.md discipline | §7, §9, DESIGN §5.1 |
| Darwin.skill (`alchaincyf/darwin-skill`) | Open-source system | Autolearn ratchet (git-native commit + revert); dual evaluation (static 60 + perf 40); independent evaluator agent; phase-gate checkpoints | §5, DESIGN §5.3 |
| Nuwa.skill (`alchaincyf/nuwa-skill`) | Open-source system | Honest limitations declaration (`limitations:` frontmatter field) | §4.1 |
| "Experience-as-Code" (Agent Factory 2026-03 arXiv) | Paper | Workflow = doc + executable spine, not prose-only; executable spines as first-class citizens | §5 |
| evo-memory (DeepMind 2025) | Paper | Search → Synthesize → Evolve lifecycle; ReMem action-think-refine loop; evidence-driven confidence scoring | §4.8, §11, DESIGN §5.2/5.3 |
| MemoryBank (arXiv 2305.10250) | Paper | Ebbinghaus forgetting curve inspires `staleness_penalty` formula; adapted to confidence-driven retention rather than time-only decay | §4.8, §11 |
| MemGPT / Letta | Paper + system | Memory as structured, paged context; inspired layered MEMORY.md design, but engram stays file-native with no paging abstraction | §7 |
| Claude Code memory system | Pre-art | Direct predecessor; engram v0.1 was a Claude Code skill; v0.2 generalizes to LLM-agnostic format | §13 (migration), §3 |
| `skills.sh` ecosystem (`npx skills add <owner>/<repo>`) | Convention | Playbook installation URL scheme: `engram playbook install github:<owner>/<repo>` | §4 (referenced), §9, DESIGN §4 |

**Acknowledgments**

engram v0.2 draws directly from ideas first demonstrated by others. The authors of the works above deserve primary credit for the insights; any errors in adaptation are ours alone. engram is a composition of well-tested ideas aimed at making persistent LLM memory truly portable and self-maintaining.

---

### §14.C — Appendix C: Frequently Asked Questions

Ten questions distilled from early-access design discussions.

1. **Q: Why markdown files instead of a vector database or dedicated memory service?**

   A: Portability beats cleverness. Markdown works with any editor, git, grep, and Obsidian. Embeddings are a cache (see DESIGN §5.1); the source of truth is text files the user owns. If engram disappears tomorrow, the markdown store remains fully usable with no special tooling.

2. **Q: Why 6 memory subtypes instead of just one "memory" type?**

   A: Epistemic status differs across subtypes. User-identity, human-authored rule, LLM-learned heuristic, ongoing decision, external pointer, and workflow pointer all require different lifecycles, default confidence values, and review cadences. A single "memory" type would collapse these distinctions. §4.2–§4.7 covers each subtype in detail.

3. **Q: Why two axes for scope (hierarchy + subscription)?**

   A: Collapsing them into a single linear dimension — as v0.1 did — forces awkward choices when knowledge needs to flow across teams without implying membership. A hierarchy models "who you belong to"; subscriptions model "what you opt into". They are orthogonal, and treating them as orthogonal simplifies every conflict-resolution rule. §8 details the two-axis model.

4. **Q: Does engram delete old memories automatically?**

   A: No. Deletions always require explicit operator action. The Consistency Engine proposes; it never mutates. Assets move through `archive/` with a six-month retention floor before physical removal is permitted. §11.6 enumerates the non-goals of the Consistency Engine.

5. **Q: What is the maximum memory store size?**

   A: There is no cap. Quality is maintained by the Consistency Engine (§11) and adaptive signals (see docs/glossary.md for `staleness_penalty`, `confidence_score`), not by size limits. Asset classes differ by function, not by length.

6. **Q: How does engram handle LLMs with small context windows (e.g., an 8K-token model)?**

   A: The Relevance Gate (DESIGN §5.1) selects a subset of assets that fits the context budget. MEMORY.md is designed to stay under 900 tokens. Small-context models receive the same quality signal, just a smaller slice of it. No special configuration is required.

7. **Q: Can engram work offline?**

   A: Yes, entirely. All assets are local files. Pool sync requires network access only when pushing or pulling. The CLI has no mandatory network dependencies; `engram validate`, `engram review`, and all local read/write operations work without connectivity.

8. **Q: How does engram compare to MemPalace, mem0, and Letta?**

   A: MemPalace stores verbatim conversation transcripts; engram stores curated, structured assets. mem0 is a hosted service; engram is local-first and LLM-agnostic. Letta treats memory as paged virtual memory; engram treats it as a versioned filesystem the user owns. §14.B compares at the technique and influence level.

9. **Q: Can I import my existing Claude Code / ChatGPT / mem0 memory?**

   A: Yes. `engram migrate --from=<source>` supports Claude Code, ChatGPT export, mem0, Obsidian, Letta, MemPalace, and generic markdown directories. No input file is deleted or modified during migration. §13.6 documents the field-by-field mapping for each source.

10. **Q: Is engram ready for production use?**

    A: v0.2 is a draft specification; the reference implementation is in active development. The SPEC is stable enough to build against — no breaking changes are expected before v1.0. Production readiness tracks milestone M4 (see TASKS.md).

---

**SPEC v0.2 draft is complete.** Chapters §0 through §14 cover the full on-disk format contract, validation rules, and migration path for the engram memory system. Companion documents continue the story:

- [`DESIGN.md`](DESIGN.md) — 5-layer implementation architecture (Data / Control / Intelligence / Access / Observation)
- [`METHODOLOGY.md`](METHODOLOGY.md) — how LLMs should write, evolve, and retire assets
- [`TASKS.md`](TASKS.md) — milestones and implementation task board
- [`docs/glossary.md`](docs/glossary.md) — authoritative term definitions

For updates and corrections, see [`docs/HISTORY.md`](docs/HISTORY.md) (to be created at first release).
