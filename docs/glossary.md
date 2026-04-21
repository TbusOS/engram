[English](glossary.md) · [中文](glossary.zh.md)

# engram Glossary (v0.2)

> **Term stability anchor.** Every v0.2 document (`SPEC.md`, `DESIGN.md`, `TASKS.md`, `README.md`, `METHODOLOGY.md`, `CONTRIBUTING.md`, and every adapter / tutorial file) MUST use the English terms in this file. Chinese translations in [`glossary.zh.md`](glossary.zh.md) are the only approved renderings. Do not invent new translations mid-document. If you need a new term, add a row here first, then use it.

Why this matters: engram has three readers (LLMs, humans, other tool authors). Term drift costs LLMs relevance hits, humans comprehension, and tool authors correctness. This table is small enough that we can keep it in our heads and big enough that all v0.2 design decisions have names.

**Last updated:** 2026-04-18 (added for v0.2 rewrite)

---

## 1. Architecture layers

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| Layer 1 — Data | 第 1 层 数据层 | On-disk format; never talks to LLM. |
| Layer 2 — Control | 第 2 层 控制层 | The `engram` CLI family; LLM-optional. |
| Layer 3 — Intelligence | 第 3 层 智能层 | Relevance / consistency / autolearn / evolve / messenger / wisdom. All optional, all append-only journaled. |
| Layer 4 — Access | 第 4 层 接入层 | Adapters, MCP, prompt pack, SDKs — how LLMs talk to the store. |
| Layer 5 — Observation | 第 5 层 观察层 | `engram-web` UI for humans. |

## 2. Asset classes

Distinguished by **function** (what the asset *is*), not by size. All three have **no hard size cap** — the system uses adaptive signals (§16) instead of fixed thresholds.

| English | 中文 | Function | Required structure |
|---------|------|----------|-------------------|
| Memory | 记忆 | An **atomic assertion** — one fact / rule / preference / pointer that can be independently superseded | A single `.md` with frontmatter + body |
| Workflow | 工作流 | An **executable procedure** — has a spine that can actually run | `workflow.md` + `spine.*` + `fixtures/` + `metrics.yaml` + `rev/` |
| Knowledge Base (KB) | 知识库 | A **domain reference** — multi-chapter document a human would read deliberately | `README.md` + chapter sections + `assets/` + `_compiled.md` (LLM-generated digest) |
| Playbook | 剧本 | Installable bundle: one or more Workflows + KB articles + seed Memory, distributable via `engram playbook publish` and `engram playbook install github:<owner>/<repo>` |

## 3. Memory subtypes (§4 of SPEC)

