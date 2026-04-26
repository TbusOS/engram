# AGENTS.md — LLM collaborator guide for engram

[English](#english) · [中文](#中文)

---

<a name="english"></a>

## 0. Who this file is for

Any LLM (Codex, Codex, Gemini, Cursor, local models) that opens this
repository to help with development. Read this file once at the start
of a session. It is **≤300 lines on purpose** — the full specifications
live in `SPEC.md`, `DESIGN.md`, `METHODOLOGY.md`, and `TASKS.md`.

## 1. The project in three sentences

engram is a **local, portable, LLM-agnostic long-term memory system**
that stores knowledge as plain markdown files under `.memory/` and
`~/.engram/`. It targets the gap between "scratch notes in AGENTS.md"
and "hosted RAG service" — small teams and solo engineers who need
curated, versioned, auditable memory that any LLM can read without a
proprietary SDK. Success looks like an engineer using engram for six
months and pointing at the `confidence_score` curve: "my assistant
genuinely got smarter."

## 2. Architecture at a glance

- **Five layers** (DESIGN §2): Data → Control → Intelligence → Access → Observation.
- **Three asset classes** (SPEC §3.1): `Memory` (short primers),
  `Workflow` (procedures with executable `spine.*` + fixtures + metrics
  + rev history), `Knowledge Base` (long articles with LLM-compiled
  digest).
- **Two-axis scope model** (SPEC §8): four-level hierarchy
  (`org > team > user > project`) plus an orthogonal `pool` axis with
  `subscribed_at` — the pool axis is NOT a fifth hierarchy level.
- **Three enforcement levels**: `mandatory` (wins absolutely) >
  `default` > `hint`.

When in doubt about layout, read the top of `SPEC.md` — the
`<project-root>/.memory/` tree is the authoritative contract.

## 3. Setup and commands

```bash
# Install (editable)
cd cli && pip install -e ".[dev]"

# Run the CLI
engram --version
engram init --name demo
engram memory add --type=user --name=role --description=… --body=…

# Tests (target 80%+ coverage)
pytest                      # full suite (500+ tests currently)
pytest tests/unit/cli/      # fast unit tests
pytest tests/e2e/           # end-to-end slower

# Lint + type
ruff check cli/engram/
cd cli && mypy engram/
```

The repo has no Makefile on purpose — the commands are short enough
that copying them into muscle memory is better than hiding them
behind targets.

## 4. Authority chain — SPEC > DESIGN > TASKS

When a conflict arises among `SPEC.md`, `DESIGN.md`, and `TASKS.md`,
**SPEC wins, then DESIGN, then TASKS**. Examples hit so far:

- TASKS said validate exit codes are `1=errors, 2=warnings`; SPEC §12.13
  said the opposite — implementation follows SPEC, TASKS got a
  correction note.
- TASKS said "reject unknown frontmatter fields"; SPEC §4.1 said
  "MUST be preserved" — implementation preserves.
- Migration §13.4 said `confidence: {}` but parser §4.8 required
  sub-fields — applied SPEC §13.7 "additive default = least-surprising
  value" with a zero-state block.

Record every deviation in the commit message and in
`memory/project_tasks_vs_spec_authority.md`. Don't re-debate decisions
that are already frozen; reopen SPEC only with explicit user go-ahead.

## 5. Code discipline

- **Module layout** (DESIGN §4.2): any feature expected to span multiple
  logic concerns goes directly into `engram/<feature>/{commands, …logic}.py`.
  Do not start in a flat `commands/<feature>.py` "and split later" —
  splitting later is never free.
- **No emoji in commits, docs, or code** unless explicitly asked.
- **Generic examples only** — never internal product / customer names in
  public docs, tests, or commits. Use `acme-*`, `platform-*`,
  `example.internal`.
- **Commit after every completed task, push immediately**. The project
  is open-source; the evolution should be public. User has granted
  standing authorization for `git push` without per-commit confirmation.
- **No compromise on core quality** — when a design choice gets
  "simpler" at the expense of the core invariants (LLM-agnostic,
  local-first, scope-aware, auditable), stop and ask.

Global language rule (`~/.Codex/rules/language.md`): ban Chinese
buzzwords like 矩阵 / 赋能 / 抓手 / 闭环 / 沉淀 / 打通 / 颗粒度 / 底层逻辑
and English buzzwords like synergy / leverage / at-scale / deep-dive.
Plain technical prose, specific numbers.

## 6. Testing discipline

- **TDD by default**: write the failing test, then implement.
- **One task = one commit = +N unit tests**; for user-facing changes,
  add an E2E test under `tests/e2e/`.
- **80%+ coverage** is the floor; the current suite is 500+ tests at
  ~94% coverage on core modules.
- **Never delete tests to make the build green**. If a test is wrong,
  fix it as a separate commit with a rationale.

## 7. When to dispatch a subagent

Dispatch to `Agent` tool when:

- The question spans many files and would take >3 sequential greps.
- Independent work streams can run in parallel (multiple files, no
  dependency).
- Protect the main context window from large search-result dumps.

Don't dispatch when:

- The target is already known (use `Read` + `Grep` directly).
- The decision requires judgment calls tied to this conversation's
  context (subagents don't see it).

Every dispatched subagent prompt must be self-contained (subagents
have no memory of this session) and should state the expected format
and length.

## 8. Memory system usage during development

- Every session reads `MEMORY.md` at the top.
- After learning something non-obvious (a user correction, a design
  decision, a deviation from SPEC/DESIGN), save it as a `feedback` or
  `project` memory in `memory/`.
- **Don't save code patterns, file paths, or recent changes** — those
  come from reading the repo or `git log`.
- Memory is shared across sessions; don't record ephemeral task state.

## 9. Never do

- Never auto-delete or rewrite an existing memory without a user
  prompt. Deletions flow through `archive/` with a 6-month floor.
- Never bypass git hooks with `--no-verify` unless the user asks.
- Never force-push `main`.
- Never invent a commit SHA or a test number in a status message — run
  `git log --oneline -1` / `pytest -q` and read the real value.
- Never write AGENTS.md / AGENTS.md sections that talk down to the
  reader. These files are for peers.

## 10. Navigation map

| File | Purpose | Read when |
|---|---|---|
| `SPEC.md` | On-disk format contract | writing / validating assets |
| `DESIGN.md` | Layer + algorithm details | implementing a subsystem |
| `TASKS.md` | 105-task rolling board | picking the next task |
| `METHODOLOGY.md` | How LLMs contribute (12 discipline rules) | the first session in a while |
| `CONTRIBUTING.md` | Contribution workflow | first-time contributor |
| `docs/glossary.md` | ~100 terms, 15 categories | unfamiliar acronym |
| `docs/superpowers/` | Per-initiative specs + plans | starting a multi-week effort |
| `memory/MEMORY.md` | Per-user memory index | every session start |

---

<a name="中文"></a>

## 0. 这个文件写给谁

任何打开这个仓库来帮忙开发的 LLM(Codex、Codex、Gemini、Cursor、本地
模型)。每个会话开头读一次。**故意控制在 300 行内** —— 详细规格在
`SPEC.md` / `DESIGN.md` / `METHODOLOGY.md` / `TASKS.md` 里。

## 1. 三句话讲清这个项目

engram 是一个**本地、可移植、不绑定任何 LLM** 的长期记忆系统,把知识
存成 `.memory/` 和 `~/.engram/` 下的普通 markdown 文件。它瞄准"AGENTS.md
的散乱笔记"和"托管 RAG 服务"之间的空档 —— 小团队和独立工程师需要经过
整理、可版本化、可审计,任何 LLM 不需要专属 SDK 就能读的记忆。成功的
样子:一个工程师用 engram 半年后指着 `confidence_score` 曲线说"我的
助手真的变聪明了"。

## 2. 架构速览

- **5 层**(DESIGN §2):Data → Control → Intelligence → Access → Observation
- **3 类资产**(SPEC §3.1):`Memory`(短 primer)/ `Workflow`(文档 +
  可执行 `spine.*` + fixtures + metrics + 版本历史)/ `Knowledge Base`
  (长文 + LLM 编译的 digest)
- **2 轴 scope 模型**(SPEC §8):4 级归属(`org > team > user > project`)
  + 正交 `pool` 轴(按 `subscribed_at` 投影)—— pool 不是第 5 级层级
- **3 enforcement 等级**:`mandatory`(绝对胜出)> `default` > `hint`

布局拿不准时读 `SPEC.md` 开头,`<project-root>/.memory/` 树是权威合约。

## 3. 建仓 + 构建命令

```bash
# 安装(editable)
cd cli && pip install -e ".[dev]"

# 跑 CLI
engram --version
engram init --name demo
engram memory add --type=user --name=role --description=… --body=…

# 测试(目标覆盖率 80%+)
pytest                      # 整库(当前 500+ 测试)
pytest tests/unit/cli/      # 快速单测
pytest tests/e2e/           # 较慢端到端

# Lint + 类型
ruff check cli/engram/
cd cli && mypy engram/
```

故意没 Makefile —— 命令本身就够短,让它们进肌肉记忆比藏在 target 后面
更好。

## 4. 权威链:SPEC > DESIGN > TASKS

当 `SPEC.md` / `DESIGN.md` / `TASKS.md` 冲突时,**SPEC 先赢,DESIGN 次之,
TASKS 最后**。M2/M3 已经撞到的几次:

- TASKS 写 validate 退出码 `1=errors, 2=warnings`;SPEC §12.13 写反了
  —— 实现按 SPEC,TASKS 加了一条校正说明。
- TASKS 写"遇到未知 frontmatter 字段就 raise";SPEC §4.1 写"MUST be
  preserved" —— 实现按 SPEC 保留。
- Migration §13.4 写 `confidence: {}`,但 parser §4.8 要子字段齐备 ——
  按 SPEC §13.7 "additive default" 规则用零态块。

每次偏离都在 commit message 里记清楚,加一条到 `memory/project_tasks_vs_spec_authority.md`。
不要反复 debate 已经冻结的决定;重开 SPEC 需用户明确同意。

## 5. 代码纪律

- **模块布局**(DESIGN §4.2):任何预计会跨多个逻辑关注点的功能,直接进
  `engram/<feature>/{commands, …logic}.py`。不要先塞 `commands/<feature>.py`
  "以后再拆" —— 以后拆从来不是免费的。
- **commit / 文档 / 代码里不用 emoji**,除非明确要求。
- **只用通用示例** —— 公开文档、测试、commit 永不出现内部产品名或客户名。
  用 `acme-*` / `platform-*` / `example.internal`。
- **每完成一个 Task 立即 commit + push**。项目开源,演进应该公开。用户
  已明确授权 git push 不用每次询问。
- **核心质量不妥协** —— 当设计的"简化"以损失核心不变量(LLM-agnostic /
  local-first / scope-aware / auditable)为代价时,停下来问用户。

全局语言规则(`~/.Codex/rules/language.md`):禁 矩阵 / 赋能 / 抓手 /
闭环 / 沉淀 / 打通 / 颗粒度 / 底层逻辑 等中文黑话,也禁 synergy /
leverage / at-scale / deep-dive 等英文 buzzword。白话 + 精确技术术语 +
具体数字。

## 6. 测试纪律

- **默认 TDD**:先写失败测试,再实现。
- **一个 Task = 一个 commit = +N 单测**;用户可见的改动加 `tests/e2e/`
  端到端。
- **80%+ 覆盖率**是下限;当前整库 500+ 测试,核心模块约 94%。
- **绝不删测试换 green**。测试本身错了,单独提一个 commit 修并写理由。

## 7. 子 agent 什么时候用

用 `Agent` 工具的场景:

- 问题跨多文件,连续 grep >3 次才能回答
- 有独立工作流可以并行(多文件,无依赖)
- 保护主上下文窗口不被大规模搜索结果撑满

不要用的场景:

- 目标已知(直接 `Read` + `Grep`)
- 判断绑在当前对话上下文上(subagent 看不到)

每个 subagent 的 prompt 必须自包含(subagent 没本次会话记忆),要说清楚
期望的格式和长度。

## 8. 开发过程中的记忆系统用法

- 每个会话开头先读 `MEMORY.md`
- 学到非显然的东西(用户校正 / 设计决策 / 偏离 SPEC/DESIGN)就存成
  `feedback` 或 `project` memory,放在 `memory/`
- **不要存代码模式 / 文件路径 / 最近改动** —— 读仓库或 `git log` 都有
- 记忆跨会话共享,不记瞬时任务状态

## 9. 永远不做

- 永远不在没用户要求时 auto-delete 或改写已有 memory。删除走 `archive/`
  + 6 个月最低保留。
- 永远不加 `--no-verify` 跳过 git hook,除非用户明说。
- 永远不 force-push `main`。
- 永远不在 status 消息里瞎编 commit SHA 或测试数字 —— 跑
  `git log --oneline -1` / `pytest -q` 读真值。
- 永远不在 AGENTS.md / AGENTS.md 里写俯视读者的话。这些文件是写给同侪的。

## 10. 路由图

| 文件 | 作用 | 什么时候读 |
|---|---|---|
| `SPEC.md` | 磁盘格式合约 | 写 / 校验资产时 |
| `DESIGN.md` | 层 + 算法细节 | 实现子系统时 |
| `TASKS.md` | 105 条滚动任务板 | 挑下一个 task 时 |
| `METHODOLOGY.md` | LLM 如何参与开发(12 条纪律) | 隔一段时间再进来时 |
| `CONTRIBUTING.md` | 贡献流程 | 第一次贡献时 |
| `docs/glossary.md` | 约 100 个术语、15 类 | 遇到陌生术语时 |
| `docs/superpowers/` | 每个 initiative 的 spec + plan | 启动多周工作时 |
| `memory/MEMORY.md` | 每用户的记忆索引 | 每个会话开头 |