Six subtypes. Subtype captures **epistemic status** (who authored, how it's known to be true) and is orthogonal to `scope`.

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| `user` | 用户型 | Facts about the human — kept from v0.1. |
| `feedback` | 反馈型 | Rules the LLM must follow, human-authored — kept from v0.1, now requires `enforcement`. |
| `project` | 项目型 | Ongoing work, absolute dates only — kept from v0.1. |
| `reference` | 引用型 | Pointers to external systems — kept from v0.1. |
| `workflow_ptr` | 工作流指针 | Lightweight pointer into `workflows/<name>/`; LLM sees this in MEMORY.md, not the whole workflow doc. |
| `agent` | 代理元指令 | LLM-learned meta-heuristic. Different from `feedback` because the source is the LLM itself, not a human — lower default trust, tighter consistency scrutiny. |

> **Note:** Earlier v0.2 drafts had a seventh subtype `team`. It was dropped because "team compliance rule" is expressible as `feedback` + `scope: team` + `enforcement: mandatory`. Subtypes are kept orthogonal to scope.

## 4. Scope model (§8 of SPEC)

Two orthogonal axes, five labels total.

### 4a. Hierarchy axis — membership, inherited automatically

Four positions, highest generality to most specific. Conflict resolution: most specific wins within the same `enforcement` level (`project > user > team > org`).

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| `org` | 组织级 | `~/.engram/org/<name>/`; git-synced; company/organization rules. A user belongs to 0 or 1 org. Highest authority. |
| `team` | 团队级 | `~/.engram/team/<name>/`; git-synced; team or department conventions. A user may belong to multiple teams. |
| `user` | 用户级 | `~/.engram/user/`; this user's cross-project baseline. Not shared. |
| `project` | 项目级 | `<project>/.memory/local/`; this project only. Most specific. |

### 4b. Subscription axis — pool, orthogonal

Pool content participates in conflict resolution at the hierarchy level where it was subscribed (`subscribed_at`), not at a fixed "pool level".

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| `pool` | 池（订阅） | `~/.engram/pools/<name>/`; topic-shared, opt-in by subscriber. Each subscriber declares `subscribed_at: org \| team \| user \| project`, which determines the pool's effective hierarchy level for that subscriber. |

### 4c. Subscription resolution

| `subscribed_at` | Meaning |
|-----------------|---------|
| `org` | Pool behaves as org-level content for every project in the org. |
| `team` | Pool behaves as team-level content for every project in that team. |
| `user` | Pool behaves as user-level content for all of this user's projects. |
| `project` | Pool behaves as project-level content for this one project only. |

## 5. Enforcement levels

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| mandatory | 强制级 | Cannot be overridden by a lower scope; `engram validate` errors. |
| default | 默认级 | May be overridden, but the overriding asset must declare `overrides: <id>`. |
| hint | 建议级 | Freely overridable without explanation. |

## 6. Intelligence Layer components (§5 of DESIGN)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| Relevance Gate | 相关性闸门 | Ranks + filters candidate assets into the context budget. The only intelligence component that mutates the LLM's visible state. |
| Consistency Engine | 一致性引擎 | Four-phase scan detecting seven conflict classes. Only suggests; never mutates. |
| Autolearn Engine | 自学习引擎 | Workflow-level evolution loop; disciplined after Karpathy's `autoresearch`. |
| Evolve Engine | 演化引擎 | Memory-level evolution via ReMem action-think-refine; monthly cadence; proposals only. |
| Inter-Repo Messenger | 跨仓传信器 | Point-to-point inbox between repos; complements pool propagation. |
| Wisdom Metrics | 智慧指标 | Four quantitative curves proving the system gets smarter. |

## 7. Consistency conflict classes (§11 of SPEC)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| factual-conflict | 事实冲突 | Two assets disagree on a fact. |
| rule-conflict | 规则冲突 | Two `feedback`/`team` items prescribe opposite actions. |
| reference-rot | 引用失效 | A `reference` asset points to a resource that no longer exists. |
| workflow-decay | 工作流衰变 | A workflow spine calls a tool / path that's gone. |
| time-expired | 时间过期 | An `expires:` date has passed but the asset is still referenced. |
| silent-override | 静默覆盖 | A newer asset effectively supersedes an older one without declaring `supersedes:`. |
| topic-divergence | 同题分歧 | Multiple assets on the same topic reach inconsistent conclusions. |

## 8. Memory lifecycle states

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| draft | 草稿 | Written but not yet validated / indexed. |
| active | 活跃 | Currently influencing LLM behavior. |
| stable | 稳定 | Validated repeatedly; unlikely to change soon. |
| deprecated | 待退 | Marked for removal; still readable, flagged in review. |
| archived | 已归档 | Moved to `~/.engram/archive/`; retrievable, not loaded. |
| tombstoned | 已删除 | Referenced only by ID in journal; physical file removed after archive retention. |

## 9. Confidence & evidence terms

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| validated_count | 验证次数 | Times the LLM acted on this asset and reality confirmed it. |
| contradicted_count | 证伪次数 | Times reality contradicted the asset. |
| last_validated | 最近验证 | ISO 8601 timestamp of the last positive outcome. |
| usage_count | 调用次数 | Times this asset entered an LLM context. |
| confidence_score | 置信分 | `(validated - 2*contradicted - staleness_penalty) / max(1, total_events)`. |
| staleness_penalty | 陈旧惩罚 | 0 (<90d), 0.3 (90–365d), 0.7 (>365d) without re-validation. |
| outcome event | 结果事件 | A single journal row recording success / failure / contradiction. |
| evidence-driven | 证据驱动 | Decisions come from recorded outcomes, not vibes. |

## 10. Propagation & inbox terms (§9, §10 of SPEC)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| propagation | 传播 | Spread of pool-level updates to subscribers. |
| auto-sync | 自动同步 | Subscriber's symlink auto-follows pool's `current` revision. |
| notify | 通知式 | Subscriber gets a journal entry, decides accept / reject / override. |
| pinned | 钉版 | Subscriber locked to a specific revision; no auto-update. |
| subscriber | 订阅者 | A project consuming a pool. |
| pool maintainer | 池维护者 | Has write access to a pool (often enforced via Git CODEOWNERS). |
| inbox | 收件箱 | `~/.engram/inbox/<repo-id>/`; point-to-point cross-repo messages. |
| intent | 意图 | Inbox message category: `bug-report` / `api-change` / `question` / `update-notify` / `task`. |
| acknowledged | 已确认 | Recipient LLM has read the message and taken responsibility. |
| resolved | 已解决 | Recipient has acted; sender will be notified on next startup. |

## 11. Access paths (§6 of DESIGN)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| adapter | 适配器 | One-file prompt template per tool: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules`, `system_prompt.txt`. |
| MCP server | MCP 服务 | `engram mcp serve`; stateless; exposes typed tools. |
| prompt pack | 提示包 | Single-file context bundle emitted by `engram context pack`, for local / small / offline models. |
| SDK | SDK | Python `engram` and TypeScript `@engram/sdk` libraries for custom agents. |
| context budget | 上下文预算 | Token ceiling the Relevance Gate must pack into. |

## 12. Web UI pages (§7 of DESIGN)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| Dashboard | 总览面板 | Top-of-funnel: counts, wisdom sparklines, attention items. |
| Graph | 知识图谱 | D3 force layout of assets + references + subscriptions. |
| Memory Detail | 记忆详情 | Frontmatter + body editor; inbound/outbound references; blame timeline. |
| Workflow Detail | 工作流详情 | Doc + spine side-by-side; rev chart; autolearn control. |
| KB Article | 知识文章 | Source + `_compiled.md` side-by-side. |
| Pool Manager | 池管理 | Pools × subscribers table; propagate UI. |
| Project Overview | 项目总览 | All engram projects on the machine; wisdom comparison. |
| Context Preview | 上下文预览 | Simulate any task + any model; see exactly what the LLM will load. |
| Autolearn Console | 自学习控制台 | Live `evolution.tsv` tail; start/pause; past runs. |
| Inbox | 收件箱 | Cross-repo message view; send / read / resolve UI. |

## 13. CLI command family (§4 of DESIGN)

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| `engram init` | 初始化 | Create `.memory/` with seeds, adapters, subscriptions. |
| `engram memory` | 记忆 | CRUD on Memory assets: `add` / `list` / `read` / `update` / `archive` / `search`. |
| `engram workflow` | 工作流 | `add` / `run` / `revise` / `promote` / `rollback` / `autolearn`. |
| `engram kb` | 知识库 | `new-article` / `compile` / `list` / `read`. |
| `engram pool` | 池 | `create` / `list` / `subscribe` / `unsubscribe` / `publish` / `propagate`. |
| `engram team` | 团队 | `join` / `sync` / `publish` / `status`. |
| `engram inbox` | 收件箱 | `list` / `send` / `read` / `acknowledge` / `resolve` / `reject`. |
| `engram consistency` | 一致性 | `scan` / `report` / `resolve <id>`. |
| `engram context` | 上下文 | `pack` / `preview`. |
| `engram mcp` | MCP | `serve [--transport=stdio|sse]`. |
| `engram web` | Web | `serve` / `open`. |
| `engram playbook` | 剧本 | `pack` / `install` / `uninstall` / `publish`. |
| `engram migrate` | 迁移 | `--from=v0.1 \| claude-code \| chatgpt \| mem0 \| obsidian \| letta`. |
| `engram review` | 健康审查 | Aggregate consistency / propagation / inbox issues. |
| `engram validate` | 校验 | Structural + semantic validation, CI-friendly exit codes. |
| `engram snapshot` | 快照 | Create / restore tarball + checksums. |
| `engram export` | 导出 | Emit markdown / prompt / JSON for external use. |
| `engram wisdom report` | 智慧报告 | Print the four metric curves. |

## 14. Core philosophy shorthand

| English | 中文 | Notes / rationale |
|---------|------|-------------------|
| no auto-delete | 永不自动删 | Deletions go through `archive/`; retention ≥ 6 months. |
| no capacity cap | 无容量上限 | Disk is cheap; quality maintained by Consistency Engine, not shrinkers. |
| LLM-first | LLM 优先 | Primary reader is any LLM; human UX second (but not afterthought). |
| data over tool | 数据高于工具 | The markdown store outlives engram itself. |
| portability > cleverness | 可移植 > 花哨 | Boring markdown beats proprietary formats on decade scales. |
| quality over quantity | 质量优于数量 | A hundred curated memories beat a thousand noisy ones. |
| evidence-driven evolution | 证据驱动演化 | Confidence, not intuition, decides when to retire a memory. |

## 15. Referenced prior art (shortcuts)

These names appear repeatedly in design discussion; use the short form in docs and link to the canonical source on first mention.

| Short form | Full reference | Canonical link |
|------------|----------------|----------------|
| autoresearch | Karpathy's `autoresearch` project (8-discipline agentic loop) | `/Users/sky/linux-kernel/github/autoresearch/program.md` |
| evo-memory | DeepMind 2025 Search-Synthesize-Evolve paper | `/Users/sky/linux-kernel/ai-doc/memory-systems/evo-memory.md` |
| agent-factory | Agent Factory 2026-03 — experience as code | `/Users/sky/linux-kernel/ai-doc/self-improving-agents/agent-factory.md` |
| MemoryBank | Ebbinghaus-curve LLM memory paper | `/Users/sky/linux-kernel/ai-doc/memory-systems/memorybank.md` |
| MemGPT / Letta | Memory as OS virtual memory | `/Users/sky/linux-kernel/ai-doc/memory-systems/memgpt.md` |
| Karpathy LLM Wiki | LLM-compiled personal knowledge base | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f |

---

## 16. Adaptive signals (replacing fixed size thresholds)

engram does **not** set hard line-count limits on any asset class. Instead, three adaptive signals surface *review candidates* to the owner without blocking or warning. All are **suggestive, never enforcing**.

| English | 中文 | Trigger / behavior |
|---------|------|-------------------|
| Dynamic budget allocation | 动态预算分配 | Relevance Gate shifts per-type token budget based on utilization rate observed in Wisdom Metrics. Frequently-used types get more context budget. |
| Percentile length signal | 百分位长度信号 | If an asset's length is ≥95th percentile within its type / scope, `engram review` lists it under "consider review". Threshold is project-relative, not absolute. M4 feature. |
| Split / promote / demote proposal | 拆分 / 升级 / 降级建议 | Evolve Engine proposes: *split* (memory contains 2+ disjoint semantic clusters), *promote to KB* (3+ memories co-load >60% of the time), *demote workflow→memory* (spine unused 90d), *promote memory→workflow* (memory encodes procedural steps reused across tasks). Proposals only; never auto-executed. M5 feature. |

## 17. Retrieval algorithm terms (MemPalace-style hybrid)

| English | 中文 | Meaning |
|---------|------|---------|
| Hybrid retrieval | 混合检索 | BM25 + vector fusion scoring. `fused_dist = dist * (1.0 - 0.30 * overlap)`. |
| Temporal date boost | 时间邻近加权 | For queries containing "N weeks ago" etc., up to 40% distance reduction for sessions near the target date. |
| Two-pass retrieval | 两段检索 | For assistant-reference queries ("you said X"), first pass on user-turns-only index, second pass includes assistant turns on top candidates. |
| BM25 fusion | BM25 融合 | Keyword overlap scoring with Okapi-BM25, computed against retrieved candidates. |
| Stop word list | 停用词表 | 32-term common-word list stripped from queries before keyword extraction. |

## 18. Autolearn terms (Darwin-style)

| English | 中文 | Meaning |
|---------|------|---------|
| Ratchet | 棘轮 | Every autolearn round is a git commit; metric regress → auto-revert; metric improve → keep. Scores monotonically increase. |
| Dual evaluation | 双维度评分 | 100-point rubric: static 60 (SPEC compliance + fixtures + parseable + no secrets) + performance 40 (fixtures pass + metric Δ > 0). |
| Independent evaluator | 独立评估 | The subagent that proposes a change and the subagent that grades it are different contexts — no self-assessment bias. |
| Phase gate | 阶段闸门 | After K=5 consecutive autolearn rounds, pause and write diff summary to `engram review`; human confirms before next phase. |

## 19. Temporal validity fields

| English | 中文 | Meaning |
|---------|------|---------|
| `valid_from` | 起效日 | ISO 8601 date. The fact became true on or after this date. Optional frontmatter. |
| `valid_to` | 失效日 | ISO 8601 date. The fact stopped being true on this date. Optional frontmatter. |
| `expires` | 过期日 | Single-point "may be stale after" marker. Complements valid_from/to — expires signals a review prompt; valid_to signals the fact is historically bounded. |
| Time-filtered query | 时间过滤查询 | graph.db operation "what was true on date X?" — returns assets whose validity window covers X. |

## 20. Performance budgets

| Name | 中文 | Target |
|------|------|--------|
| Hook latency | 钩子延迟 | Each Claude Code hook (`engram_stop.sh`, `engram_precompact.sh`) completes in <500ms |
| Startup context injection | 启动上下文注入 | MEMORY.md + Level 1 essentials load in <100ms |
| `engram review` | 健康审查 | <2s on a store of ~1000 assets |
| LongMemEval Relevance Gate | 检索基准(防御性) | ≥95% R@5 as baseline (not a headline metric) |

---

## Adding or renaming a term

1. Discuss in a PR that touches only `docs/glossary.md` + `docs/glossary.zh.md`.
2. If renaming: `grep -rn "<old term>" *.md docs/` and update every hit in the same PR.
3. The PR description MUST explain why the old name was wrong (or what gap the new term fills).
4. A term is ready only when both the English and Chinese rows are filled and the "Notes / rationale" column justifies the choice.
