[English](DESIGN.md) · [中文](DESIGN.zh.md)

# engram 系统设计

**版本**: 0.2（草稿）
**状态**: 设计草稿，SPEC v0.2 的配套文档
**最后更新**: 2026-04-18
**规范地址**: https://github.com/TbusOS/engram/blob/main/DESIGN.md
**术语表**: [docs/glossary.md](docs/glossary.md) — 本文档所有术语均遵循该表
**SPEC**: [SPEC.md](SPEC.md) — 本设计所实现的格式契约

---

## 0. 目的

`DESIGN.md` 规定 engram v0.2 的**实现架构**。`SPEC.md` 定义磁盘格式；本文档定义需要构建哪些代码来处理该格式、这些代码如何组织为五层架构，以及每层形态的原因。

### SPEC 与 DESIGN 的分工

划分原则：如果修改某个细节会要求所有读取该存储的工具都更新，则归属 SPEC。如果描述的是某个具体工具（engram-cli、engram-web、MCP 服务）如何实现该规范，则归属本文档 DESIGN。

具体示例：记忆资产的 YAML frontmatter 模式是 SPEC 领域；验证该 frontmatter 的 Python 函数是 DESIGN 领域。`enforcement` 字段语义是 SPEC；一致性引擎用于检测 `rule-conflict` 违规的算法是 DESIGN。

### 作用域

DESIGN 覆盖第 2 层（控制层）到第 5 层（观察层）。第 1 层完全是 SPEC 领域；本文档不重新定义 SPEC 中已有的内容。

- **第 2 层 — 控制层**：`engram` CLI 命令族；所有子命令、标志、错误码和输出格式。
- **第 3 层 — 智能层**：相关性闸门、一致性引擎、自学习引擎、演化引擎、跨仓传信器和智慧指标——使存储能自我改进的可选组件。
- **第 4 层 — 接入层**：适配器、MCP 服务、提示包、Python SDK、TypeScript SDK——LLM 与存储交互的方式。
- **第 5 层 — 观察层**：`engram-web`，面向人类的一流仪表板，用于查看知识图谱和管理存储。

### 受众

工具实现者是主要受众：任何构建 engram 兼容 CLI、适配器、Web 服务或 SDK 的人，应能够结合 SPEC 和 DESIGN 推导出完整的实现方案。设计评审者（评估架构决策）是次要受众。希望理解系统行为原因的高级用户是第三受众。

### 契约边界

DESIGN 描述具体的技术选型——Python + FastAPI、用于图缓存的 SQLite、用于本地嵌入的 bge-reranker-v2-m3——这些可以随时间调整而不破坏 SPEC 兼容性。使用 LanceDB 替代 SQLite 存储图的工具，只要满足本文档的所有不变式和 SPEC 的所有规则，仍然是合规的 engram 实现。

后续章节详细介绍每一层；第 2 节提供五层架构概览。

---

## 1. v0.1 → v0.2 定位变更

### 1.1 变更对比表

| 维度 | v0.1 | v0.2 | 变更原因 |
|------|------|------|----------|
| **架构层数** | 3 层（数据层 / CLI / 适配器） | 5 层（数据层 / 控制层 / 智能层 / 接入层 / 观察层） | 智能层和观察层解决的是全新问题，无法在不产生严重耦合的情况下塞进 CLI 或适配器。 |
| **记忆子类型** | 4 种（`user`、`feedback`、`project`、`reference`） | 6 种（新增 `workflow_ptr`、`agent`） | 更丰富的认识论建模：`workflow_ptr` 是指向完整工作流资产的轻量索引项；`agent` 捕获 LLM 推导的元启发式，区别于人类编写的 `feedback`。 |
| **一等资产** | 仅记忆 | 记忆 + 工作流 + 知识库 | 三类知识在结构、生命周期和加载路径上存在本质差异；将它们合并为单一类型会产生体积过大、难以加载的记忆文件。 |
| **Scope 模型** | 2 级（本地 / 通过 symlink 的共享池） | 5 个标签，2 轴：归属层次（`org` / `team` / `user` / `project`）+ 正交订阅（`pool` + `subscribed_at`） | 真实团队以多种方式共享知识；线性层次无法表达"以团队级别订阅但无团队成员资格的主题池"，也无法表达允许项目级覆盖的组织强制规则。 |
| **强制性** | 隐式（所有记忆权重相等） | 显式（`mandatory` / `default` / `hint`） | 确定性冲突解决需要显式权威排序；若无强制级别，两条相互矛盾的规则无法解决。 |
| **MEMORY.md 容量** | 硬性上限 200 行 | 无上限的分层落地索引 | 支持跨范围分布的数千个资产；索引按层次和类型组织，LLM 可以增量导航，无需一次全部加载。 |
| **容量维护** | 用户手动审查 | 一致性引擎检测 7 类冲突并提出修复建议；永不自动 mutate | 可扩展的质量维护。超过 500 个资产后手动审查会崩溃；证据驱动的建议能在不破坏任何内容的前提下浮现关键问题。 |
| **跨项目知识** | 基于 symlink 的共享池 | 池传播（自动同步 / 通知式 / 钉版）+ 跨仓传信器收件箱 | 两种互补机制：池传播适用于多项目共享的主题知识；收件箱适用于特定仓库之间的点对点通信。每种机制覆盖另一种无法处理的场景。 |
| **LLM 接入路径** | 仅适配器（提示模板） | 适配器 + MCP 服务 + 提示包 + Python SDK + TypeScript SDK | 在 LLM 所在的地方与之对接：IDE 集成使用 MCP；小型/本地模型使用提示包；自定义代理使用 SDK；适配器适用于最简单的场景。 |
| **Web UI** | 无 | 一等观察层（`engram-web`，FastAPI + Svelte） | 人类需要查看知识图谱、模拟上下文加载、审查一致性引擎的建议；纯 CLI 界面无法提供能够早期发现质量问题的空间概览。 |
| **自我改进** | 无 | 自学习引擎（工作流级）+ 演化引擎（记忆级）+ 智慧指标（4 条量化曲线） | 可量化的证据证明存储随时间变得更智能，而不仅仅是更大；智慧指标将"感觉更有用"转化为可以回归或改进的数字。 |
| **后端抽象** | 无（仅文件系统） | `BaseCollection` ABC（向量/图存储接口） | 可将 ChromaDB 换成 LanceDB 或 PostgreSQL+pgvector，而不影响任何上层；接口即契约，存储引擎可替换。 |

### 1.2 为何从 3 层变为 5 层

v0.1 的三层架构（数据层 / CLI / 适配器）对单用户、单工具的记忆系统已经足够。适配器是薄薄的提示模板；CLI 处理其他一切。当 v0.2 添加智能组件——相关性闸门、一致性引擎、自学习引擎、演化引擎——这些组件无法塞进 CLI 层，否则会使 CLI 命令依赖 LLM 且无法孤立测试。智能层是可选的，必须可以禁用；它需要自己的层，拥有自己的开关。

观察层同样独立。带有图渲染器的 Web 服务器不是 CLI 命令。将它强行并入 CLI 层意味着 CLI 需要依赖 FastAPI 和 Svelte，这是荒谬的。第 5 层依赖第 4 层的数据访问原语，但增加了完全不同的运行时（长运行的 HTTP 服务器，而非一次性命令）。五层是分离这些关注点同时避免跨层依赖的最小层数。

### 1.3 为何从 2 级变为 5 个标签

v0.1 的 scope 模型——本地 vs. 通过 symlink 的共享池——表达了两件事："仅此项目"和"该池中的所有内容"。这对单个用户在多个个人项目上工作时是有效的。当真实团队到来时，它就崩溃了。

团队同时在多个粒度上使用知识：组织强制规定合规规则，平台团队拥有设计系统，个别工程师有个人偏好，特定项目有本地规范。线性四级层次（`org > team > user > project`）能自然处理基于成员关系的继承。但主题池——关于技术领域（如 `kernel-work` 或 `android-bsp`）的共享知识——不是基于成员关系的。订阅池不会使你成为团队成员。两个轴是真正正交的。

`subscribed_at` 字段无需发明新轴就能解决权威性问题：以 `org` 订阅的池对组织内所有项目具有与组织级内容相同的权威性；以 `project` 订阅的池仅对该单一项目具有权威性。池内容在声明的层次级别参与冲突解决，而非在一个对所有用例来说要么太高要么太低的固定"池级别"参与。

### 1.4 为何添加一致性引擎

一致性引擎是 v0.2 中最重要的能力赌注。前提是：在没有质量维护的情况下增长的存储会成为负担：相互矛盾的规则堆积，过期引用在索引中保持有效，项目结束后项目级事实依然活跃。v0.1 依赖用户手动发现这些问题。手动审查在 20 个资产时有效，200 个时失败，2000 个时毫无希望。

一致性引擎运行四阶段扫描——结构验证、语义冲突检测、引用健康检查和陈旧度评分——并提交建议而不执行。这是关键设计选择：建议，而非 mutation。一个静默修改资产的自动修正引擎会破坏使存储可靠的信任。用户必须确认每项变更；引擎提供证据。

七类冲突（`factual-conflict`、`rule-conflict`、`reference-rot`、`workflow-decay`、`time-expired`、`silent-override`、`topic-divergence`）覆盖了真实存储中观察到的完整质量问题分类。置信分公式（`(validated - 2×contradicted - staleness_penalty) / max(1, total_events)`）将这些信息提炼为每个资产的单一数字，使即便在大规模时也能进行可处理的优先级排序。

---

## 2. 五层架构

### 2.1 架构图与层角色

```
┌──────────────────────────────────────────────────────────────────────────┐
│  第 5 层  观察层               engram-web：总览面板 / 知识图谱 / 上下文   │
│           (FastAPI + Svelte)  预览 / 收件箱 / 自学习控制台 / ...         │
├──────────────────────────────────────────────────────────────────────────┤
│  第 4 层  接入层               适配器 | MCP 服务 | 提示包                 │
│           (面向 LLM)          | Python SDK | TypeScript SDK              │
├──────────────────────────────────────────────────────────────────────────┤
│  第 3 层  智能层               相关性闸门 · 一致性引擎 ·                  │
│           (可选，有闸门)       自学习引擎 · 演化引擎 · 跨仓传信器         │
│                               · 智慧指标                                 │
├──────────────────────────────────────────────────────────────────────────┤
│  第 2 层  控制层               engram CLI：memory / workflow / kb / pool  │
│           (LLM 可选)          / team / org / inbox / consistency /       │
│                               context / mcp / web / playbook / migrate   │
├──────────────────────────────────────────────────────────────────────────┤
│  第 1 层  数据层               .memory/ 目录 + ~/.engram/                │
│           (SPEC 定义)          SPEC 合规 markdown；任意 LLM 可读         │
└──────────────────────────────────────────────────────────────────────────┘
```

**第 1 层 — 数据层**是磁盘格式：`.memory/` 目录树和用户全局 `~/.engram/` 层次结构。它只依赖文件系统，以及可选的 git 用于历史记录。第 1 层之上的所有内容都读写这些文件。第 1 层完全由 SPEC 规定；DESIGN 不重新定义它。

**第 2 层 — 控制层**是 `engram` CLI 命令族。它依赖第 1 层（读写 SPEC 合规文件），在启用时编排第 3 层组件，并暴露面向用户的命令接口。它是 LLM 可选的：每个命令在没有 LLM 的情况下都能正确运行。第 3 层和第 4 层依赖第 2 层获取存储访问原语。技术选型：Python 3.10+ 配合 click；§3（本文档内）规定完整命令接口。

**第 3 层 — 智能层**包含使存储自我改进的可选组件：相关性闸门（将候选项排名打入上下文预算）、一致性引擎（检测冲突类别并提出修复建议）、自学习引擎（工作流级演化）、演化引擎（记忆级演化）、跨仓传信器（跨仓库的点对点通信）和智慧指标（量化自我改进证据）。第 3 层依赖第 2 层进行存储读写。第 4 层（MCP 服务和 SDK）调用相关性闸门来组装上下文。第 3 层有闸门：每个组件都有配置标志；在所有智能关闭的情况下，系统保持完全正确。§5（本文档内）规定每个组件。

**第 4 层 — 接入层**是面向 LLM 的接口：适配器（每种工具一个提示模板文件）、MCP 服务（`engram mcp serve`）、提示包（`engram context pack`）、Python SDK 和 TypeScript SDK。它依赖第 2 层进行存储访问，依赖第 3 层的相关性闸门。适配器是 LLM 的终端层。§6（本文档内）规定每条接入路径。

**第 5 层 — 观察层**是 `engram-web`：FastAPI 后端 + Svelte 前端，提供总览面板、知识图谱、记忆详情、工作流详情、上下文预览、自学习控制台、池管理和收件箱页面。它依赖第 2–4 层获取数据和智能。第 5 层完全可选：仅有第 1–4 层的系统是完全功能且 SPEC 合规的。§7（本文档内）规定 Web UI。

### 2.2 依赖规则

1. **第 N 层只依赖第 N−1 层。** 第 3 层可以调用第 2 层 API；它不得绕过第 2 层原语直接操作第 1 层文件。
2. **第 1 层只依赖文件系统**，以及可选的 git 用于历史记录。无 Python import，无网络调用，无 LLM。
3. **第 1 层（文件系统形态）是 SPEC 领域。** DESIGN 规定第 2–5 层的行为；它不重新定义目录布局、文件命名或 frontmatter 模式。
4. **第 3 层组件可独立禁用。** 禁用相关性闸门、一致性引擎或自学习引擎不影响 SPEC 合规性，也不影响第 1、2、4 或 5 层的正确性。
5. **第 5 层是可选的。** 单独的 CLI（第 1–4 层）必须产生完全功能的 SPEC 合规系统。Web UI 增加可观察性；它不作为任何存储操作的门卫。

### 2.3 不变式

以下五条不变式适用于所有层。任何 engram 实现都必须满足全部五条。满足其他要求但违反任何一条不变式的合规实现是不合规的。

1. **数据独立性。** 第 1 层绝不引用任何工具特定的路径或格式。一个 v0.2 合规存储——遵循 SPEC 的 markdown 文件目录——在零 engram-cli 安装的情况下可以正常工作。任意 LLM 可以读取，任意文本编辑器可以编辑，任意版本控制系统可以跟踪。

2. **永不自动删。** 任何层都不得静默删除存储中的资产。删除始终流经 `archive/`，物理移除前有六个月的保留下限。一致性引擎和演化引擎生成建议；只有通过 `engram memory archive` 或 `engram workflow archive` 的显式人类或 LLM 指令才能将资产移至 `archived` 状态。`enforcement: mandatory` 的强制级资产需要在创建它的范围级别采取行动。

3. **追加专用日志。** `~/.engram/journal/*.jsonl` 文件永不原地编辑。新事件追加到末尾。压缩（用于存储管理）将完整日志文件移至 `archive/journal/` 并启动新文件；它永不删除事件或修改现有行。

4. **智能层有闸门。** 每个第 3 层组件都有配置标志（`relevance_gate.enabled`、`consistency_engine.enabled`、`autolearn.enabled`、`evolve.enabled`、`messenger.enabled`、`wisdom_metrics.enabled`），具有定义的默认值，可在 `.memory/config.toml` 或 `~/.engram/config.toml` 中覆盖。在所有智能禁用时，系统仍能正确地验证、读取、写入和导出。

5. **确定性冲突解决。** 给定相同的资产集和相同的 `pools.toml`，相关性闸门的 scope/enforcement 排名和 SPEC 验证器的冲突检测在不同运行、不同环境和不同版本中产生相同的输出。无随机种子，无实现定义的平局处理，无环境敏感行为。

### 2.4 技术栈预览

详细的技术选型论证在各层专属章节中给出。下表提供参考实现选型及第三方实现可以采用的替代方案。

| 层 | 主要技术 | 允许的替代方案 |
|---|---|---|
| 第 1 层 — 数据层 | Markdown + YAML frontmatter（文件系统原生） | —（SPEC 定义；不可替换） |
| 第 2 层 — 控制层 | Python 3.10+ / click（`engram-cli` pip 包） | Go、Rust、TypeScript（任何能生成合规 CLI 的语言） |
| 第 3 层 — 智能层 | Python + SQLite（`graph.db`、嵌入缓存）+ bge-reranker-v2-m3（本地嵌入） | 按组件：详见 §5；例如向量存储可用 LanceDB 或 pgvector |
| 第 4 层 — 接入层 | Python（MCP 服务 + Python SDK）、TypeScript（`@engram/sdk`）、纯文本（提示包） | 自定义适配器可用任何语言；MCP 传输：stdio 或 SSE |
| 第 5 层 — 观察层 | FastAPI（HTTP 后端）+ Svelte（前端）+ Server-Sent Events | —（仅参考实现；Web UI 为可选） |

"主要技术"指随 engram-cli 发布的参考实现。实现任意子集栈的第三方工具——例如满足所有第 2 层行为的纯 Go CLI——只要满足 DESIGN 的所有不变式和 SPEC 的所有规则，即为合规的 engram 实现。

---

---

## 3. 第 1 层数据——实现决策

### 3.0 概述

§3 介绍**参考实现 engram-cli** 如何处理第 1 层周边的关注点——那些不属于第 1 层本身但与之密切相关的系统。磁盘格式（目录布局、文件命名、YAML frontmatter、日志文件结构）完全属于 SPEC 领域，此处不再重复。§3 规定的是 CLI 为安全、高效地操作该格式而构建的各种*系统*：

| 小节 | 关注点 |
|---|---|
| 3.1 | 文件系统约定：原子写入、权限、符号链接、编码 |
| 3.2 | `graph.db` — SQLite 模式，涵盖资产清单、引用图、订阅、收件箱、一致性与使用追踪 |
| 3.3 | `~/.engram/cache/` — 嵌入、FTS5、相关性与已编译知识库缓存 |
| 3.4 | `~/.engram/journal/` — 追加专用事件文件及每工作流日志 |
| 3.5 | `~/.engram/archive/` — 保留期、恢复与物理删除策略 |
| 3.6 | `~/.engram/workspace/` — 为自学习、演化和一致性扫描设立的隔离运行沙箱 |
| 3.7 | 快照备份与恢复 |
| 3.8 | 并发保护 — WAL 模式、文件锁、乐观资产并发 |
| 3.9 | 跨机器同步策略 |

第三方实现可以自由替换此处的任何子系统（例如将图存储在 LanceDB 中、完全跳过嵌入缓存），只要满足 SPEC 的所有规则和 §2.3 的所有 DESIGN 不变式即可。

---

### 3.1 文件系统约定

#### 原子写入

所有对资产文件、配置文件和索引文件的写入都采用**先写临时文件再重命名**的模式：

```python
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(content, encoding="utf-8")
os.replace(tmp, path)   # POSIX：原子重命名；Windows：回退到 shutil.move
```

这保证了进程崩溃或断电不会在规范路径上留下不完整的文件。`.tmp` 文件要么完整，要么不存在；永远不会处于半写状态而被误认为有效资产。

#### 权限

| 路径 | 模式 |
|---|---|
| `~/.engram/` | `0700` — 私有；仅所有者可访问 |
| `~/.engram/` 内所有目录 | `0755` |
| 所有文本文件（`*.md`、`*.jsonl`、`*.toml`、`*.json`、`*.yaml`） | `0644` |
| `graph.db`、`cache/*/index.db`、`cache/embedding/vectors.db` | `0644` |

#### 符号链接

符号链接在 SPEC 合规存储中用于两个目的：

1. **池订阅**：`.memory/pools/<name>` → `~/.engram/pools/<name>/current/`
2. **工作流修订版本指针**：`workflows/<name>/rev/current` → `rev/<timestamp>/`

工具在读取时**必须**追踪符号链接。写入时**必须**解析符号链接目标并原子写入到解析后的路径；工具绝不能写入符号链接路径本身（否则会将符号链接替换为普通文件）。

在 POSIX 上，符号链接的创建/替换通过 `os.symlink` + 对临时符号链接执行 `os.replace` 来实现原子性。在 Windows 上，符号链接需要开发者模式或管理员权限；工具将记录警告并回退到使用 Junction。

#### 大小写敏感性

所有路径在 POSIX 上**大小写敏感**。在大小写不敏感的文件系统上（macOS HFS+ 默认模式、Windows NTFS），工具维护一个 `~/.engram/case-map.json` 文件，将规范化小写资产 ID 映射到其磁盘上的实际大小写路径。读取始终经由该映射；写入规范化为标准大小写。

#### 编码与行尾

- 所有文本文件：**UTF-8**；禁止 BOM。
- 行尾：**仅 LF**。工具在读取和写入时将 CRLF 规范化为 LF。
- 每个文本文件均以单个 **`\n`**（文件末尾换行符）结尾。写入时如缺少则自动追加。

---

### 3.2 graph.db 模式

`graph.db` 是位于 **`~/.engram/graph.db`** 的 **SQLite 数据库**。它是跨所有范围进行快速查询的中央索引。它不是权威来源——文件系统（加上日志文件）才是权威来源——可以随时通过 `engram graph rebuild` 删除并重建。

**SQLite 配置**：启用 WAL 模式；`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;`

```sql
-- 核心资产清单
CREATE TABLE assets (
    id          TEXT PRIMARY KEY,       -- 范围限定：如 "local/feedback_push_confirm"
    scope       TEXT NOT NULL,          -- org | team | user | project | pool
    scope_name  TEXT,                   -- 对 org/team/pool：名称；本地/用户时为 NULL
    subtype     TEXT NOT NULL,          -- user | feedback | project | reference | workflow_ptr | agent
    kind        TEXT NOT NULL,          -- memory | workflow | kb
    path        TEXT NOT NULL UNIQUE,   -- 相对于范围根目录的路径
    lifecycle_state TEXT NOT NULL,      -- draft | active | stable | deprecated | archived | tombstoned
    created     TEXT,                   -- ISO-8601
    updated     TEXT,                   -- ISO-8601
    enforcement TEXT,                   -- mandatory | default | hint | NULL（工作流/kb 无此字段）
    confidence_score REAL DEFAULT 0.0,  -- 由 frontmatter 中的置信字段计算
    size_bytes  INTEGER,
    sha256      TEXT                    -- 内容哈希，用于变更检测
);
CREATE INDEX idx_assets_scope     ON assets(scope, scope_name);
CREATE INDEX idx_assets_kind      ON assets(kind);
CREATE INDEX idx_assets_lifecycle ON assets(lifecycle_state);

-- 引用图（资产之间的边）
CREATE TABLE references_ (
    from_id TEXT NOT NULL,
    to_id   TEXT NOT NULL,
    kind    TEXT NOT NULL,   -- references | requires | supersedes | overrides | reply_to
    created TEXT,
    PRIMARY KEY (from_id, to_id, kind),
    FOREIGN KEY (from_id) REFERENCES assets(id)
);

-- 池订阅
CREATE TABLE subscriptions (
    subscriber_scope  TEXT NOT NULL,   -- 项目路径 | user | team:<name> | org:<name>
    pool_name         TEXT NOT NULL,
    subscribed_at     TEXT NOT NULL,   -- org | team | user | project
    propagation_mode  TEXT NOT NULL,   -- auto-sync | notify | pinned
    pinned_revision   TEXT,            -- 仅当 propagation_mode = pinned 时设置
    last_synced_rev   TEXT,
    PRIMARY KEY (subscriber_scope, pool_name)
);

-- 收件箱索引（用于快速查询"仓库 X 的待处理消息"）
CREATE TABLE inbox_messages (
    message_id  TEXT PRIMARY KEY,
    from_repo   TEXT NOT NULL,
    to_repo     TEXT NOT NULL,
    intent      TEXT NOT NULL,   -- bug-report | api-change | question | update-notify | task
    status      TEXT NOT NULL,   -- pending | acknowledged | resolved | rejected
    severity    TEXT,
    created     TEXT NOT NULL,
    path        TEXT NOT NULL,   -- 磁盘上 .md 文件的完整路径
    dedup_key   TEXT
);
CREATE INDEX idx_inbox_to_status ON inbox_messages(to_repo, status);

-- 一致性建议
CREATE TABLE consistency_proposals (
    proposal_id     TEXT PRIMARY KEY,
    class           TEXT NOT NULL,          -- factual-conflict | rule-conflict | reference-rot |
                                            -- workflow-decay | time-expired | silent-override | topic-divergence
    severity        TEXT NOT NULL,          -- critical | high | medium | low
    involved_assets TEXT,                   -- 资产 id 的 JSON 数组
    status          TEXT NOT NULL,          -- open | in_review | resolved | dismissed | expired
    detected_at     TEXT NOT NULL,
    resolved_at     TEXT
);

-- 使用追踪（为置信更新和相关性闸门利用率信号提供数据）
CREATE TABLE usage_events (
    event_id   TEXT PRIMARY KEY,
    asset_id   TEXT NOT NULL,
    event_type TEXT NOT NULL,   -- loaded | validated | contradicted
    task_hash  TEXT,            -- 加载到的 LLM 任务上下文的 SHA-256
    outcome    TEXT,            -- success | failure | ambiguous
    timestamp  TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);
CREATE INDEX idx_usage_asset ON usage_events(asset_id, timestamp);

-- 模式版本追踪
CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

#### 重建规则

`graph.db` 是**从文件系统和日志文件派生的缓存**。若被删除或损坏，`engram graph rebuild` 将通过以下步骤从头重建：

1. 扫描所有范围中的所有资产文件，解析 frontmatter，填充 `assets` 表。
2. 解析 frontmatter 中的 `references:` 字段以填充 `references_` 表。
3. 重放 `~/.engram/journal/propagation.jsonl` 以填充 `subscriptions` 表。
4. 重放 `~/.engram/journal/inter_repo.jsonl` 以填充 `inbox_messages` 表。
5. 重放 `~/.engram/journal/consistency.jsonl` 以填充 `consistency_proposals` 表。
6. 重放 `~/.engram/journal/usage.jsonl`（若已启用）以填充 `usage_events` 表。

重建操作幂等。在已一致的数据库上运行是安全的。

---

### 3.3 缓存目录

```
~/.engram/cache/
├── embedding/
│   ├── version            # 嵌入模型标识符，如 "bge-reranker-v2-m3@2025-11"
│   ├── vectors.db         # sqlite-vss；每个资产一行：(id TEXT, vector BLOB)
│   └── asset_hash.json    # { asset_id: sha256_at_index_time }；哈希不匹配时触发逐资产重建
├── fts5/
│   └── index.db           # SQLite FTS5 全文索引；每个资产一行
├── relevance/
│   ├── manifest.json      # LRU 顺序 + 每条目 TTL 时间戳
│   └── <task_hash>.json   # 该任务上下文哈希对应的排序资产 id 列表
└── compiled_kb/
    └── manifest.json      # { kb_id: { path, sha256, compiled_at } }；读取 KB 时检查陈旧性
```

#### 嵌入缓存

- 每次资产写入时，工具**仅对变更的资产重新嵌入**（通过与 `asset_hash.json` 的 sha256 差异识别）。
- 嵌入模型版本变更时（通过将 `embedding/version` 与配置的模型对比检测），工具对 `vectors.db` 和 `asset_hash.json` 执行**完整重建**。
- `vectors.db` 使用 sqlite-vss 扩展。若该扩展不可用，相关性闸门仅回退到 BM25（FTS5）。

#### FTS5 索引

每次资产写入时**增量更新**。若 `index.db` 不存在或其 `schema_version` 行与当前模式不匹配，工具从头重建。重建时间与资产总数成 O(n) 正比。

#### 相关性缓存

- 默认 TTL：每个 task-hash 条目 **1 小时**。
- 对 `enforcement: mandatory` 资产的任何写入都会**立即使整个相关性缓存失效**。强制级资产总是进入上下文；任何强制级资产的变更都可能改变其他资产是否在预算内。
- manifest 将缓存上限设为 1000 条（LRU 淘汰）。

#### 缓存是可丢弃的

`engram cache rebuild` 从文件系统和 `graph.db` 重建所有四个子目录。无数据丢失；缓存始终可重建。

---

### 3.4 日志目录

```
~/.engram/journal/
├── propagation.jsonl    # 池传播事件（SPEC §9）
├── inter_repo.jsonl     # 跨仓收件箱事件（SPEC §10）
├── consistency.jsonl    # 一致性建议生命周期事件（SPEC §11）
├── migration.jsonl      # v0.1→v0.2（及未来版本）迁移事件（SPEC §13）
└── usage.jsonl          # （可选；默认关闭）详细的每次加载 LLM 使用事件
```

所有文件均为**追加专用**。工具永不编辑现有行。每行是一个独立的 JSON 对象，至少包含 `{ "event_type": "...", "sender_id": "...", "seq": N, "timestamp": "ISO-8601", ... }`。`sender_id` + `seq` 对提供单调排序，能容忍并发追加者（在实践中极少见；详见 §3.8）。

#### 压缩

当日志文件超过 `journal.max_size_mb`（默认：100 MB）时：

1. 将当前文件复制到 `~/.engram/archive/journal/<name>.<ISO时间戳>.jsonl`。
2. 写入新的活跃文件，仅包含比 `journal.hot_window_days`（默认：30 天）新的事件，并在首行前置压缩记录：`{ "event_type": "compaction", "archived_to": "<path>", "timestamp": "..." }`。
3. 步骤 1 完成后，已归档副本永不再修改。

#### 每工作流日志

`<scope-root>/workflows/<name>/journal/` 下的每个工作流维护：

- `evolution.tsv` — 每次自学习轮次一行 TSV 记录（SPEC §5 定义列）
- `runs.jsonl` — 每次工作流调用一个 JSON 对象

这些文件使用与全局日志相同的追加专用 + 压缩模式，`journal.hot_window_days` 独立适用。

---

### 3.5 归档目录

```
~/.engram/archive/
├── assets/
│   ├── memory/
│   │   └── <asset-id>/
│   │       ├── content.md       # 已归档的资产文件
│   │       └── metadata.json    # { archived_at, archived_by, original_path, tombstone_date }
│   ├── workflows/
│   │   └── <workflow-name>/     # 相同结构：content.md + metadata.json
│   └── kb/
│       └── <topic>/             # 相同结构
├── journal/                     # 压缩后的日志文件（来自 §3.4 压缩）
└── rev/                         # 已归档的工作流修订版本快照
```

#### 保留策略

| 事件 | 操作 |
|---|---|
| `engram memory archive <id>` | 资产移入此处；`tombstone_date` = `archived_at` + 6 个月 |
| `tombstone_date` 之前 | `engram archive restore <id>` 将其移回活跃位置 |
| `tombstone_date` 之后 | 可进行物理删除；**不自动删除** |
| `engram archive gc --past-retention` | 运营者命令；仅删除已过 `tombstone_date` 的资产 |

`engram archive list` 显示所有归档项、其 `archived_at` 时间，以及距 `tombstone_date` 的剩余天数。没有任何例行工具操作会在未经运营者显式调用 `gc` 的情况下从 `~/.engram/archive/` 删除文件。

---

### 3.6 工作区目录

```
~/.engram/workspace/
├── autolearn-<run-id>/
│   ├── input/        # 运行开始时工作流的快照
│   ├── output/       # 运行建议的脊柱修改和固件输出
│   └── run.log       # 运行的结构化日志
├── consistency-<run-id>/
│   ├── input/        # 涉及资产的快照
│   ├── proposals/    # 候选建议 JSON 文件
│   └── run.log
└── evolve-<run-id>/
    ├── input/
    ├── output/
    └── run.log
```

每个工作区都是**隔离沙箱**。工作区内的操作不能直接接触活跃存储。成功时，工作区的 `output/` 通过原子提交（对每个文件执行先写临时文件再重命名）应用到存储。失败时，工作区保留以供运营者检查失败原因；`engram workspace clean [<run-id>]` 丢弃它。

运行 ID 格式为 `<类型>-<ISO时间戳>-<6字符随机>`，例如 `autolearn-20260418T103045Z-a3f9b2`。工作区目录在运行开始前创建，其存在充当运行中锁（同类型的第二次调用若发现非过期工作区则拒绝启动，防止对同一工作流的并行 mutation）。

---

### 3.7 备份与恢复

`engram snapshot` 创建完整 `~/.engram/` 目录树的 tarball 备份。

```bash
engram snapshot create                       # ~/.engram-backup/snapshot-YYYY-MM-DD.tar.gz
engram snapshot create --dir=/path/to/dir    # 自定义输出目录
engram snapshot create --include-projects    # 同时包含已知项目中的 .memory/ 目录
engram snapshot list                         # 列出快照及大小、日期和 sha256 状态
engram snapshot restore <snapshot-name>      # 恢复到 ~/.engram/；覆盖前提示确认
engram snapshot diff <snapshot-a> <snapshot-b>  # 对比两个快照（资产级差异）
```

#### 完整性

每个快照 tarball 附带一个 `<name>.sha256` 文件。`snapshot restore` 在解压前验证 sha256。若验证失败，恢复中止并报错。

#### 内容

| 默认包含 | 可选 |
|---|---|
| `~/.engram/graph.db` | 每个已知项目中的 `.memory/` 目录（`--include-projects`） |
| `~/.engram/journal/` | |
| `~/.engram/archive/` | |
| `~/.engram/cache/` | |
| `~/.engram/user/`、`~/.engram/team/`、`~/.engram/org/`、`~/.engram/pools/` | |

缓存目录默认包含在快照中，使恢复后无需重建即可立即运行。`--no-cache` 标志可省略它们以减小快照体积。

---

### 3.8 并发保护

engram-cli 是本地优先工具。来自多个终端或后台进程的并发调用是可能的；以下机制确保正确性。

| 机制 | 应用位置 | 保证 |
|---|---|---|
| **SQLite WAL 模式** | `graph.db`、`cache/fts5/index.db`、`cache/embedding/vectors.db` | 多个并发读取者；单一写入者；读取者永不阻塞写入者 |
| **`fcntl.flock` 独占锁** | `~/.engram/.lock` | 迁移、缓存重建、图重建和快照恢复期间持有独占锁——这些操作不能交叉执行 |
| **原子文件写入** | 所有资产文件、配置文件、索引文件 | 先写临时文件 + `os.replace`；规范路径上不存在不完整文件（见 §3.1） |
| **原子符号链接替换** | 池和修订版本符号链接 | `os.symlink(target, tmp_link)` + `os.replace(tmp_link, link_path)` — 在 POSIX 上原子 |
| **乐观资产并发** | 任何资产写入之前 | 工具检查当前磁盘 sha256 是否与上次读取时缓存的 sha256 一致；不匹配 → 重新加载 + 重试（最多 3 次，然后报错） |
| **追加专用日志** | 所有 `*.jsonl` 文件 | 每行是独立记录；并发追加者不能破坏现有行；`sender_id` + `seq` 提供事后排序 |

#### Windows 说明

`fcntl.flock` 在 Windows 上不可用。工具使用 `msvcrt.locking` 作为 `.lock` 文件的回退方案。SQLite WAL 模式在标准 SQLite 发行版的 Windows 上正常工作。

---

### 3.9 跨机器同步策略

engram 是本地优先的。参考实现在 v0.2 中不提供内置同步协议。在多台机器上工作的用户有以下四种支持的策略：

#### 方案 1 — git（适用于 team、org、pool 范围）

`~/.engram/team/<name>/`、`~/.engram/org/<name>/` 和 `~/.engram/pools/<name>/` 设计为 git 仓库。参考实现在创建时将其初始化为 git 仓库。同步通过标准 git 操作或以下命令包装进行：

```bash
engram team sync <name>    # 对指定 team 范围执行 git pull + push
engram pool sync <name>    # 对指定池执行 git pull + push
```

合并冲突通过标准 git 工具解决。日志文件是追加专用的，因此来自不同机器的并发追加产生的合并会保留两组事件。

#### 方案 2 — rsync（适用于 user 范围）

`~/.engram/user/` 默认不是 git 仓库。对于多机器用户内容：

```bash
# 从受信任的主机单向拉取：
rsync -avz --delete user@primary:~/.engram/user/ ~/.engram/user/
```

对于双向同步，推荐使用 Unison 等能显式处理冲突的工具，而非裸 rsync。

#### 方案 3 — 云存储符号链接

`~/.engram/user/` 可以是指向云同步目录的符号链接（例如 `~/Dropbox/engram-user/`）。工具能正确追踪符号链接。**注意：** 来自两台机器的同时写入可能破坏 `graph.db`，因为云存储缺乏原子重命名支持。仅在机器使用时间不重叠的情况下使用此方案，或将 `graph.db` 排除在云同步之外并在本地重建。

#### 方案 4 — 自定义同步 hook

```bash
engram config set sync.post_write_hook="your-sync-command"
```

该 hook 在每次写入后运行。用户负责确保命令安全且幂等。工具不验证或包装 hook 的行为。

#### v0.2 范围之外

engram v0.2 不提供自有同步协议。v0.2 之后的路线图计划是基于 CRDT 复制模型的 `engram sync`，无需中央服务器即可处理跨机器对同一资产的并发编辑。

---

## 4. 第 2 层控制——CLI 命令族

### 4.0 命令族原则

`engram` CLI 是存储的控制平面。命令族遵循五条原则：

1. **名词-动词结构。** 命令遵循 `engram <名词> <动词>` 格式（例如 `engram memory add`、`engram pool sync`）。顶层动词——`init`、`status`、`version`、`review`、`validate`、`migrate`、`export`、`snapshot`——作用于整个存储，不需要名词前缀。其他所有子命令都归属于且仅归属于一个名词组：`memory`、`workflow`、`kb`、`pool`、`team`、`org`、`inbox`、`consistency`、`context`、`mcp`、`web`、`playbook`、`graph`、`cache`、`archive`、`workspace`、`config`。

2. **默认幂等。** 执行相同命令两次产生相同结果。本质上非幂等的命令——`workflow run`（有副作用）、`pool publish`（创建新修订版本）、`inbox send`（创建新消息）——在描述和 `--help` 输出中明确说明。

3. **可管道输出。** 每个命令支持 `--json` 标志，生成机器可读输出。默认输出为人类可读、对齐列格式，适配 80 列以上的终端。脚本和 CI 流水线始终使用 `--json`。与 `--quiet` 组合时，仅向 stdout 输出结构化 JSON；警告输出到 stderr。

4. **无 LLM 依赖。** 每个 CLI 命令在没有 LLM、没有 API key、没有网络访问的情况下必须正确运行。可选调用智能层功能的命令（例如 `consistency scan --phase=llm`、`workflow autolearn`）在 LLM 不可用时优雅降级到离线等效模式。没有任何命令仅因模型不可达而以退出码 2 退出。

5. **可预期的退出码。** 四个码，仅此而已：`0` = 干净完成；`1` = 存在警告，运营者应检查；`2` = 操作失败；`3` = 操作因前置条件未满足而被阻止。完整契约见 §4.3。

---

### 4.1 完整命令清单

命令按名词分组。每条目给出命令签名和用途。完整的 `--help` 文本位于 CLI 源码；本节是"哪条命令做 X？"的查阅参考。

#### 顶层操作

| 命令 | 用途 |
|---|---|
| `engram init [--scope=...] [--subscribe=...] [--adapter=...] [--org=...] [--team=...]` | 在当前目录初始化 `.memory/` |
| `engram status` | 显示项目 engram 状态：资产计数、范围成员关系、池订阅、待处理收件箱、未解决一致性建议 |
| `engram version` | 工具版本和规范版本 |
| `engram config <get\|set\|list> <key> [value]` | 读写 `~/.engram/config.toml` |
| `engram review` | 聚合健康检查：一致性建议 + 池通知 + 待处理收件箱 + 过期 KB 摘要 |
| `engram validate [--category=...] [--json]` | 运行 SPEC §12 的所有验证规则 |
| `engram migrate --from=<source> [--dry-run] [--target=...]` | 从 v0.1、claude-code、chatgpt、mem0、obsidian、letta、mempalace 或 markdown 迁移 |
| `engram snapshot <create\|list\|restore\|diff>` | 备份与恢复（按 §3.7） |
| `engram export --format=<markdown\|prompt\|json> [--output=...]` | 导出存储内容 |

#### 记忆操作

| 命令 | 用途 |
|---|---|
| `engram memory add --type=<subtype> --scope=<scope> [--enforcement=...]` | 创建新记忆资产；省略标志时交互式提示 |
| `engram memory list [--type=...] [--scope=...] [--limit=...]` | 列出符合过滤条件的记忆 |
| `engram memory read <id>` | 打印资产完整内容（LLM 脊柱访问，按 SPEC §3.3 MUST 2） |
| `engram memory update <id> [flags]` | 编辑 frontmatter、正文或移动范围 |
| `engram memory archive <id> [--reason=...]` | 移入归档（保留策略适用） |
| `engram memory search <query> [--limit=...] [--scope=...]` | 全文和语义搜索 |
| `engram memory validate-use <id> --outcome=<success\|failure>` | 记录结果以更新置信度（§11 一致性契约） |

#### 工作流操作

| 命令 | 用途 |
|---|---|
| `engram workflow add <name> --scope=<scope> [--spine-lang=...]` | 脚手架新工作流目录 |
| `engram workflow run <name> --inputs='<json>'` | 调用脊柱（非幂等） |
| `engram workflow revise <name>` | 启动手动修订，创建 `rev/rN/` |
| `engram workflow promote <name> --to=<rev>` | 将 `current` 符号链接移至指定修订版本 |
| `engram workflow rollback <name> [--to=<rev>]` | 回滚至先前修订版本 |
| `engram workflow autolearn <name> [--rounds=...] [--budget=...]` | 启动自学习循环（智能层） |
| `engram workflow list` | 列出所有范围内的所有工作流 |
| `engram workflow test <name>` | 对当前修订版本运行固件 |

#### 知识库操作

| 命令 | 用途 |
|---|---|
| `engram kb new-article <topic> --scope=<scope>` | 脚手架新 KB 文章目录 |
| `engram kb compile [<topic>] [--check]` | 重新生成 `_compiled.md`；`--check` 在不重新生成的情况下验证陈旧性 |
| `engram kb list` | 列出所有 KB 文章 |
| `engram kb read <topic>[/<chapter>]` | 打印文章或指定章节 |

#### 池操作

| 命令 | 用途 |
|---|---|
| `engram pool create <name> [--scope=<initial-scope>]` | 在 `~/.engram/pools/<name>/` 创建新池 |
| `engram pool list` | 列出所有本地池和订阅状态 |
| `engram pool subscribe <source> [--at=<hierarchy-level>] [--mode=<auto-sync\|notify\|pinned>]` | 订阅池（项目或指定层次级别） |
| `engram pool unsubscribe <name>` | 取消订阅 |
| `engram pool publish <name> [--message=...]` | 创建新修订版本、git 提交并推送（非幂等） |
| `engram pool propagate <name>` | 手动触发：通知订阅者最新修订版本 |
| `engram pool sync [<name>]` | 从池的 git 远端拉取更新 |
| `engram pool diff <name> --from=<rev> --to=<rev>` | 显示两个修订版本之间的差异 |
| `engram pool update <name> --to=<rev>` | 将钉版订阅移至新修订版本 |

#### Team 与 Org 操作

| 命令 | 用途 |
|---|---|
| `engram team join <git-url>` | 将 team 仓库克隆到 `~/.engram/team/<name>/` |
| `engram team sync [<name>]` | 从 team 远端拉取更新 |
| `engram team publish [<name>] [--message=...]` | 提交并推送 team 记忆（非幂等） |
| `engram team status` | 显示 team 成员关系和待同步状态 |
| `engram org join <git-url>` | org 的同等操作（单 org 约束适用） |
| `engram org sync` | 从 org 远端拉取更新 |
| `engram org publish` | 提交并推送 org 记忆（非幂等） |
| `engram org status` | 显示 org 成员关系和待同步状态 |

#### 收件箱操作

| 命令 | 用途 |
|---|---|
| `engram inbox list [--status=<pending\|acknowledged\|resolved\|rejected>] [--to=<repo-id>]` | 列出消息 |
| `engram inbox send --to=<repo-id> --intent=<type> --severity=<level> --message='...' [--code-ref=...] [--deadline=...]` | 发送消息（非幂等） |
| `engram inbox read <message-id>` | 读取完整消息 |
| `engram inbox acknowledge <message-id>` | 将消息状态从 pending 转为 acknowledged |
| `engram inbox resolve <message-id> --note='...' [--commit=<sha>]` | 转为 resolved |
| `engram inbox reject <message-id> --reason='...'` | 转为 rejected |
| `engram inbox list-repos` | 显示已知 repo-id |

#### 一致性操作

| 命令 | 用途 |
|---|---|
| `engram consistency scan [--classes=...]` | 运行检测扫描；创建建议 |
| `engram consistency report [--since=...] [--status=...]` | 显示未解决或近期的建议 |
| `engram consistency resolve <proposal-id> --action=<update\|supersede\|merge\|archive\|dismiss\|escalate> [flags]` | 应用一个解决方案 |

#### 上下文操作（供 LLM 集成使用）

| 命令 | 用途 |
|---|---|
| `engram context pack --task='...' --budget=<tokens> [--model=...]` | 生成紧凑的 LLM 系统提示 |
| `engram context preview --task='...' --budget=<tokens>` | 显示将要打包的内容及诊断信息 |

#### 服务操作

| 命令 | 用途 |
|---|---|
| `engram mcp serve [--transport=stdio\|sse] [--port=...]` | 启动 MCP 服务 |
| `engram web serve [--port=8787] [--auth=<user:pass>]` | 启动 Web UI 后端 |
| `engram web open` | 在浏览器中打开本地 Web UI |

#### Playbook 操作

| 命令 | 用途 |
|---|---|
| `engram playbook install github:<owner>/<repo>[@<ref>]` | 从 GitHub 安装 playbook |
| `engram playbook publish [--remote=...]` | 发布当前 playbook |
| `engram playbook list` | 显示已安装的 playbook 和源 URL |
| `engram playbook uninstall <name>` | 删除符号链接（文件保留在 `~/.engram/playbooks/` 中） |

#### 维护操作

| 命令 | 用途 |
|---|---|
| `engram graph rebuild` | 从文件系统重建 `~/.engram/graph.db`（按 §3.2） |
| `engram cache rebuild [--embedding\|--fts5\|--relevance]` | 重建缓存（可选择性或全部） |
| `engram archive list` | 显示归档项及保留日期 |
| `engram archive restore <id>` | 将归档资产恢复到活跃位置 |
| `engram archive gc --past-retention` | 物理删除超过 6 个月保留下限的资产（需要确认） |
| `engram workspace list` | 显示活跃和近期的工作区 |
| `engram workspace clean [<id>]` | 删除一个工作区或所有非活跃工作区 |

---

### 4.2 全局标志

以下标志被所有命令接受。命令特定的标志见各命令的 `--help`。

| 标志 | 效果 |
|---|---|
| `--json` | 机器可读输出；结构化 JSON 输出到 stdout |
| `--verbose` | 调试级日志输出到 stderr |
| `--dry-run` | 对于修改状态的命令：显示将发生的内容，不实际执行 |
| `--engram-dir=<path>` | 覆盖 `~/.engram/`；适用于测试或多用户环境 |
| `--config=<path>` | 使用备用配置文件替代 `~/.engram/config.toml` |
| `--scope=<scope>` | 覆盖推断的范围；极少需要；主要用于脚本 |
| `--quiet` | 抑制所有输出，仅保留错误和 JSON（与 `--json` 同用时） |
| `--help` / `-h` | 打印命令帮助并退出 |
| `--version` | 打印工具版本和规范版本 |

**配置解析顺序：** 命令行标志 > 环境变量（如 `ENGRAM_DIR`）> `~/.engram/config.toml` > 内置默认值。

---

### 4.3 退出码契约

| 码 | 含义 |
|---|---|
| `0` | 操作干净完成 |
| `1` | 操作完成但存在警告；运营者应检查 |
| `2` | 操作因错误失败（SPEC 违规、I/O 故障、强制性冲突） |
| `3` | 操作被阻止：前置条件不满足；操作未执行 |
| `130` | 被用户中断（SIGINT） |

具体示例：

- `engram validate` 发现 5 个警告、0 个错误 → 退出 `1`
- `engram validate` 发现 2 个错误 → 退出 `2`
- 在已是 v0.2 存储上执行 `engram migrate --from=v0.1` → 退出 `0`（幂等）
- `engram pool subscribe` 提供不可达的远端 URL → 退出 `3`
- `engram memory archive <id>` 其中 `<id>` 不存在 → 退出 `2`
- `engram review` 存在待处理收件箱项但无错误 → 退出 `1`
- `engram status` 存储健康时 → 退出 `0`

`validate`、`review` 或 `consistency scan` 返回退出码 `1` 不代表存储已损坏——它表示运营者有内容需要查看。将退出码 `1` 视为构建失败的 CI 流水线应使用 `--json` 并解析输出以区分警告类别。

---

### 4.4 `~/.engram/config.toml` 模式

```toml
[general]
spec_version = "0.2"
user_scope_name = "alice"           # 映射到 ~/.engram/user/

[embedding]
model = "bge-reranker-v2-m3"        # 本地模型，默认值
provider = "local"                  # local | openai | cohere | anthropic
api_key_env = "ENGRAM_EMBED_KEY"    # 持有 API key 的环境变量（当 provider != local 时）
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
llm_review_enabled = false                      # 第 3 阶段扫描使用 LLM；默认关闭
llm_review_budget_tokens_per_scan = 50000

[autolearn]
default_budget_seconds = 300                    # 每轮
default_rounds = 10
phase_gate_rounds = 5                           # 每 5 轮暂停，等待人工审查
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
# port = 3000                                   # 用于 sse 传输

[git]
auto_commit = false                             # 变更时自动提交；默认关闭
# signing_key = "..."
```

**配置解析顺序：** 命令行 > 环境变量 > `~/.engram/config.toml` > 内置默认值。

所有键均为可选；文件不存在时工具以内置默认值启动。`engram config set <key> <value>` 写入此文件。`engram config get <key>` 读取应用完整解析顺序后的值。

---

### 4.5 命令详情——关键子集

#### `engram init`

```
engram init [--scope=project] [--org=<name>] [--team=<name>]
            [--subscribe=<pool-source>] [--adapter=<tool>]
```

在当前目录创建 `.memory/`，包含完整的初始脚手架：`local/`、`pools/`、`workflows/`、`kb/`、`pools.toml`、`MEMORY.md` 和 `.engram/version`。省略标志时，交互式提示涵盖 org/team 成员关系、池订阅和适配器选择。`--adapter` 写入相应的适配器文件（例如 `adapters/claude-code.md`）。在已有 `.memory/` 的目录上运行 `init`，若存储已处于当前规范版本则为空操作；若发现 v0.1 存储则优雅升级。

#### `engram review`

```
engram review [--json]
```

以五个分类显示所有需要关注的内容的单一命令：

1. **一致性建议** — 按严重程度列出的未解决建议
2. **池通知** — 有待处理订阅者通知的池
3. **待处理收件箱** — 等待确认的消息
4. **过期 KB 文章** — `_compiled.md` 比其源章节更旧
5. **过期工作流** — 指标衰减或超过审查日期的工作流

任何分类非空时返回退出码 `1`；全部为空时返回退出码 `0`。设计为每日检查或 CI 门控。使用 `--json` 时，输出按分类结构化，便于下游解析。

#### `engram validate`

```
engram validate [--category=<class>] [--json]
```

按顺序运行 SPEC §12 的每条验证规则。类别与 SPEC §12 规则类匹配（例如 `memory-schema`、`workflow-rev`、`pool-config`、`inbox-format`）。输出格式由 SPEC §12.13 规定。CI 友好：退出 `0` = 无问题；退出 `1` = 仅警告；退出 `2` = 一个或多个错误。使用 `--json` 时，每个问题是包含 `rule`、`severity`、`asset_id`、`message` 和 `suggestion` 的结构化对象。

#### `engram migrate --from=<source>`

```
engram migrate --from=<source> [--dry-run] [--target=<path>]
```

来源：`v0.1`、`claude-code`、`chatgpt`、`mem0`、`obsidian`、`letta`、`mempalace`、`markdown`。迁移遵循 SPEC §13.4。`--dry-run` 将完整的迁移报告作为 JSON 输出到 stdout，不写入任何文件。在已迁移的存储上，命令为空操作，退出 `0`。每次迁移向 `~/.engram/journal/migration.jsonl` 追加一条事件，用于审计。

#### `engram context pack`

```
engram context pack --task='<description>' --budget=<tokens> [--model=<id>]
```

调用相关性闸门（第 3 层）在 token 预算内选择和排名资产，然后将其格式化为紧凑的系统提示。默认完全离线运行——相关性闸门使用 BM25 + 嵌入缓存；除非 `--model` 为托管提供商，否则不进行网络调用。若指定模型的分词器可用，则按其计算 token 数；否则使用基于字符的估算。输出写入 stdout，可直接管道传入 LLM 调用。

#### `engram consistency scan`

```
engram consistency scan [--classes=<comma-list>] [--phase=<1|2|3|4>]
```

运行 SPEC §11 的分阶段一致性扫描。各阶段：1 = 结构验证（始终离线），2 = 语义聚类（需要嵌入缓存），3 = LLM 审查（需要 `consistency.llm_review_enabled = true`），4 = 固件执行（需要带固件的工作流）。每个阶段均可用 `--phase` 跳过。建议写入 `graph.db` 并追加到 `journal/consistency.jsonl`。创建新建议时返回退出码 `1`；扫描未发现任何问题时返回退出码 `0`。

#### `engram pool subscribe`

```
engram pool subscribe <source> [--at=<org|team|user|project>]
                                [--mode=<auto-sync|notify|pinned>]
                                [--pin-rev=<revision>]
```

将当前项目（或 `--at` 指定的范围）订阅到一个池。`<source>` 为 git URL、`~/.engram/pools/<name>` 路径或 playbook 引用。`--at` 标志设置 `subscribed_at` 级别，控制冲突解决中的权威性。首次订阅时，池被克隆到 `~/.engram/pools/<name>/`；后续订阅复用现有克隆。源 URL 不可达时退出 `3`。

---

### 4.6 演进路线（P0–P3）

命令按与里程碑计划对齐的阶段发布。后续阶段依赖前序阶段的基础设施；P0 为最重要的日常工作流交付完整、可用的 CLI。

**P0 — v0.2 首次发布（M4 里程碑）：**

- `init`、`status`、`version`、`config`、`review`、`validate`、`migrate --from=v0.1`
- `memory add/list/read/update/archive/search`
- `pool create/list/subscribe/unsubscribe/publish/sync`
- `team join/sync/publish/status`、`org join/sync/publish/status`
- `inbox list/send/read/acknowledge/resolve/reject`
- `context pack/preview`
- `graph rebuild`、`cache rebuild`
- `archive list/restore`
- `snapshot create/list/restore`
- `export`

**P1 — M5–M6：**

- `workflow add/run/revise/promote/rollback/autolearn/list/test`
- `kb new-article/compile/list/read`
- `consistency scan/report/resolve`
- `migrate --from={claude-code,chatgpt,mem0,obsidian,letta,mempalace,markdown}`
- `inbox list-repos`
- `web serve/open`

**P2 — M7：**

- `mcp serve`
- `pool propagate/diff/update`
- `archive gc`、`workspace list/clean`
- `snapshot diff`

**P3 — M8 后：**

- `playbook install/publish/list/uninstall`
- 增强的 `consistency` 功能（跨范围建议）
- `engram sync`（跨机器，基于 CRDT；见 §3.9）

---

## 5. 第 3 层 — 智能层

### 5.0 概述

智能层是一组六个可选组件，在原始数据存储之上提供推理与自我改进能力。每个组件均可独立禁用；当所有组件关闭时，系统仍可正确运行（仅无智能功能）。任何组件均不是 SPEC 合规性的必要条件。

#### 5.0.1 组件关系图

```
                    ┌─────────────────────────────────┐
                    │     第 4 层 接入层（提示）        │
                    └───────────────┬─────────────────┘
                                    │ 请求上下文
                                    ▼
┌──────────────────────┐    ┌───────────────────┐    ┌──────────────────────┐
│ 一致性引擎           │◄──►│ 相关性闸门        │◄──►│  智慧指标            │
│ (检测 7 类冲突;      │    │ (排序 + 打包      │    │ (4 条曲线; 分析统计) │
│  生成 proposal)      │    │  进上下文预算)    │    │                      │
└────┬─────────────────┘    └───────────────────┘    └──────────┬───────────┘
     │ proposals                   ▲                             │ 指标
     ▼                             │                             ▼
┌──────────────────────┐    ┌──────┴────────────┐    ┌──────────────────────┐
│  跨仓传信器          │    │ 自学习引擎        │    │  演化引擎            │
│  (inbox 投递)        │    │ (工作流演化)      │    │  (记忆演化)          │
│                      │    │                   │    │  ReMem 循环          │
└──────┬───────────────┘    └───────────────────┘    └──────────────────────┘
       │ 消息
       ▼
   第 1 层（数据层）
```

#### 5.0.2 六个组件

| 组件 | 用途 | 写入内容 |
|---|---|---|
| **相关性闸门** | 对候选资产排序 + 打包进上下文预算 | 无（只读查询层） |
| **一致性引擎** | 检测 7 类冲突；生成修复建议 | `consistency.jsonl` proposals |
| **自学习引擎** | 工作流自学习（Darwin 式棘轮 + 双维度评分） | 新工作流 `rev/rN/`；`evolution.tsv` |
| **演化引擎** | 记忆演化（ReMem action-think-refine） | Proposal 记录（不直接 mutate） |
| **跨仓传信器** | 监听并路由 inbox 消息 | `inter_repo.jsonl` 事件 |
| **智慧指标** | 追踪 4 条自我改进曲线 | graph.db 中的时序表 |

#### 5.0.3 共享设计原则

1. **建议，不 mutate** — 相关性闸门和跨仓传信器修改的是**临时上下文**，而非资产本身。一致性引擎、自学习引擎和演化引擎只生成 proposal；人类或 LLM 显式接受后才执行。

2. **日志记录一切** — 每次智能层操作都写入 journal（`~/.engram/journal/` 下的 `*.jsonl` 文件），支持完整审计和回放。

3. **可独立禁用** — 每个组件在 `config.toml` 中均有 `[<组件>].enabled = false` 开关；所有组件关闭时系统仍然正确。

4. **工作区隔离** — 运行耗时操作的组件（自学习引擎、演化引擎、一致性引擎第 3 阶段）在 `~/.engram/workspace/<组件>-<run-id>/` 沙箱中执行，中途不会触碰 live store。

5. **核心路径不依赖 LLM** — 相关性闸门必须仅依赖本地嵌入即可工作。可选 LLM 重排序默认关闭，保持唤醒路径可在离线/气隙环境下运行。

---

### 5.1 相关性闸门

**用途：** 给定任务上下文和 token 预算，选择哪些资产进入 LLM 的 system prompt。每次 `engram context pack` 调用和每次 MCP `engram_context_pack` 工具调用时触发。

**输入：**

```python
{
  "task": str,                      # LLM 需要完成的任务的自由描述
  "budget_tokens": int,             # 上下文预算（唤醒默认 900）
  "model_profile": str | None,      # 可选：关于模型上下文长度的提示
  "project_root": str,              # engram 项目路径
}
```

**输出：**

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
  "packed_prompt": str,             # 最终 system prompt（在预算内）
  "tokens_used": int,
  "tokens_remaining": int,
  "excluded_due_to_budget": [str],  # 因预算不足而丢弃的 asset id 列表
}
```

#### 5.1.1 流水线（7 个阶段）

流水线是线性的；每个阶段将输出传给下一阶段。

```
task                                          packed_prompt
  │                                              ▲
  ▼                                              │
(1) 强制包含（绕过排序）────────────────────────► [上下文]
  │
  ▼
(2) 候选检索
    a. 语义搜索（向量 / cache/embedding/）→ top-50
    b. BM25 全文（cache/fts5/）           → top-50
    c. 结构检索（订阅 + scope）            → 全部可见
  │
  ▼
(3) 混合评分融合
    fused_dist = dist * (1.0 - 0.30 * keyword_overlap)
  │
  ▼
(4) 时间邻近加权（若任务含"N 周前"等表达）
    fused_dist *= (1.0 - min(0.40 * proximity_factor, 0.40))
  │
  ▼
(5) 两段检索（若任务为 assistant-reference）
    第一段：仅在 user 回合索引查；第二段：在 top 候选上加 assistant 内容再查
  │
  ▼
(6) scope / enforcement 加权
    score *= scope_weight（project=1.5, user=1.2, team=1.0, org=0.8）
    时效衰减：score *= exp(-days_since_updated / 30)
  │
  ▼
(7) 预算感知截断
    按 score-per-token 贪心选取；按 scope 顺序组装 packed_prompt
  │
  ▼
packed_prompt
```

#### 5.1.2 阶段详情

**阶段 1：强制包含（绕过排序）**

所有 `enforcement: mandatory` 的资产在任何评分之前无条件包含。强制资产最先插入 `packed_prompt`，消耗其 token 配额后再考虑排名候选项。

若仅强制资产已超出可用预算，相关性闸门发出硬错误：
```
budget insufficient for mandatory rules (N tokens required, M tokens available)
```

强制资产内部的包含顺序是确定性的：按 scope 特异性（project 最先，然后 user、team、org——由最具体到最通用），同 scope 内以 asset-id 字母顺序作为决胜规则。这确保相同调用产生可复现的输出。

**阶段 2：候选检索（三路来源，并发扇出）**

三路检索来源并行运行，结果合并：

- **语义检索：** 用配置的嵌入器对任务字符串编码；从 `cache/embedding/vectors.db` 中取最近的 K=50 个资产（按余弦距离）。若嵌入缓存不存在或嵌入器不可达，则跳过本来源（离线模式）。
- **BM25：** 对任务 query 分词，剥离词表 §17 中 32 个停用词，提取 ≥3 字符的关键词；对每个候选资产的正文用 Okapi-BM25 打分（使用 `cache/fts5/index.db`）。保留 top-50。
- **结构检索：** 所有已订阅 pool 中的资产 + 所有 `tags:` frontmatter 与任务关键词有至少一个匹配的资产。该集合无数量上限，但实际上通常很小。

三路结果取并集，按 `asset_id` 去重。

**阶段 3：混合评分融合（MemPalace Hybrid v2）**

混合融合公式直接采用 MemPalace Hybrid v2 模式（在 LongMemEval 上达到 98.4% R@5）：

```
dist    = 嵌入余弦距离        # 越低越相似
overlap = len(set(task_keywords) & set(asset_keywords)) / max(1, len(task_keywords))
fused_dist = dist * (1.0 - 0.30 * overlap)
```

`fused_dist` 越低表示匹配越好。0.30 权重由 MemPalace 已发表的基准确定；修改前需重新运行 LongMemEval 评测（见 §5.1.8）。

当语义评分不可用时（离线模式），所有候选的 `dist` 统一设为 `0.5`，退化为纯 BM25 评分。质量下降但系统不报错。

**阶段 4：时间邻近加权**

检测任务字符串中的时间锚点："N 周前"、"上个月"、"昨天"、"2026 年 Q1"、"上周二"等。若检测到时间锚点：

1. 计算 `target_date = query_date - time_offset`（如"3 周前"→减去 21 天）。
2. 对每个候选计算其 `updated` 日期与 `target_date` 的天数差。
3. 若在窗口内则施加加权：

```python
window = days_offset * 1.5    # 如"4 周前"→ ±42 天窗口
days_diff = abs((asset.updated_date - target_date).days)
if days_diff < window:
    boost = max(0.0, 0.40 * (1.0 - days_diff / window))
    fused_dist *= (1.0 - boost)   # 最多减少 40% 距离
```

最大加权上限为距离减少 40%（`temporal_max_boost = 0.40`）。若未检测到时间锚点，阶段 4 为空操作。

**阶段 5：两段检索（针对 assistant-reference 查询）**

检测任务是否引用了助手之前所说或建议的内容："你说过 X"、"根据你的建议"、"你之前提到"等短语。

若检测到：
- **第一段：** 用任务关键词对仅包含 user 回合的索引检索 top-5 会话（assistant 回合不在此索引中，避免污染全局嵌入空间）。
- **第二段：** 对这 5 个会话的完整文本（含 assistant 回合）用原始任务字符串重新检索。

在被明确请求时仍能找到 assistant 引用的内容，同时不污染全局索引。

若任务不是 assistant-reference 查询，阶段 5 为空操作，所有候选直接通过。

**阶段 6：scope 与 enforcement 加权**

对每个候选应用基于 scope 的乘数，将 `fused_dist` 转换为 `score`（越高越好）：

```python
# 距离转分数：dist 越低 → score 越高
base_score = 1.0 - fused_dist

weights = {
    "project": 1.5,   # 最具体 → 权重最高
    "user":    1.2,
    "team":    1.0,
    "org":     0.8,   # 最通用（但阶段 1 的 mandatory 绕过是独立的）
    "pool":    # 继承 subscribed_at 层级的权重
}
score = base_score * weights[asset.scope]
```

时效衰减作为最后调整：

```python
days = (now - asset.updated).days
score *= exp(-days / 30.0)   # 30 天半衰期；可通过 weights_recency_halflife_days 调整
```

默认半衰期为 30 天。30 天前更新的资产保留约 50% 的加权分；90 天前更新的资产保留约 5%。

**阶段 7：预算感知截断**

1. 按 `score / tokens_est` 降序排列所有已评分候选（每 token 价值）。
2. 贪心选取，直到剩余 token 预算耗尽。
3. 按 scope 顺序组装 `packed_prompt`：强制资产最先，然后 project → user → team → org → pool。同一 scope 内按 score 降序排列。
4. 已评分但未放入的资产加入 `excluded_due_to_budget`。

按 score-per-token 而非原始 score 排序，确保短而高相关的资产优先于长而略相关的资产，最大化有限预算的利用率。

#### 5.1.3 Token 估算

每个资产在写入时计算 token 数，缓存至 `graph.db`（`size_bytes` 字段）。估算公式：

```
tokens_est = len(body_bytes) * 0.25
```

这是英文散文的保守比例（平均每 token 4 字节）。代码密集型资产比例略低；含 emoji 或 CJK 字符的资产比例略高。查询时不重新计算——使用缓存值。

**模型适配调整：**

- **短上下文模型（≤8k tokens）：** 预算缩减 25%（`budget_short_context_shave = 0.25`），为用户任务专用 prompt 留出余量。
- **长上下文模型（≥100k tokens）：** 唤醒上下文预算可扩展至 9,000 tokens（`budget_long_context_expand_to = 9000`），仍是总窗口的很小比例，但足够丰富。

每次资产写入时重新计算 token 估算值（捕获正文的重大变化）；所有查询时操作使用缓存值。

#### 5.1.4 缓存

相关性闸门使用三级缓存，均在 §3.3 中详述：

**嵌入缓存（`cache/embedding/vectors.db`）：**
- 每个资产一行，以 `asset_id` 为索引。
- 写入时按资产粒度失效：仅对变更的资产重新嵌入（通过 `asset_hash.json` sha256 diff 检测）。
- 当 `cache/embedding/version` 与配置的模型标识符不匹配时触发全量重建。
- 缓存未命中 → 重新嵌入并写入后继续；查询不会因此失败。

**FTS5 缓存（`cache/fts5/index.db`）：**
- 每次资产写入时增量更新。
- 无外部依赖：SQLite FTS5 内置于 sqlite3 标准库。
- schema 版本不匹配时全量重建。

**相关性缓存（`cache/relevance/`）：**
- Key：`sha256(task + str(budget_tokens) + active_assets_hash)` — 捕获完整查询上下文。
- Value：序列化的 `ranked_assets` 列表 + `packed_prompt` 字符串。
- TTL：1 小时（默认；`cache_ttl_seconds = 3600`）。
- 任何 `enforcement: mandatory` 资产写入时全部失效（因为强制包含影响整体预算计算）。
- LRU 淘汰，上限 1,000 条（见 §3.3）。

**缓存命中率目标：** 稳态使用下（相同项目、相似任务模式每日重复）会话启动时 ≥65%。

#### 5.1.5 调优参数（`config.toml`）

`[relevance_gate]` 节暴露所有可调参数：

```toml
[relevance_gate]
enabled = true

# 阶段 2：检索广度
candidate_top_k_semantic = 50
candidate_top_k_bm25 = 50
candidate_include_all_subscribed = true

# 阶段 3：混合融合
hybrid_keyword_weight = 0.30      # MemPalace 已调优；不经基准测试不要修改

# 阶段 4：时间邻近加权
temporal_max_boost = 0.40
temporal_window_multiplier = 1.5

# 阶段 5：两段检索
two_pass_enabled = true
two_pass_first_k = 5

# 阶段 6：scope 权重与时效衰减
weights_scope = { project = 1.5, user = 1.2, team = 1.0, org = 0.8 }
weights_recency_halflife_days = 30

# 阶段 7：预算
budget_default_tokens = 900
budget_short_context_shave = 0.25
budget_long_context_expand_to = 9000

# 缓存
cache_ttl_seconds = 3600
cache_hit_rate_target = 0.65
```

**校验规则：** `engram validate` 若 `hybrid_keyword_weight` 超出 [0.15, 0.45] 范围则发出 `W-RG-001` 警告——该范围基于 MemPalace 已发表的基准。超出范围的值被允许但会被标记。

#### 5.1.6 防御指标博弈

相关性闸门以"最相关资产装入预算"为优化目标。存在两类博弈风险：

**宽泛描述博弈：** `description` 字段极宽泛的资产会对几乎所有查询都命中 top-K，挤占真正相关的资产。

**关键词填充：** 在 `body` 中堆砌任务匹配关键词会人为抬高 BM25 分数。

防御措施（被动式，浮现给操作员而非自动惩罚）：

- `description` 字段长度 > 150 字符 → 校验警告 `W-FM-002`（来自 SPEC §12）。
- 资产在所有相关性查询中的命中率 > 存储平均命中率的 3 倍 → 在 `engram review` 输出中标记为"疑似宽泛"。
- BM25 分数异常：若资产 BM25 分数相对其语义距离异常偏高（暗示词频膨胀）→ `engram review` 中显示"可能存在关键词填充"提示。

三项均为**向操作员浮现的警告，绝不是查询时的自动惩罚。** 合法意义上宽泛的资产（如用户身份、全组织安全策略）不应因真实的宽泛性而被惩罚。

#### 5.1.7 降级模式

相关性闸门有三种运行模式，自动选择：

| 模式 | 触发条件 | 行为 |
|---|---|---|
| **全功能（默认）** | 嵌入缓存存在且嵌入器可达 | 全部 7 个阶段运行；语义 + BM25 + 结构检索 |
| **离线** | 无嵌入提供商或无缓存（首次运行、气隙环境） | 跳过阶段 2a（语义）；仅 BM25 + 结构检索。质量下降但系统不报错 |
| **应急** | 可用预算甚至不足以容纳强制资产 | 发出错误；packed_prompt 仅包含用户身份 + 按 scope 特异性排名的 top-3 强制资产 |

操作员可显式强制指定模式：

```bash
engram context pack --task='...' --mode=offline
```

模式选择记录到 `journal/usage.jsonl`（当使用日志启用时），以便操作员发现降级模式频繁触发。

#### 5.1.8 基准测试

相关性闸门的目标指标：

| 指标 | 目标 | 说明 |
|---|---|---|
| LongMemEval R@5（原始 BM25 基线） | ≥95% | 与 MemPalace 报告的原始模式匹配 |
| LongMemEval R@5（hybrid v2） | ≥98% | MemPalace Hybrid v2 结果；engram 采用相同算法 |
| 打包延迟（热缓存） | <200ms | ≤10k 资产存储，900 token 预算 |
| 打包延迟（冷缓存） | <1s | 含嵌入查找的完整流水线 |
| 缓存命中率（稳态） | ≥65% | 会话启动唤醒，相同项目，相似任务模式 |

**基准测试套件：** `benchmarks/longmemeval_relevance_gate.py` — 在本地资产存储上复现 LongMemEval 评估。作为里程碑 M6 校验的一部分运行（实现计划附件 B，章节 B.3）。套件遵循 MemPalace 的 `benchmarks/BENCHMARKS.md` 规范：固定随机种子，仅使用公开测试集，不对测试集进行超参数调优。

运行方式：

```bash
python benchmarks/longmemeval_relevance_gate.py --store=~/.engram --split=test
```

---

---

### 5.2 一致性引擎

#### 5.2.0 职责概述

一致性引擎负责检测 engram 存储中 7 类不一致问题（SPEC §11.1），提出整改建议，且**永不直接修改资产**。其唯一输出为：

- `~/.engram/journal/consistency.jsonl` — 仅追加的提案日志
- `graph.db consistency_proposals` 表 — 提案的可查询索引（按需从日志重建）

引擎不会自行解决提案。每一项解决操作都需要人工或 LLM 通过 `engram consistency resolve` 进行明确确认。这一设计遵循了 §5.0.3 原则 1 和 SPEC §11 所规定的"建议，绝不直接修改"不变性。

检测的 7 类（SPEC §11.1）：`factual-conflict`（事实冲突）、`rule-conflict`（规则冲突）、`reference-rot`（引用失效）、`workflow-decay`（工作流衰减）、`time-expired`（时效过期）、`silent-override`（隐式覆盖）、`topic-divergence`（主题分歧）。

---

#### 5.2.1 四阶段扫描架构

引擎由四个可独立调度的阶段组成。每个阶段均可在 `config.toml` 的 `[consistency]` 节下单独启用或禁用。

```
触发器（定时任务或 engram consistency scan）
  │
  ▼
阶段 1：静态检查  （快速，每次写入，<20 ms/资产）
  ├─ SPEC 结构验证
  ├─ 前置元数据格式检查
  ├─ 引用目标可达性检查
  └─ 生命周期状态转换合法性检查
  │
  ▼
阶段 2：语义聚类  （每日，后台执行）
  ├─ 嵌入所有资产（复用 cache/embedding/）
  ├─ DBSCAN 聚类
  ├─ 逐簇：通过静态规则检测矛盾
  └─ 生成候选提案
  │
  ▼
阶段 3：LLM 审核  （每周或按需，可选）
  ├─ 采样含可疑对的簇
  ├─ LLM 生成结构化提案 JSON
  └─ 追加至 consistency.jsonl
  │
  ▼
阶段 4：执行验证  （每周或按需）
  ├─ 运行每个工作流的 fixtures/
  ├─ 为失败项生成 workflow-decay 提案
  └─ 为通过项更新置信度字段
  │
  ▼
consistency.jsonl 提案
```

**默认调度摘要：**

| 阶段 | 默认触发条件 | 配置键 |
|---|---|---|
| 阶段 1 | 每次资产写入 | 始终启用，无配置键 |
| 阶段 2 | 每日本地 02:00 | `[consistency].scan_schedule` |
| 阶段 3 | 默认禁用 | `[consistency].llm_review_enabled` |
| 阶段 4 | 每周六本地 03:00 | `[consistency].phase_4_schedule` |

各阶段可独立配置（开/关、调度时间）。§5.2.2–§5.2.5 分别详述各阶段。

---

#### 5.2.2 阶段 1 — 静态检查

**触发时机：** 每次资产写入——`engram memory add`、`engram memory update`、`engram workflow revise`，以及任何写入资产的适配器/脊柱。

**检查项（每项均须在 <20 ms 内完成）：**

- SPEC §12 结构性错误码：`STR-*`（结构）、`FM-*`（前置元数据）、`MEM-*`（记忆体专项）、`WF-*`（工作流专项）、`KB-*`（知识库）、`IDX-*`（索引）
- 引用图完整性（`REF-*`）：所有 `references:` 目标存在；无循环 `supersedes:` 链
- 强制执行合法性（`ENF-*`）：未经 `overrides:` 声明的强制覆盖视为非法
- 作用域一致性（`SCO-*`）：`scope:` 标签与文件系统位置匹配；`org/team/pool` 名称能在目录层级中解析

**实现方式：** 进程内运行（不做工作空间隔离——速度快、同步执行）。结果写入 `graph.db` 的 `validation_results` 表：

```sql
CREATE TABLE validation_results (
    asset_id    TEXT NOT NULL,
    code        TEXT NOT NULL,       -- 例如 'E-FM-003'
    severity    TEXT NOT NULL,       -- error | warning | info
    message     TEXT,
    detected_at TEXT NOT NULL,
    resolved_at TEXT,
    PRIMARY KEY (asset_id, code)
);
```

**输出区分：** 阶段 1 **不**写入 `consistency.jsonl`。其结果写入验证表，并通过 `engram review` / `engram validate` 呈现给用户。分离的原因在于：阶段 1 的结果属于**写入时的结构性错误**（应由作者立即修复），而非**语义层面的不一致**（需经审核，且可能是有意为之）。

---

#### 5.2.3 阶段 2 — 语义聚类

**触发时机：** 定时执行（默认：每日本地 02:00，可通过 `[consistency].scan_schedule` 调整），或直接调用 `engram consistency scan --phase=2`。

**算法：**

```python
def phase_2():
    # 复用嵌入缓存，避免对未变更资产重复嵌入
    vectors = load_embeddings_from_cache()

    # DBSCAN 聚类——无需预先指定簇数
    clusters = DBSCAN(
        eps=compute_adaptive_eps(vectors),  # k-NN 距离的第 75 百分位（k=5）
        min_samples=3,                      # 最小簇大小
        metric='cosine'
    ).fit_predict(vectors)

    proposals = []
    for cluster_id, asset_ids in group_by_cluster(clusters):
        # 对每个簇应用静态规则模式
        for rule_id, matcher in CLUSTER_RULES:
            for match in matcher(asset_ids):
                proposals.append(make_proposal(rule_id, match, cluster_id))

    return proposals
```

**簇规则（检测特定资产间模式）：**

| 规则 | 检测模式 | 提案类别 |
|---|---|---|
| CR-1 | 两个资产存在对立关键词对（如"优先 rebase"vs."禁止 rebase"） | `rule-conflict` |
| CR-2 | 两个资产共享 `tags:` 但数值字段或枚举值不同 | `factual-conflict` |
| CR-3 | 较新资产未通过 `supersedes:` 指向同簇的同主题旧资产 | `silent-override` |
| CR-4 | ≥3 个资产讨论相同主题但结论分歧 | `topic-divergence` |
| CR-5 | 资产引用 URL/路径 → 发起 HEAD 请求；返回 404 | `reference-rot` |
| CR-6 | 资产 `valid_to` 已过期 + ≥1 个活跃资产仍在引用它 | `time-expired` |

**自适应 `eps`：** 每次运行时从 k 近邻距离分布（k=5）中计算。取排序距离曲线的肘点，随存储规模变化防止欠聚类或过聚类。

**性能目标：** 单 CPU 消费级笔记本（无需 GPU）10 分钟内处理 1 万个资产。

**工作空间隔离：** 阶段 2 使用 `~/.engram/workspace/consistency-<run-id>/` 存放中间数据。提案在阶段结束时原子性地写入 `consistency.jsonl`。

---

#### 5.2.4 阶段 3 — LLM 审核（可选）

**触发时机：** `[consistency].llm_review_enabled = true`（默认：`false`）。启用后每周执行，或通过 `engram consistency scan --phase=3` 按需调用。

**算法：**

```python
def phase_3(candidate_proposals):
    # 每个簇取一个提案，按严重程度优先（critical > high > medium > low）
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

**LLM 提供商：** 在 `[consistency].llm_provider` 下配置，支持：

- `ollama` / `llama.cpp` — 默认；本地运行，可气隙部署，完全保护隐私
- `anthropic` / `openai` / `google` — 需显式选择；操作员须配置 API 密钥

**预算：** `[consistency].llm_review_budget_tokens_per_scan`（默认：5 万 token）。超出预算的扫描将被跳过并记录警告。

**工作空间隔离：** 与阶段 2 共用 `~/.engram/workspace/consistency-<run-id>/` 工作空间。LLM 请求/响应对在提交前写入工作空间以供审计。

**误报防御：** 目标误报率 ≤5%。若最近 100 次 LLM 审核的观测误报率超过 10%（以后续被人工 dismiss 的提案占比衡量），阶段 3 将自动暂停，并通过 `engram review` 和指标仪表板通知操作员。

---

#### 5.2.5 阶段 4 — 执行验证

**触发时机：** 每周定时执行（默认：周六本地 03:00，可通过 `[consistency].phase_4_schedule` 调整），或执行 `engram consistency scan --phase=4`。

**算法：**

```python
def phase_4():
    proposals = []
    for workflow in list_all_workflows():
        results = run_fixtures(workflow)   # 执行工作流的 fixtures/ 测试套件
        for fixture_result in results:
            if fixture_result.failed:
                proposals.append(make_proposal(
                    class_='workflow-decay',
                    involved=[workflow.id],
                    evidence=fixture_result.diff,
                    severity='error' if fixture_result.regression else 'warning',
                ))
            else:
                # 正向置信度信号——工作流仍然有效
                update_confidence(workflow.id, event='validated')
    return proposals
```

**预算：** `[consistency].phase_4_time_budget_seconds`（默认：600 秒总计）。超出单个 fixture 超时限制的测试将被终止，并为其生成 `severity=error` 的 `workflow-decay` 提案。

**工作空间：** 每个工作流的 fixtures 在其独立工作空间（`workflows/<name>/rev/current/`）中运行，复用工作流专属沙箱，而非引擎级共享工作空间。

---

#### 5.2.6 置信度更新引擎

**对应 SPEC §4.8 和 §11.4。** 本节说明驱动这些公式的更新流水线。

**事件来源：**

1. **LLM 自报告** — `engram memory validate-use <id> --outcome=success|failure|ambiguous`（由脊柱和适配器在使用资产后调用）
2. **人工审核** — `engram review` TUI 和 Web UI 中的点赞/点踩
3. **阶段 4 正向信号** — fixture 测试通过后调用 `update_confidence(workflow.id, event='validated')`
4. **收件箱解决信号** — 当 `bug-report` 类型的收件箱消息被解决时，被引用的资产收到 `validated` 事件

**流水线：**

```
事件来源
      │
      ▼ 追加
usage.jsonl  （仅追加，永不修改）
      │
      ▼ 批量聚合（每 1 小时或每 100 个事件，取先到者）
      │
      ▼
graph.db  assets.confidence_score  （就地更新）
      │
      ▼ 分数低于阈值时生成提案
      │
      ▼
consistency.jsonl  （低置信度提案）
```

**置信度公式（SPEC §4.8）：**

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

公式对矛盾的惩罚力度是验证奖励的两倍，并对 90 天内未经验证的资产施加陈旧性惩罚。

**低置信度阈值：** `[consistency].low_confidence_threshold`（默认：−0.2）。`confidence_score` 低于此阈值的资产将触发 `time-expired` 或 `topic-divergence` 提案，取决于主要信号来自陈旧性还是簇级分歧。

---

#### 5.2.7 解决命令应用

SPEC §11.5 定义了 6 种解决操作。本节说明每种操作的具体文件系统动作。

**`update` — 重写资产内容或前置元数据：**

```python
def apply_update(proposal, target_id, new_content):
    asset = load(target_id)
    updated = {**asset, 'body': new_content, 'updated': now()}
    save_atomic(updated)
    journal.append('proposal_resolved', proposal.id, action='update')
```

**`supersede` — 将旧资产标记为已弃用，并从新资产建立引用：**

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

**`merge` — 将多个资产合并为一个：**

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

**`archive` — 将资产移至归档目录：**

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

**`dismiss` — 将提案标记为误报：**

```python
def apply_dismiss(proposal, reason):
    updated_proposal = {**proposal, 'status': 'dismissed', 'dismiss_reason': reason}
    save_proposal(updated_proposal)
    journal.append('proposal_resolved', proposal.id, action='dismiss', reason=reason)
    # 对相同提案（相同 involved_assets + class）自动 dismiss 90 天
    register_dismiss_suppression(proposal.involved_assets, proposal.class_, ttl_days=90)
```

**`escalate` — 路由至作用域维护者：**

```python
def apply_escalate(proposal):
    updated_proposal = {**proposal, 'status': 'escalated'}
    save_proposal(updated_proposal)
    if is_mandatory_asset(proposal):
        notify_scope_maintainer(proposal)
    journal.append('proposal_resolved', proposal.id, action='escalate')
```

全部 6 个 `apply_*` 函数均使用 `save_atomic`（写入 `.tmp` 后 `rename`）防止部分写入。所有日志条目遵循 SPEC §10 仅追加事件格式。

---

#### 5.2.8 CLI 接口概览

`engram consistency` 子命令（来自 §4 CLI 清单，补充操作细节）：

| 命令 | 说明 |
|---|---|
| `engram consistency scan [--phase=1\|2\|3\|4] [--classes=...]` | 触发扫描；默认运行阶段 1+2；阶段 3 和 4 需显式指定 `--phase` |
| `engram consistency report [--status=...] [--severity=...] [--since=...]` | 按条件列出提案 |
| `engram consistency resolve <proposal-id> --action=<action>` | 应用一项解决操作 |
| `engram consistency dismiss-all --criteria='<jq-expr>'` | 批量 dismiss 匹配提案；需 `--yes` 确认（管理员操作，不可逆） |

`scan` 的 `--classes` 过滤器接受以逗号分隔的 7 个类别名称子集，例如 `--classes=rule-conflict,silent-override`。

---

#### 5.2.9 可观测性指标

指标写入 `graph.db` 的 `metrics_consistency` 表，并被智慧指标组件（§5.5）消费：

```sql
CREATE TABLE metrics_consistency (
    run_id              TEXT NOT NULL,
    phase               INTEGER NOT NULL,     -- 1 | 2 | 3 | 4
    run_at              TEXT NOT NULL,
    asset_count         INTEGER,
    proposals_emitted   INTEGER,
    proposals_dismissed INTEGER,
    duration_ms         INTEGER,
    PRIMARY KEY (run_id, phase)
);
```

**关键信号：**

| 指标 | 用途 |
|---|---|
| 提案生成速率（每日） | 峰值表明存储频繁变动或摄取问题 |
| 检测延迟（阶段 1 p50/p95） | 从资产写入到验证结果的时间 |
| 阶段 2 扫描耗时 | 时间、资产数量、生成的提案数 |
| 误报率 | 通过 `action=dismiss` 关闭的提案占比 |
| 解决吞吐量 | 每日解决的提案数，按操作类型分类 |

这些指标为智慧指标的"记忆整理比率"曲线（§5.5）提供数据。

---

### 5.3 自学习引擎

#### 5.3.0 职责

自学习引擎对特定 Workflow 资产进行演化。给定一个包含 `spine.*` 文件、`fixtures/` 目录和 `metrics.yaml` 的工作流，引擎生成对 spine 的候选修改，运行 fixture 套件，保留能改善主要指标的修改——然后循环。失败的轮次会被存档以供审计；成功的轮次推进 `current` 符号链接。

由 `engram workflow autolearn <name>` 显式触发。在 `~/.engram/workspace/autolearn-<run-id>/` 工作区沙箱中运行，相互隔离。成功时，写入新的 `rev/rN/` 目录并将 `current` 指向新版本。回退时，符号链接保持在先前版本；失败的版本以 git commit 记录以供溯源。

引擎在 `--rounds=N` 完成（默认预算内无限）或达到阶段闸门（§5.3.5）时停止。它绝不修改 `workflow.md`、`fixtures/` 或 `metrics.yaml`——这些均为只读输入。

---

#### 5.3.1 八条纪律

自学习引擎依照 Karpathy 的 `autoresearch` 八条纪律化的智能体循环建模。每条纪律对应一个具体机制：

**纪律 1 — 固定每轮预算。**
`[autolearn].default_budget_seconds = 300`（5 分钟）。超过此实际时钟预算的轮次将被终止，视为崩溃失败。时间预算确保每轮资源有界且结果可比。

**纪律 2 — 单文件边界。**
每轮仅修改 `spine.*`。`workflow.md`、`fixtures/` 和 `metrics.yaml` 以只读方式打开。该约束使搜索空间可控，并确保 fixture 评估始终基于已知有效的测试套件。

**纪律 3 — 永不停止（预算内）。**
若某轮失败（未改善、被拒绝或崩溃），引擎立即启动下一轮——无需暂停，无需提示。`--rounds=N` 参数限制总轮次；在此上限内，引擎自主运行。这与 autoresearch 的"NEVER STOP"指令一致：引擎预设为无人值守运行，直至人工中断或轮次预算耗尽。

**纪律 4 — 仅追加结果。**
`rev/<N>/outcome.tsv`（每版本）和 `journal/evolution.tsv`（跨版本）为仅追加文件。已有行不会被修改；新轮次追加新行。这形成了所有自学习活动的防篡改审计记录。

**纪律 5 — 保留或回滚。**
每轮结束后：若指标改善且满足评估阈值 → 保留新版本（移动 `current` 符号链接，git commit）；否则 → 回滚（符号链接不变；失败版本提交为审计记录）。没有中间状态；每个结果要么是干净推进，要么是有文档的回退。

**纪律 6 — 简洁性准则。**
拒绝满足 `new_spine_lines > complexity_budget_factor × old_spine_lines`（默认 1.5×）的 diff。这防止通过复杂度膨胀来刷指标——即 LLM 在 spine 中填充冗余步骤以通过 fixture 检查，却无实质改善。可在每个工作流的 `metrics.yaml` 中通过 `complexity_budget_factor` 字段单独配置。

**纪律 7 — 复杂度下限。**
每轮结束后，工作流必须保留最少数量的步骤/检查点。可在每个工作流的 `metrics.yaml` 中通过 `min_steps` 字段配置（默认：当前步骤数）。防止优化崩溃——即 LLM 通过将 spine 精简为空壳来"改善"主要指标。

**纪律 8 — 人工可审查。**
每 K 轮（默认 `phase_gate_rounds = 5`），自学习引擎暂停，并将 diff 摘要以待处理自学习检查点形式写入 `engram review`。人工必须通过 `engram workflow autolearn --continue <name>` 确认后才能开始下一阶段。这让运维人员对引擎行为保持可见性，确保没有长时间运行的自学习会话完全脱离人工审查。`--unattended` 标志可禁用此闸门（§5.3.5）。

---

#### 5.3.2 每轮算法

```python
def autolearn_round(workflow, context):
    workspace = create_workspace(f'autolearn-{run_id}-round-{N}')

    # 步骤 1：加载当前版本
    current = load_rev(workflow, 'current')
    copy_to_workspace(current, workspace)

    # 步骤 2：提案生成（LLM）
    proposer_context = build_context(workflow, recent_outcomes=last_10)
    proposed_diff = proposer_llm.complete(
        system=AUTOLEARN_PROPOSER_PROMPT,
        user=proposer_context,
    )
    apply_diff(workspace, proposed_diff)

    # 步骤 3：简洁性检查（纪律 6）
    if lines(workspace.spine) > complexity_budget_factor * lines(current.spine):
        return RoundResult(status='rejected', reason='complexity_budget_exceeded')

    # 步骤 4：复杂度下限检查（纪律 7）
    if count_steps(workspace.spine) < workflow.min_steps:
        return RoundResult(status='rejected', reason='complexity_floor_violated')

    # 步骤 5：运行 fixtures（含时间预算，纪律 1）
    with time_budget(default_budget_seconds):
        fixture_results = run_fixtures(workspace)

    # 步骤 6：计算指标
    new_metrics = aggregate_metrics(fixture_results, workflow.metrics_yaml)

    # 步骤 7：静态评分（60 分）
    static_score = score_static(workspace)   # SPEC 验证器 + schema + 无密钥

    # 步骤 8：性能评分（40 分）
    performance_score = score_performance(
        new_metrics, current.metrics, workflow.ratchet_rule
    )

    total_score = static_score + performance_score  # 0..100

    # 步骤 9：独立评委（独立 LLM 会话——Darwin G3 纪律）
    judge_ctx = build_judge_context(current, workspace, fixture_results)
    judge_verdict = judge_llm.complete(
        system=AUTOLEARN_JUDGE_PROMPT,
        user=judge_ctx,
    )

    # 步骤 10：决策（纪律 5）
    if total_score >= threshold and judge_verdict.endorse:
        commit_new_rev(workflow, workspace)
        return RoundResult(
            status='kept', new_rev=f'r{N+1}', metrics=new_metrics
        )
    else:
        archive_failed_rev(workspace)   # 存档审计（纪律 4）
        return RoundResult(
            status='reverted',
            reason=build_reason(total_score, judge_verdict)
        )
```

**提案者/评委分离（Darwin G3）：** 两个独立的 LLM 会话，无共享上下文。提案者看到当前工作流、指标历史和 fixture 描述；评委仅看到 diff 和实测 fixture 结果。这防止提案者为自身评估刷分——这是单会话自改进循环的已知失效模式。

`AUTOLEARN_PROPOSER_PROMPT` 指导提案者分析当前 spine 为何表现欠佳，并生成最小化的定向 diff。`AUTOLEARN_JUDGE_PROMPT` 指导评委独立于提案者推理，判断实测结果是否真正支持所声称的改善。

---

#### 5.3.3 Git 原生棘轮（Darwin G1）

每轮自学习以真实的 git commit 持久化至工作流版本历史中：

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
    └── current -> r3/      # 符号链接；仅在接受时向前移动
```

**接受路径：** `ln -sf r{N+1} current && git add rev/r{N+1}/ && git commit -am "autolearn r{N+1} accepted, primary_metric +X%"`。commit 信息包含指标增量，使 `git log --oneline` 成为人类可读的改善日志。

**拒绝路径：** `git add rev/r{N+1}/; git commit -m "autolearn r{N+1} rejected — reason"`。符号链接不移动。失败版本以 commit 记录（纪律 4），但不是线上版本。

**Git 历史不变性：** 工作流分支上的每个 commit 要么是单调改善的接受，要么是明确标注的审计拒绝。不存在静默回滚。运维人员仅通过 `git log` 即可重建完整的自学习历史。

**运营优势：**
- 通过 `git reset` 完整回滚（运维人员覆盖任何已接受轮次）。
- `git blame spine.py` 将当前 spine 中每一行追溯至引入它的自学习轮次。
- 分发：`engram workflow sync` 将新版本推送至团队或 pool 远端，支持跨机器自学习协作。

---

#### 5.3.4 双维度评分标准（Darwin G2）

每轮在 100 分制下评分，综合静态合规性与性能改善两个维度。

**静态评分（60 分）：**

| 评分项 | 分值 |
|---|---|
| SPEC §12 `E-WF-*` 验证器全部通过 | 20 |
| 所有 fixtures 语法有效（YAML） | 10 |
| `spine.*` 在声明的 `spine_lang` 下可解析 | 10 |
| 未引入新的密钥或凭证（正则扫描） | 10 |
| `metrics.yaml` 中所有引用均可解析 | 5 |
| `inputs_schema` / `outputs_schema` 仍然合规 | 5 |
| **静态总分** | **60** |

**性能评分（40 分）：**

| 评分项 | 分值 |
|---|---|
| 所有成功用例 fixtures 通过 | 15 |
| 无失败用例 fixture 回退（之前通过的失败用例仍通过） | 10 |
| 主要指标 Δ 沿棘轮方向改善 | 10 |
| 所有附加指标均未回退 | 5 |
| **性能总分** | **40** |

**阈值：** 默认 `70/100`。低于阈值的轮次无论评委裁决如何均自动拒绝。可在每个工作流的 `metrics.yaml` `autolearn_threshold` 字段中配置（范围 50–95）。

**评委否决：** 即使 `total_score >= threshold`，评委 `endorse=false` 也会阻止接受。评委的书面理由记录在 `outcome.tsv` 中供运维人员审查。

---

#### 5.3.5 阶段闸门（Darwin G4）

每 K 轮连续运行后（默认 `phase_gate_rounds = 5`），自学习引擎暂停：

1. 生成阶段摘要：运行轮次、接受轮次、自上次闸门以来的主要指标 Δ、按行数排列的前 3 个 spine diff。
2. 将摘要写入 `engram review`，作为待处理的自学习检查点（与一致性引擎提案使用同一队列）。
3. 阻塞，直至运维人员执行：
   - `engram workflow autolearn --continue <name>` — 继续下一阶段。
   - `engram workflow autolearn --abort <name>` — 停止；存档本次运行；保持当前版本。

**`--unattended` 标志：** 完全禁用阶段闸门。适用于 CI/cron 自动化。需同时满足两个显式条件：
- `config.toml` 中 `[autolearn].allow_unattended = true`。
- 针对特定工作流启用无人值守模式的签名 commit（维护者级别 GPG 密钥）。

两个条件共同防止意外或恶意的无人值守运行。未设置 `allow_unattended` 的 CI 作业将在首个闸门处暂停，而非无限运行。

---

#### 5.3.6 CLI 接口

| 命令 | 说明 |
|---|---|
| `engram workflow autolearn <name> [--rounds=N] [--budget=Ns] [--unattended]` | 启动自学习；rounds 和 budget 默认取配置值 |
| `engram workflow autolearn-status <name>` | 显示进度：已完成轮次、当前版本、待处理阶段闸门、接受率 |
| `engram workflow autolearn --continue <name>` | 阶段闸门后解除阻塞；开始下一阶段 |
| `engram workflow autolearn --abort <name>` | 取消；保留审计记录；保持当前版本 |
| `engram workflow rollback <name> [--to=<rev>]` | 手动回滚至先前版本（运维人员覆盖；来自 §4 CLI 清单） |

所有命令在出错时以非零码退出，并将结构化 JSON 写入 stderr，遵循 §4 错误格式约定。

---

#### 5.3.7 可观测性

每个工作流的 `journal/evolution.tsv` 每轮追加一行（仅追加）：

```
rev	ts	proposer_tokens	judge_endorse	static	performance	total	primary_metric	accepted	reason
r1	2026-04-18T10:30:00Z	1248	true	58	35	93	4.2s	true	initial
r2	2026-04-18T10:38:00Z	1440	false	55	28	83	4.5s	false	metric_regress
r3	2026-04-18T10:44:00Z	1320	true	60	38	98	3.9s	true	improvement
```

字段说明：`rev`（版本标签）、`ts`（ISO 8601）、`proposer_tokens`（提案者消耗的 LLM token 数）、`judge_endorse`（布尔值）、`static` / `performance` / `total`（各维度得分）、`primary_metric`（原始值）、`accepted`（布尔值）、`reason`（评委或拒绝规则的自由文本）。

**输送至智慧指标"工作流掌控曲线"（§5.6）的信号：**

| 信号 | 用途 |
|---|---|
| 接受轮次 / 总轮次 | 接受率；低接受率表明提案者能力弱或阈值过严 |
| 主要指标时间序列 | 改善轨迹；平台期检测 |
| 复杂度趋势（各版本 spine 行数） | 在纪律 6 生效的情况下捕捉潜在复杂度增长 |
| 首次改善所需轮次 | 首次接受前经历的轮次数；工作流难度的代理指标 |

---

### 5.4 演化引擎

#### 5.4.0 职责

演化引擎对 Memory（及知识库文章）资产进行演化。与自学习引擎——在通过棘轮检查后直接修改工作流 spine——不同，演化引擎**仅生成提案**。所有提案进入一致性引擎的提案流，需要运维人员显式接受后方可修改任何资产。

该设计受 evo-memory 的 **ReMem** 循环启发：行动 → 思考 → 精炼。引擎基于近期使用数据（协同加载模式、嵌入偏移、矛盾事件）进行行动，思考哪些结构性变更能提升清晰度或覆盖率，并生成具体的精炼提案。

默认每月触发一次（`[evolve].cadence = "monthly"`），或通过 `engram evolve scan` 按需触发。每月频率刻意保守：记忆资产积累缓慢，激进扫描会以超出运维人员处理能力的速度向审查队列注入提案。

---

#### 5.4.1 精炼类型

演化引擎生成四类提案，每类映射至一致性引擎提案格式（§5.2.3）中的一个或多个 `suggested_resolutions`。

**类型 1 — 合并（2+ 记忆 → 1）**

- *触发条件：* 协同加载率 > 60%（在 ≥ 60% 的相关性闸门输出集中同时出现）且平均成对余弦距离 < 0.20（高语义重叠）的记忆簇。
- *提案操作：* 将内容合并为单条记忆，保留最优前置元数据字段，在源记忆上添加 `supersedes:` 指向合并目标。
- *原因：* 两条始终协同加载且语义近乎相同的记忆以双倍 token 代价提供了可忽略的信息增益。

**类型 2 — 拆分（1 条记忆 → N 条）**

- *触发条件：* 单条记忆长度在其类型中达到或超过第 95 百分位，且对其内容进行句级 DBSCAN 聚类揭示 ≥ 2 个不同的子主题簇。
- *提案操作：* 创建 N 条新记忆（每个子簇一条），各有聚焦的标题和正文；将原记忆标记为已弃用，`supersedes:` 链指向所有 N 个后继。
- *原因：* 密集记忆增加部分相关性风险——相关性闸门在仅需一个子主题时检索整条记忆，虚增上下文成本。

**类型 3 — 升级为知识库文章**

- *触发条件：* 3 条或更多相关记忆均处于高长度百分位，频繁协同加载（> 60%），且主题连贯（语义簇紧密且质心主题可清晰命名）。
- *提案操作：* 起草一篇新知识库文章（自动生成的 `README.md` 骨架及建议章节结构）；将源记忆改写为指向新知识库文章各章节的 `reference` 类型指针。
- *原因：* 当多条大型记忆围绕同一主题时，它们是升级为结构化知识库文章的候选——后者支持按章节部分加载。

**类型 4 — 改写以提升清晰度**

- *触发条件：* 记忆的 `confidence_score < -0.2`，且在近 90 天内有 ≥ 2 次矛盾事件（来自一致性引擎历史），且使用稳定（未趋向弃用——仍被定期加载）。
- *提案操作：* LLM 生成的改写，保留所有关键观点但澄清模糊语言；新正文出现在提案记录中，运维人员并排审查后决定是否接受。
- *原因：* 持续触发矛盾检测的记忆很可能表述不够精确，而非事实有误。从源头改写精确化可消解矛盾检测问题。

---

#### 5.4.2 算法

```python
def evolve_scan():
    # 阶段 1：收集候选

    candidates = []

    # 合并候选
    for cluster in dbscan_cluster_memories(eps=0.15, min_samples=2):
        if coloading_rate(cluster) > 0.60 and avg_cosine_dist(cluster) < 0.20:
            candidates.append(MergeCandidate(cluster))

    # 拆分候选
    for mem in memories_at_p95_length():
        sub_clusters = sentence_level_cluster(mem.body)
        if len(sub_clusters) >= 2:
            candidates.append(SplitCandidate(mem, sub_clusters))

    # 升级候选
    for cluster in high_length_coloaded_clusters():
        if len(cluster) >= 3 and topic_coherent(cluster):
            candidates.append(PromoteCandidate(cluster))

    # 改写候选
    for mem in memories_below_confidence(-0.2):
        if contradiction_count(mem, window_days=90) >= 2:
            if not trending_to_deprecation(mem):
                candidates.append(RewriteCandidate(mem))

    # 阶段 2：预算与优先排序
    prioritized = prioritize_by_impact(
        candidates,
        budget=config.proposals_per_cadence_max   # 默认 20
    )

    # 阶段 3：提案生成（LLM 生成具体提案内容）
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

    # 阶段 4：更新指标
    update_evolve_metrics(
        cadence_run_at=now(),
        proposals_emitted=len(prioritized),
        candidates_found=len(candidates),
    )
```

**关键设计选择：** 演化引擎不直接写入任何资产。其唯一输出是追加到 `consistency.jsonl` 的提案记录，与一致性引擎提案使用同一通道。这意味着运维人员的 `engram review` 队列是所有拟议变更的统一入口——无需单独的"演化审查"界面。

**优先排序逻辑（`prioritize_by_impact`）：** 候选按估算的 token 节省量（合并/拆分/升级）或估算的矛盾解决概率（改写）评分，降序排列。前 `proposals_per_cadence_max` 个保留；其余本次周期丢弃，下次重新评估。

---

#### 5.4.3 工作区与沙箱

演化引擎在 `~/.engram/workspace/evolve-<run-id>/` 中运行。沙箱内容：
- `graph.db` 的只读副本（扫描开始时快照；扫描期间不更新）。
- 嵌入重计算和聚类中间结果的暂存区。
- LLM 请求/响应日志（用于可复现性和调试）。

完成后，仅序列化的提案记录离开沙箱，追加至 `consistency.jsonl`。中间数据（嵌入向量、聚类结果）被丢弃。沙箱目录保留 `[evolve].workspace_retention_days` 天（默认 7 天）后删除。

---

#### 5.4.4 与一致性引擎的集成

演化引擎生成的提案使用独立的 `class` 前缀：`evolve-refinement-merge`、`evolve-refinement-split`、`evolve-refinement-promote`、`evolve-refinement-rewrite`。它们存储在同一个 `consistency_proposals` 表中，出现在同一个 `engram review` 队列里。

`class` 前缀支持细粒度过滤：

```bash
engram consistency report --classes=evolve-refinement-merge,evolve-refinement-split
engram consistency report --classes=rule-conflict,factual-conflict
```

**解决路径：** 演化提案与一致性引擎提案接受同样的六种解决操作（§5.2.5）：`update`、`supersede`、`merge`、`archive`、`dismiss`、`escalate`。合并提案最常见的解决操作是 `merge`；拆分提案最常见的是 `supersede`（弃用原始）加 `update`（创建后继）。

**分析分离：** 智慧指标（§5.6）在"记忆整理比率"曲线下单独统计演化提案（标记 `source=evolve`），以区分有意识的结构性演化与被动冲突检测。这使运维人员能够回答：「我的存储是在智能演化，还是只是在积累冲突？」

---

#### 5.4.5 CLI 接口

| 命令 | 说明 |
|---|---|
| `engram evolve scan [--types=merge,split,promote,rewrite]` | 运行扫描；默认运行全部四种类型 |
| `engram evolve status` | 显示最近一次扫描的统计信息：发现的候选数、生成的提案数、历史接受率 |
| `engram evolve enable [--types=...]` | 启用特定精炼类型（默认全部启用） |
| `engram evolve disable [--types=...]` | 禁用特定精炼类型而不禁用整个引擎 |

演化引擎生成的提案通过标准的 `engram review` 和 `engram consistency resolve` 界面进行审查和解决——无需单独的演化专用 resolve 命令。

---

#### 5.4.6 安全性

演化引擎有四条硬性安全约束：

1. **不写入不变性。** 演化引擎绝不直接修改资产或实时 graph。其唯一副作用是向 `consistency.jsonl` 追加记录。若 `consistency.jsonl` 为只读（例如在 CI 环境中），扫描将中止，而不会写入备用位置。

2. **禁止单方面减少记忆数量。** 演化引擎绝不提议在没有对应 supersession 链的情况下减少总记忆数量。每个合并或拆分提案必须包含完整的 `supersedes:` 链接，确保不会有知识被静默丢失。

3. **频率警告。** 若 `[evolve].cadence` 设置为短于每月的间隔（`< 30d`），engram 在启动时发出警告：`"演化周期 <X> 较为激进；审查队列可能超出运维人员处理能力"`。这是警告，非错误——运维人员可确认后继续。

4. **审查队列上限。** `[evolve].proposals_per_cadence_max`（默认 20）限制每次扫描运行的提案数量。若超过 20 个候选通过所有过滤器，仅按影响分值排名前 20 的提案被生成。这防止单次扫描以超出运维人员处理能力的速度向队列注入提案。

---

### 5.5 跨仓传信器

#### 5.5.0 职责

跨仓传信器实现 SPEC §10 中定义的跨仓收件箱协议。其工作是在同一开发者机器上的不同仓库之间实现点对点消息传递：一个仓库的 LLM 代理发送结构化消息；收件仓库的 LLM 在下次会话开始时读取消息；双方都追踪生命周期转换。本节详述守护进程、每次状态转换背后的文件系统操作、去重和限速执行，以及 MCP 工具接口。所有线协议格式（消息 frontmatter、事件模式、意图语义）的权威定义在 SPEC §10；本节描述满足该协议的实现。

---

#### 5.5.1 架构

```
┌──────────────────────────┐       ┌──────────────────────────┐
│  仓库 A 会话              │       │  仓库 B 会话              │
│  ┌────────────────────┐  │       │  ┌────────────────────┐  │
│  │ LLM 调用           │  │       │  │ LLM 在会话开始时   │  │
│  │ engram inbox send  │  │       │  │ 读取收件箱         │  │
│  └──────┬─────────────┘  │       │  └──────┬─────────────┘  │
└─────────┼────────────────┘       └─────────┼────────────────┘
          │                                  ▲
          ▼                                  │
     ~/.engram/inbox/<repo-b-id>/pending/    │
          │                                  │
          ▼                                  │
   监听守护进程 (fs watch inotify/kqueue) ───┘
          │
          ▼
   inter_repo.jsonl 事件 + graph.db inbox_messages 更新
```

**组件：**

| 组件 | 职责 |
|---|---|
| `engram inbox send` CLI / MCP 工具 | 验证输入、执行去重和限速、原子写入消息文件、追加 `inter_repo.jsonl`、向 `graph.db inbox_messages` 插入行 |
| 监听守护进程 | 使用 `inotify`（Linux）或 `kqueue`（macOS）监听 `~/.engram/inbox/*/pending/`；收到 `IN_CREATE` / `NOTE_WRITE` 时更新 `graph.db` 并通过 SSE 通知活跃的 Web UI 会话 |
| `engram context pack` | 在会话开始时读取当前仓库的 `pending/`，将消息注入上下文的 `## 待处理跨仓消息` 节 |
| `graph.db inbox_messages` | 所有消息的索引视图；为 Web UI `/inbox` 页面和按状态/意图/严重性/截止日期的快速查询提供支持 |
| `inter_repo.jsonl` | 只追加的全局事件日志（SPEC §10.7）；反向通知和审计的权威记录 |

**守护进程启动。** 监听守护进程在 `engram daemon start` 下自动启动，或作为 `engram web serve` 内的后台线程运行。每用户一个守护进程实例（不是每仓库）。在 Linux 上使用 `inotify_add_watch`；在 macOS 上使用 `kqueue` / `FSEvents`。守护进程 pid 写入 `~/.engram/run/daemon.pid`。

---

#### 5.5.2 消息生命周期实现

状态转换实现为在 `~/.engram/inbox/<repo-id>/` 下各子目录之间的原子文件系统移动。原子性通过同一文件系统上的 `os.rename()` 实现（POSIX 原子操作）。frontmatter 在移动前在原位重写；graph.db 行在移动提交后更新。

```python
def send(from_repo, to_repo, intent, severity, message, **kwargs):
    # 1. 去重检查（§5.5.3）
    dedup_key = compute_dedup_key(from_repo, to_repo, intent, **kwargs)
    existing = find_pending(to_repo, dedup_key)
    if existing:
        existing.duplicate_count += 1
        existing.body.append(f"\n\n<!-- duplicate received {now} -->\n{message}")
        save_atomic(existing)
        log_event('message_duplicated', existing.message_id, duplicate_count=existing.duplicate_count)
        return existing.message_id

    # 2. 限速检查（§5.5.4）
    check_rate_limit(from_repo, to_repo)  # 超限则抛出 RateLimitError

    # 3. 创建消息文件
    msg_id = generate_message_id(from_repo)   # "<repo-id>:<YYYYMMDD-HHmmss>:<4字符随机数>"
    filename = f"{utcnow_compact()}-from-{slug(from_repo)}-{slug(intent)}-{nonce4()}.md"
    msg_file = Path.home() / f".engram/inbox/{slug(to_repo)}/pending/{filename}"
    write_atomic(msg_file, render_frontmatter(msg_id, from_repo, to_repo, intent, severity, **kwargs) + "\n\n" + message)

    # 4. 更新 graph.db inbox_messages 索引
    insert_inbox_row(msg_id, from_repo, to_repo, intent, severity, 'pending',
                     deadline=kwargs.get('deadline'),
                     related_code_refs=kwargs.get('related_code_refs'),
                     dedup_key=dedup_key)

    # 5. 日志事件（SPEC §10.7）
    log_event('message_sent', msg_id, from_repo=from_repo, to_repo=to_repo,
              intent=intent, severity=severity)

    return msg_id


def transition(msg_id, new_status, note=None, commit_sha=None, reason=None):
    msg = load_inbox_message(msg_id)          # 读取文件 + frontmatter

    # 在子目录之间移动文件（原子 rename）
    old_path = msg.path
    new_path = old_path.parent.parent / new_status / old_path.name
    new_path.parent.mkdir(parents=True, exist_ok=True)

    # 移动前更新 frontmatter
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
    overwrite_frontmatter(old_path, msg)      # 重写后 rename

    atomic_move(old_path, new_path)           # os.rename()

    # 更新 graph.db
    update_inbox_row(msg_id, new_status, resolved_at=msg.resolved_at,
                     resolution_note=note, commit_sha=commit_sha)

    # 日志事件
    log_event(f'message_{new_status}', msg_id,
              resolution_note=note, commit_sha=commit_sha, rejection_reason=reason)
```

**自动归档**在 `engram review` 和 `engram daemon start` 内运行。已解决消息超过 180 天、被拒绝消息超过 30 天时，通过同样的 `transition()` 路径（`new_status='archived'`）移至 `~/.engram/archive/inbox/<repo-id>/<state>/`。

---

#### 5.5.3 去重实现

```python
def compute_dedup_key(from_repo, to_repo, intent, related_code_refs=None, **kwargs):
    """
    优先级顺序（对应 SPEC §10.5）：
    1. 调用方显式传入的 dedup_key — 对批处理的精确控制。
    2. related_code_refs 排序后的哈希 — 合并所有关于同一代码位置的消息，
       不论消息正文措辞如何。最常见情况：两个会话在读取同一文件时
       都发现了同一个 bug。
    3. 正文前缀回退 — 当既无 dedup_key 也无 code refs 时防止纯重复。
    """
    if kwargs.get('dedup_key'):
        return ('explicit', sha256(f"{to_repo}:{intent}:{kwargs['dedup_key']}"))

    if related_code_refs:
        sorted_refs = sorted(related_code_refs)
        return ('coderef', sha256(f"{to_repo}:{intent}:{':'.join(sorted_refs)}"))

    # 回退：正文前 200 字符 + 意图（SPEC §10.5 规则 3）
    body_prefix = kwargs.get('message', '')[:200]
    return ('body_prefix', sha256(f"{from_repo}:{intent}:{body_prefix}"))
```

`find_pending(to_repo, dedup_key)` 通过 `WHERE to_repo=? AND status='pending' AND dedup_hash=?` 查询 `inbox_messages` 表；`dedup_hash` 列存储上述函数返回元组的第二个元素。`(to_repo, status, dedup_hash)` 上的表索引使查询为 O(1)。

**合并语义。** 检测到重复时，新消息正文作为新段落追加到现有文件（带 `<!-- duplicate received <timestamp> -->` 注释，符合 SPEC §10.5）。`duplicate_count` frontmatter 字段加 1。调用方收到现有 `message_id`。`inbox_messages` 中不插入新行。

---

#### 5.5.4 限速

每 `(from_repo, to_repo)` 对执行令牌桶限速。两条独立限制同时生效：

```python
RATE_LIMIT_DEFAULTS = {
    'pending_max':      20,   # A → B 最大并发待处理消息数
    '24h_window_max':   50,   # A → B 在任意 24 小时 UTC 窗口内的最大总发送数（含合并的重复）
}

def check_rate_limit(from_repo, to_repo):
    """若任一限制超出则抛出 RateLimitError，含用户可读信息。"""
    pending = db.scalar(
        "SELECT COUNT(*) FROM inbox_messages WHERE from_repo=? AND to_repo=? AND status='pending'",
        from_repo, to_repo
    )
    if pending >= cfg('inbox.max_pending_per_sender', RATE_LIMIT_DEFAULTS['pending_max']):
        log_event('rate_limit_hit', from_repo=from_repo, to_repo=to_repo,
                  limit_type='pending_cap', current=pending)
        raise RateLimitError(
            f"待处理上限：{from_repo} → {to_repo} 已有 {pending}/{RATE_LIMIT_DEFAULTS['pending_max']} 条待处理消息。\n"
            f"等待收件方处理，或通过以下命令查看：engram inbox list --to={to_repo}"
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
            f"每日窗口：过去 24 小时内 {from_repo} → {to_repo} 已发送 {sent_24h}/{RATE_LIMIT_DEFAULTS['24h_window_max']} 条消息。"
        )
```

两条限制均可在 `~/.engram/config.toml` 的 `[inbox]` 节中按用户配置（§4.4 配置参考）。无论哪条限制触发，`rate_limit_hit` 事件都会追加到 `inter_repo.jsonl`，使运维人员可以监控失控的代理。

---

#### 5.5.5 LLM 会话集成

在会话开始时，`engram context pack` 将待处理的收件箱消息注入打包后的提示词：

1. **读取阶段。** 扫描 `~/.engram/inbox/<当前仓库>/pending/`（按严重性降序、截止日期升序、创建时间升序排序——与 SPEC §10.3 优先级顺序一致）。
2. **预算分配。** 消息共享一个子预算，上限为 `min(总上下文预算的 20%, config inbox.context_budget_pct)`。若消息超出预算，按同样的优先级顺序截断；末尾追加摘要行：`"[还有 N 条待处理消息未显示 — 运行 'engram inbox list' 查看全部]"`。
3. **提示注入。** 消息出现在专用标题下：

```markdown
## 待处理跨仓消息

来自 `acme/service-a`（2026-04-18，bug-report，warning，截止 2026-04-25）：
> GET /api/users 对缺失 ID 返回空数组而非 404
>
> **问题：** 调用 `GET /api/users?id=nonexistent-id` 时，接口返回
> `200 OK` 并携带空数组 `[]`，而非 `404 Not Found`...

→ 确认收到：`engram inbox acknowledge acme/service-a:20260418-103000:7f3a`
→ 修复后解决：`engram inbox resolve acme/service-a:20260418-103000:7f3a --note='...' --commit=<sha>`
→ 拒绝：`engram inbox reject acme/service-a:20260418-103000:7f3a --reason='...'`
```

4. **会话中操作。** LLM 可在会话的任何时刻通过 MCP 工具（§5.5.6）或 CLI 调用 `engram_inbox_acknowledge`、`engram_inbox_resolve` 或 `engram_inbox_reject`。
5. **会话结束扫描。** `engram context pack --close` 为会话期间发生转换的所有消息发出反向通知事件，使发件方在下次 `engram review` 时看到更新。

**`engram status` 中的收件箱。** `engram status` 始终显示单行摘要：`收件箱：2 条待处理（1 条 warning，1 条 info）`。状态输出中不嵌入消息正文；完整列表通过 `engram inbox list` 获取。

---

#### 5.5.6 MCP 工具接口

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
    列出收件箱消息。只读。返回适合 LLM 使用的结构化字典。
    过滤条件：status（pending/acknowledged/resolved/rejected/all）、to_repo、from_repo、intent。
    排序：严重性降序、截止日期升序、创建时间升序。
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
    发送跨仓收件箱消息。返回 message_id。
    执行去重（§5.5.3）和限速（§5.5.4）。
    intent: bug-report | api-change | question | update-notify | task
    severity: info | warning | critical
    """

@mcp.tool()
def engram_inbox_acknowledge(message_id: str) -> None:
    """将 pending 转换为 acknowledged。记录 acknowledged_at 时间戳。"""

@mcp.tool()
def engram_inbox_resolve(
    message_id: str,
    note: str,
    commit_sha: str | None = None,
) -> None:
    """
    转换为 resolved。记录 resolved_at、resolution_note、可选的 commit_sha。
    向 inter_repo.jsonl 发出 message_resolved 事件；发件方在下次 engram review 时可见。
    """

@mcp.tool()
def engram_inbox_reject(
    message_id: str,
    reason: str,
) -> None:
    """转换为 rejected。记录 rejected_at 和 rejection_reason。"""
```

所有工具在 MCP 服务器启动序列（§4 工具注册）中注册，对任何激活了 engram MCP 服务器的 LLM 会话均可用。

---

#### 5.5.7 Web UI 数据源

Web UI `/inbox` 页面专门从 `graph.db inbox_messages` 读取。这是文件系统状态的去范式化视图，由每次 `send()` / `transition()` 调用同步维护，由监听守护进程异步维护。

**实时更新。** 监听守护进程在每次收件箱状态变更时发出 SSE 事件；Web UI `/inbox` 页面订阅后无需完整刷新即可重新获取受影响的行。

**过滤与排序。** UI 支持按状态、意图、严重性、from_repo、to_repo、截止日期范围过滤。默认排序：严重性降序 → 截止日期升序 → 创建时间升序（与 SPEC §10.3 优先级顺序一致）。

**graph.db 表结构：**

```sql
CREATE TABLE inbox_messages (
    message_id        TEXT PRIMARY KEY,
    from_repo         TEXT NOT NULL,
    to_repo           TEXT NOT NULL,
    intent            TEXT NOT NULL,
    severity          TEXT NOT NULL DEFAULT 'info',
    status            TEXT NOT NULL DEFAULT 'pending',
    created           TEXT NOT NULL,
    deadline          TEXT,
    dedup_hash        TEXT,
    duplicate_count   INTEGER NOT NULL DEFAULT 0,
    acknowledged_at   TEXT,
    resolved_at       TEXT,
    resolution_note   TEXT,
    resolution_commit TEXT,
    rejected_at       TEXT,
    rejection_reason  TEXT,
    file_path         TEXT NOT NULL
);

CREATE INDEX idx_inbox_to_status     ON inbox_messages(to_repo, status);
CREATE INDEX idx_inbox_from_status   ON inbox_messages(from_repo, status);
CREATE INDEX idx_inbox_dedup         ON inbox_messages(to_repo, status, dedup_hash);
```

---

### 5.6 智慧指标

#### 5.6.0 职责

智慧指标追踪四条定量时间序列曲线，衡量 engram 是否随时间推移让 LLM 变得可量化地更智慧。这是 engram 的第五支柱（见 README）：不仅仅是"我存储记忆"，而是"我能证明我在进步"。每条曲线都是存储在 `graph.db metrics_wisdom` 中的时间序列；Web UI 在仪表板上以迷你图（sparkline）形式展示，在 `/wisdom` 页面以完整图表展示；CLI 通过 `engram wisdom report` 暴露。

四条曲线：

| 曲线 | 衡量内容 | 健康信号 |
|---|---|---|
| **工作流掌握度** | 工作流在自学习轮次间的逐步提升 | 单调上升 = 系统在学习；平坦/低值 = 工作流停滞 |
| **任务复现效率** | 相似任务随时间推移的成本比 | 趋向 <1.0 = 处理更快（改进）；>1.0 = 退化 |
| **记忆整理比率** | 活跃记忆与已弃用/归档记忆的占比 | ~85–95% 活跃为健康；>20% 已弃用 = 审查积压 |
| **上下文效率** | 每次会话的预算利用率 × 任务成功率 | 趋势上升 = 相关性闸门改进中；下降 = 退化 |

智慧指标使第五支柱可证伪：若曲线未朝健康方向趋进，说明系统没有变得更智慧，运维人员应介入调查。

---

#### 5.6.1 四条曲线

**曲线 1：工作流掌握度**

- **定义。** 对于每个工作流 `W`，第 `r` 轮自学习的值为：`success_rate(W, r) × 0.5 + normalize(primary_metric_Δ(W, r)) × 0.5`。两个分量权重相等，因此工作流可通过稳定通过运行或通过展示可量化的主指标提升来得分。
- **数据来源。** `workflows/<name>/journal/evolution.tsv`（每轮行）+ `workflows/<name>/runs.jsonl`（每次运行通过/失败）。
- **单位。** 0–100 指数；时间轴 = 自学习轮次编号（非日历时间）。
- **健康信号：**

  | 信号 | 解读 |
  |---|---|
  | 5 轮以上单调上升 | 系统正在学习此工作流。正常且理想。 |
  | 平坦且值 < 50 | 工作流停滞。可能原因：夹具过严、提议器预算过低或工作流范围过宽。 |
  | 振荡 ±10 点以上 | 夹具噪声或主指标非确定性。检查夹具设计。 |
  | 单次急剧下跌 | 可能因错误接受引起退化。检查该轮接受的版本是否引入了范围变更。 |

**曲线 2：任务复现效率**

- **定义。** 对于会话对 `(s_new, s_old)`，若任务文本余弦相似度 ≥ 0.85，计算 `ratio = cost(s_new) / cost(s_old)`，其中 `cost = tokens_used × session_duration_seconds`。周桶 = 该周内所有此类对的中位比。
- **数据来源。** `~/.engram/journal/usage.jsonl`（每次会话的 token 数）+ 会话元数据（任务文本、时长）。相似度使用与相关性闸门（§5.1）相同的嵌入模型计算。
- **单位。** 比率（无量纲）；1.0 = 无变化；< 1.0 = 更便宜（改进）；> 1.0 = 更昂贵（退化）。时间轴 = ISO 周（UTC 周一至周日桶）。
- **最小样本量。** 若某周内找到的复现任务对 < 5 对，则该桶不绘制；图表上显示空心标记以表示置信度低。
- **健康信号：**

  | 信号 | 解读 |
  |---|---|
  | 数月内趋向 0.8–0.9 | 系统在保留上下文；LLM 减少了重复工作。健康。 |
  | 平坦在 1.0 附近 | 无复现收益；可能没有重复任务，或记忆未被加载。检查相关性闸门得分。 |
  | 连续 3 周以上比率 > 1.0 | 退化。记忆存储可能过大导致上下文质量下降。运行 `engram wisdom report --curve=task_recurrence` 获取详情。 |

**曲线 3：记忆整理比率**

- **定义。** `active_ratio = count(lifecycle_state='active') / count(*)` 跨 `graph.db assets` 中所有记忆资产。补充比率：`deprecated_ratio`、`archived_ratio`。渲染为堆叠面积图（活跃 + 已弃用 + 已归档 = 100%）。
- **数据来源。** `graph.db assets` 表的 `lifecycle_state` 列。每次 `aggregate_hourly()` 运行结束时对快照进行采样，存储为周桶（ISO 周边界）。
- **单位。** 百分比；时间轴 = 日历周。
- **健康目标范围：**

  | 状态 | 健康 | 警告 | 严重 |
  |---|---|---|---|
  | 活跃 | 85–95% | 70–84% | < 70% |
  | 已弃用 | 3–10% | 11–20% | > 20% |
  | 已归档 | 2–5% | 6–10% | > 10% |

- **健康信号：** 已弃用 > 20% 说明审查积压增长速度超过了运维人员处理速度——运行 `engram review` 处理待处理的一致性提案。活跃 < 70% 可能表明演化扫描过于激进；检查 `[evolve].proposals_per_cadence_max`。

**曲线 4：上下文效率**

- **定义。** 对于每次会话 `s`，`efficiency(s) = (tokens_packed / context_budget) × task_success_indicator(s)`。`task_success_indicator` 在会话以显式成功事件（`engram status --complete`）结束时为 1.0，无显式结果时为 0.5，记录了错误事件时为 0.0。滚动 7 会话平均值为绘制值。
- **数据来源。** `engram context pack` 调用日志（打包的 token 数、使用的预算）+ 会话结果事件，均写入 `~/.engram/journal/sessions.jsonl`。
- **单位。** 效率指数 0–1；时间轴 = 每会话索引（滚动平均）。
- **健康信号：**

  | 信号 | 解读 |
  |---|---|
  | 指数趋向 0.8–0.9 | 相关性闸门选择良好；预算主要被相关内容占用且带来成功。 |
  | 低且平坦（< 0.4） | 预算过小（tokens_packed / budget 低）或过多会话失败（成功因子低）。 |
  | 周环比下降 > 15% | 退化。可能表明记忆存储已过时或相关性闸门阈值漂移。 |

---

#### 5.6.2 数据模型

`graph.db` 中的新表：

```sql
CREATE TABLE metrics_wisdom (
    curve            TEXT    NOT NULL,   -- workflow_mastery | task_recurrence | memory_curation | context_efficiency
    scope            TEXT,               -- 可选：工作流名称、仓库路径等。NULL = 全局
    bucket_start     TEXT    NOT NULL,   -- ISO 8601 桶边界（周开始、轮次开始等）
    bucket_duration  TEXT    NOT NULL,   -- 'weekly' | 'per_round' | 'per_session'
    value            REAL    NOT NULL,
    sample_count     INTEGER,            -- 此桶内的数据点数量
    metadata         TEXT,               -- 曲线专属附加字段的 JSON blob（如 accepted_rounds、p50_ratio）
    PRIMARY KEY (curve, scope, bucket_start)
);

CREATE INDEX idx_metrics_curve_time  ON metrics_wisdom(curve, bucket_start DESC);
CREATE INDEX idx_metrics_scope       ON metrics_wisdom(curve, scope, bucket_start DESC);

-- check_health_signal() 生成的退化警报
CREATE TABLE metrics_wisdom_alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    curve            TEXT    NOT NULL,
    scope            TEXT,
    detected_at      TEXT    NOT NULL,
    alert_class      TEXT    NOT NULL,   -- wisdom-regression-mastery | wisdom-regression-recurrence 等
    detail           TEXT    NOT NULL,   -- 退化的人类可读描述
    proposal_id      TEXT,               -- FK → consistency_proposals.id（生成后填充）
    resolved         INTEGER NOT NULL DEFAULT 0
);
```

**聚合流水线。** 由守护进程每小时运行（可通过 `[wisdom].aggregate_interval` 配置）：

```python
def aggregate_hourly():
    # 每个子聚合器是幂等的：对同一桶重复运行时
    # 执行 INSERT OR REPLACE 而非创建重复行。
    aggregate_workflow_mastery()     # 扫描所有工作流的 evolution.tsv + runs.jsonl
    aggregate_task_recurrence()      # 扫描 usage.jsonl + 余弦相似度比较
    aggregate_memory_curation()      # 按 lifecycle_state 统计资产数量
    aggregate_context_efficiency()   # 扫描 sessions.jsonl 中的 pack 调用 + 结果

    # 退化检测（§5.6.5）——在聚合后运行
    for curve in ('workflow_mastery', 'task_recurrence', 'memory_curation', 'context_efficiency'):
        for scope in get_active_scopes(curve):
            check_health_signal(curve, scope)
```

`aggregate_workflow_mastery()` 遍历每个 `~/.engram/workflows/*/journal/evolution.tsv`，计算每轮指数，写入 `scope=<workflow-name>`、`bucket_duration='per_round'` 的行。`aggregate_memory_curation()` 运行单条 `SELECT lifecycle_state, COUNT(*) FROM assets GROUP BY lifecycle_state`，写入单条 `scope=NULL` 的行。

---

#### 5.6.3 CLI `engram wisdom report`

```
$ engram wisdom report --since=30d

工作流掌握度（30 天，按自学习轮次）
  release-checklist       ▁▂▃▅▆▇██  指数 72 → 94  (+22，自 2026-03-18)
  pr-review               ▅▅▆▅▆▇▇▇  指数 51 → 59  (+8)
  dep-upgrade             ▂▃▅▄▅▆▇▇  指数 31 → 72  (+41)

任务复现效率（周桶，最近 8 周）
  比率（中位数）：  1.00 → 0.82  （相似任务成本降低 18%）
  每周样本数：      47 → 134 对复现任务

记忆整理比率（当前快照）
  活跃：      487  (89.7%)  ██████████████████░░
  已弃用：     38  (7.0%)   ████░░░░░░░░░░░░░░░░
  已归档：     18  (3.3%)   ██░░░░░░░░░░░░░░░░░░
  [所有比率均在健康范围内]

上下文效率（滚动 7 会话均值，最近 30 天）
  指数：    0.71 → 0.84  (+0.13)
  趋势：    ▂▃▄▅▅▆▇▇  （上升中）

✓ 全部 4 条曲线趋势良好。未检测到退化。
```

**选项：**

| 选项 | 说明 |
|---|---|
| `--since=<时长>` | 时间窗口：`7d`、`30d`、`90d`、`1y`（默认 `30d`） |
| `--curve=<名称>` | 仅显示一条曲线：`workflow_mastery`、`task_recurrence`、`memory_curation`、`context_efficiency` |
| `--scope=<名称>` | 过滤到特定工作流或仓库路径 |
| `--json` | 输出 JSON 格式（结构化，可通过 MCP 被 LLM 使用） |
| `--web-url` | 打印 `/wisdom` Web UI 页面的 URL 而非终端输出 |

所有曲线健康时退出码为 0，任何退化警报激活时为 1。

---

#### 5.6.4 Web UI 集成

`/wisdom` 页面是主要可视化界面：

- **四张图表**（每条曲线一张），带时间范围选择器：`7d` / `30d` / `90d` / `1y`。图表以折线图渲染，健康范围以绿色阴影标出。
- **工作流掌握度下钻。** 点击掌握度图表中的工作流名称，打开每工作流面板，显示每轮自学习信息：版本标签、主指标值、已接受/已拒绝、提议器 token 数。这是 evolution.tsv 数据的可视化渲染。
- **任务复现散点图。** 悬停在某周的桶上，显示样本量和比率的 p25/p50/p75 分布，使运维人员能区分噪声与信号。
- **退化横幅。** 任何曲线有激活中的退化警报（`metrics_wisdom_alerts.resolved = 0`）时，所有页面顶部（不仅仅是 `/wisdom`）显示红色横幅：`"检测到智慧退化：上下文效率本周下降 17%——运行 engram wisdom report"`。
- **导出。** 每张图表有"下载 CSV"按钮，返回该曲线的原始 `metrics_wisdom` 行为 CSV 文件。
- **实时更新。** `/wisdom` 页面订阅 SSE 流。`aggregate_hourly()` 写入新行时发出 `metrics_updated` SSE 事件，图表无需完整页面刷新即可重新渲染。

---

#### 5.6.5 退化检测

自动健康检查在每次 `aggregate_hourly()` 调用结束时运行。每项检查将最新的完整桶与前一个桶（或滚动基准）进行比较。阈值被突破时：

1. 向 `metrics_wisdom_alerts` 插入一行。
2. 向 `consistency.jsonl` 发出对应 `wisdom-regression-*` 类的一致性提案。
3. 提案与记忆和一致性提案一起出现在 `engram review` 中。

**退化阈值：**

| 曲线 | 触发条件 | 警报类别 |
|---|---|---|
| 工作流掌握度 | 任一工作流的指数周环比下降 > 10 点 | `wisdom-regression-mastery` |
| 任务复现效率 | 中位比率连续 3 周以上超过 1.0 | `wisdom-regression-recurrence` |
| 记忆整理比率 | `deprecated_ratio` 超过 20% | `wisdom-regression-curation` |
| 上下文效率 | 滚动 7 会话指数相对前 7 会话窗口下降 > 15% | `wisdom-regression-context` |

**解决方式。** 退化提案与一致性引擎提案接受同样的六种解决操作（§5.2.5）：`update`、`supersede`、`merge`、`archive`、`dismiss`、`escalate`。最常见的解决方式是：在运维人员调查并确认退化已被理解后（如工作流夹具集暂时为空），执行 `dismiss`；或在记录了纠正措施后执行 `update`。与所有提案一样，退化警报**绝不**自动解决——需要运维人员显式确认。

**警报去重。** 若同一曲线 + scope 组合已有未解决的开放警报，则不为同一退化插入新警报。只有当一条曲线从之前的健康状态再次进入退化区间时，才发出新警报。

---

#### 5.6.6 MCP 工具与 Python SDK

```python
@mcp.tool()
def engram_wisdom_report(
    since: str = '30d',
    curve: str | None = None,
    scope: str | None = None,
) -> dict:
    """
    以结构化数据返回智慧指标。适合 LLM 使用。
    返回：{ curves: { <name>: { buckets: [...], health: 'ok'|'warning'|'regression', alerts: [...] } } }
    """
```

**Python SDK：**

```python
from engram import wisdom

# 完整报告
report = wisdom.report(since='30d')
print(report.to_sparklines())         # 终端迷你图渲染（与 CLI 相同）
print(report.to_dict())               # 用于程序化使用的结构化字典

# 单条曲线
mastery = wisdom.report(since='90d', curve='workflow_mastery', scope='release-checklist')
print(mastery.health)                 # 'ok' | 'warning' | 'regression'
for bucket in mastery.buckets:
    print(bucket.round_tag, bucket.value, bucket.accepted)

# 检查活跃退化
alerts = wisdom.active_alerts()
for a in alerts:
    print(a.curve, a.alert_class, a.detected_at, a.detail)
```

---

---

## 6. 第 4 层 — 接入层

### 6.0 概述

第 4 层定义 LLM 和智能体如何与存储交互。四条接入路径可共存；用户或工具根据运行时场景选择最合适的一条。所有路径读取同一个 `.memory/` 目录，通过同一套第 2 层 CLI 原语写入。它们的区别仅在于传输方式。

#### 6.0.1 接入路径对照表

| LLM / 智能体类型 | 最佳接入路径 | 原因 |
|---|---|---|
| Claude Code / Codex / Gemini CLI / Cursor | 适配器（`CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.cursor/rules`） | 工具原生配置文件，启动时自动加载，无额外配置开销 |
| Claude Desktop / Zed / 任意 MCP 客户端 | MCP 服务 | 原生 MCP 协议，带类型的工具模式，实时读取 |
| Ollama / llama.cpp / 任意本地小模型 | 提示包 | 一次性 system prompt 注入；离线可用；无需服务进程 |
| 自定义 Python 智能体 | Python SDK | 进程内库，细粒度控制，无子进程开销 |
| 自定义 TypeScript / Node 智能体 | TypeScript SDK | `@engram/sdk` npm 包；与 Python SDK API 形态一致 |
| 其他——脚本、临时工具、CI 流水线 | CLI + Shell 胶水 | `engram context pack` 可通过管道接入任何支持 stdin 的工具 |

**共享状态。** 所有路径读取同一个 `.memory/` 目录，通过 `engram memory add`、`engram workflow run`、`engram inbox send` 等 CLI 原语写入。并发写入通过文件锁串行化（§3.8）。没有任何路径拥有其他路径不具备的特权存储访问权限。

**对第 3 层的依赖。** 当相关性闸门启用时，`engram context pack` 和 MCP `engram_context_pack` 工具均通过相关性闸门进行候选排序。当相关性闸门禁用时，两者均退回到确定性的 scope/enforcement 排序。接入路径从不直接调用一致性引擎、自学习引擎或演化引擎；这些组件通过 `engram consistency scan`、`engram workflow autolearn`、`engram memory evolve` 单独触发。

---

### 6.1 适配器

适配器是单文件提示模板，在 `engram init` 时或通过 `engram adapter <tool>` 按需生成。它将 LLM 工具指向 `.memory/` 并提供最小行为契约：启动时加载记忆、遵循 METHODOLOGY.md、会话结束时汇报。

#### 6.1.1 五种适配器文件

| 工具 | 文件路径 | 说明 |
|---|---|---|
| Claude Code | `CLAUDE.md` | Claude Code 每次会话启动时自动加载 |
| Codex | `AGENTS.md` | OpenAI Codex 标准配置文件 |
| Gemini CLI | `GEMINI.md` | Google Gemini CLI 标准配置文件 |
| Cursor | `.cursor/rules` | Cursor IDE rules 目录 |
| 原始 API / 自定义 | `system_prompt.txt` | 纯文本；可粘贴或通过程序注入 |

所有五个适配器均由 `adapters/<tool>/template.md` 中的版本化模板生成（随 `engram-cli` 发布）。模板以项目的 `.memory/` 路径、用户的 scope 配置和当前 SPEC 版本为参数进行渲染。

#### 6.1.2 标记分区结构

每个适配器文件使用标记分区布局，使 `engram adapter --regenerate` 能在不覆盖用户自定义内容的情况下更新托管区：

```markdown
<!-- engram:begin v0.2 -->
<!-- 本节由 `engram adapter` 托管。此处的编辑在重新生成时将被覆盖。-->

## engram 记忆 — 会话契约

**启动时读取 `.memory/MEMORY.md`。遵循 `METHODOLOGY.md`。**

记忆位置：`.memory/`
规范：`SPEC.md`
术语表：`docs/glossary.md`
方法论：`METHODOLOGY.md`

### 会话开始
执行 `engram context pack --task="<当前任务>" --budget=6000` 并将输出加入上下文。

### 会话结束
执行 `engram context pack --close` 以记录会话结果并触发智慧指标更新。

### 预算提示
L1 唤醒（mandatory + default 记忆，不含项目上下文）保持在 ≤900 tokens。

<!-- engram:end v0.2 -->

# 以下为用户自定义内容，重新生成时将保留。
```

用户可编辑区（`<!-- engram:end v0.2 -->` 之后的所有内容）在重新生成前被提取，并在生成后原样追加。若现有文件中未找到 `engram:begin` / `engram:end` 标记，`engram adapter --regenerate` 将报错并退出，不进行任何写入；绝不静默覆盖无法识别的文件。

#### 6.1.3 托管区内容

engram 托管区始终包含：

1. **任务一行。** "启动时读取 `.memory/MEMORY.md`。遵循 METHODOLOGY.md。"
2. **文件位置。** `.memory/`、`SPEC.md`、`docs/glossary.md`、`METHODOLOGY.md` 的相对路径。
3. **生命周期钩子。** 会话开始：`engram context pack`；会话结束：`engram context pack --close`。
4. **工具特定钩子引用。** Claude Code：引用 `adapters/claude-code/hooks/`（PreCompact 和 Stop 钩子）。其他工具：对应的钩子文件位置（如存在）。
5. **预算提示。** L1 唤醒提示的 token 上限（默认 900 tokens；可在 `.memory/config.toml` 的 `[access.adapter]` 中配置）。

#### 6.1.4 重新生成算法

```python
def regenerate_adapter(tool: str, project_root: Path) -> None:
    adapter_path = adapter_file(tool, project_root)
    current = read_adapter_file(adapter_path)          # 首次运行时可能为空
    user_section = extract_user_section(current)       # engram:end 标记之后的文本
    new_managed = render_managed_template(tool, project_root)  # engram:begin..engram:end 块
    if current and BEGIN_MARKER not in current:
        raise AdapterMarkerNotFound(
            f"{adapter_path}: 未找到 engram:begin 标记。"
            "请在重新生成前重命名或删除该文件。"
        )
    write_atomic(adapter_path, new_managed + '\n' + user_section)
```

`write_atomic` 先写入 `.tmp` 文件再原子重命名，防止部分写入导致适配器状态不一致。

#### 6.1.5 调用方式

```bash
# 为本项目生成所有适配器（engram init 时执行）
engram adapter --all

# 生成或重新生成特定适配器
engram adapter claude-code
engram adapter claude-code --regenerate

# 列出可用适配器类型
engram adapter --list

# 重新生成前查看 diff
engram adapter claude-code --dry-run
```

---

### 6.2 MCP 服务

MCP 服务将完整的 engram 存储以一组带类型工具的形式暴露给任何兼容 MCP 协议的客户端：Claude Desktop、Zed、带工具使用的 Claude API，或任何自定义 MCP 客户端。

通过 `engram mcp serve [--transport=stdio|sse] [--port=N]` 启动。

#### 6.2.1 设计原则

**请求级无状态。** 每次工具调用均重新从文件系统读取（`graph.db` 作为性能索引缓存）。两个并发会话读取同一个记忆目录时，读工具 MUST 返回相同结果。无进程内会话状态。

**性能预算。** 每次工具调用 MUST 在 p95 < 300ms 内完成（§20 术语表）。MCP 服务冷启动 MUST 在 500ms 内完成。以上预算针对本地文件系统；网络挂载文件系统不在范围之内。

**审计追踪。** 每次工具调用（读写均包含）向 `~/.engram/journal/<date>.jsonl` 追加一条结构化事件，包含工具名称、输入参数（敏感信息已脱敏）、时间戳、耗时和结果。

**写入串行化。** 写工具在修改资产前获取文件锁（§3.8）。来自不同 MCP 会话的并发写入调用可正确串行化，不会死锁。

#### 6.2.2 读工具

```python
@mcp.tool()
def engram_search(
    query: str,
    scope: str = 'visible',   # 'visible' | 'project' | 'user' | 'team' | 'org' | 'pool:<name>'
    top_k: int = 10,
) -> list[dict]:
    """语义 + BM25 混合搜索 scope 内所有资产。返回排序后的资产摘要列表。"""

@mcp.tool()
def engram_read(asset_id: str) -> dict:
    """按 asset_id 返回单个资产的完整内容和 frontmatter。"""

@mcp.tool()
def engram_list(
    scope: str | None = None,
    subtype: str | None = None,   # 'user' | 'feedback' | 'project' | 'reference' | 'workflow_ptr' | 'agent'
) -> list[dict]:
    """返回资产清单，可按 scope 和 subtype 过滤。"""

@mcp.tool()
def engram_context_pack(
    task: str,
    budget_tokens: int = 6000,
) -> str:
    """在 token 预算内为给定任务组装并返回打包的 system prompt。"""

@mcp.tool()
def engram_wisdom_report(
    since: str = '30d',
    curve: str | None = None,
) -> dict:
    """以结构化数据返回智慧指标。曲线名称和模式见 §5.6。"""
```

#### 6.2.3 写工具 — 资产

```python
@mcp.tool()
def engram_memory_add(
    subtype: str,                 # 'user' | 'feedback' | 'project' | 'reference' | 'agent'
    scope: str,                   # 'user' | 'project' | 'team' | 'org' | 'pool:<name>'
    body: str,
    frontmatter_extras: dict = {},
) -> dict:
    """创建新的 Memory 资产。返回新 asset_id 和文件路径。"""

@mcp.tool()
def engram_memory_update(
    asset_id: str,
    **fields,
) -> dict:
    """编辑现有 Memory 资产。不可变字段（asset_id、created_at）将被拒绝。"""

@mcp.tool()
def engram_memory_validate_use(
    asset_id: str,
    outcome: str,   # 'helpful' | 'neutral' | 'harmful'
) -> dict:
    """为记忆记录置信度信号。输入智慧指标的整理比率曲线。"""
```

#### 6.2.4 写工具 — 工作流与知识库

```python
@mcp.tool()
def engram_workflow_run(
    name: str,
    inputs: dict = {},
) -> dict:
    """调用命名工作流 spine。返回包含退出码和输出的结构化结果。"""

@mcp.tool()
def engram_kb_read(
    topic: str,
    chapter: str | None = None,
) -> str:
    """返回知识库文章内容（编译摘要）。指定 chapter 可返回子章节。"""
```

#### 6.2.5 收件箱工具

```python
@mcp.tool()
def engram_inbox_list(
    status: str = 'pending',     # 'pending' | 'acknowledged' | 'resolved' | 'all'
    to_repo: str | None = None,
) -> list[dict]:
    """列出本仓库的 inbox 消息，按 status 过滤，可选按目标仓库过滤。"""

@mcp.tool()
def engram_inbox_send(
    to_repo: str,
    intent: str,       # 'bug-report' | 'api-change' | 'dependency-update' | 'question' | 'info'
    severity: str,     # 'info' | 'warning' | 'critical'
    message: str,
    **kwargs,          # 可选：related_code_refs, related_asset_ids, expires_at
) -> dict:
    """向另一个仓库的 inbox 发送点对点消息。返回 message_id。"""

@mcp.tool()
def engram_inbox_acknowledge(message_id: str) -> dict:
    """将消息标记为已确认（已读但尚未解决）。"""

@mcp.tool()
def engram_inbox_resolve(
    message_id: str,
    note: str,
    commit_sha: str | None = None,
) -> dict:
    """将消息标记为已解决，附带解决说明和可选 commit 引用。"""
```

#### 6.2.6 一致性工具（对 LLM 只读）

```python
@mcp.tool()
def engram_review() -> dict:
    """返回聚合的待处理项：一致性 proposal、inbox 待处理、退化警报。"""

@mcp.tool()
def engram_consistency_list(status: str = 'open') -> list[dict]:
    """按状态列出一致性引擎 proposal：'open' | 'resolved' | 'dismissed' | 'all'。"""
```

这些工具仅供 LLM 查看一致性信息。解决 proposal（接受、忽略、上报）通过 CLI（`engram consistency resolve <id>`）操作，以保持人工决策环路，与 §2.3 不变式（一致性引擎只提议、从不自动 mutate）保持一致。

---

### 6.3 提示包

`engram context pack` 生成单文件文本提示，适用于任何无法运行子进程或连接 MCP 服务的工具。

#### 6.3.1 使用场景

- Ollama / llama.cpp / 任何接受 system prompt 字符串的模型。
- 无网络连接的离线或气隙环境。
- 小上下文模型（4k–8k tokens），每个 token 都弥足珍贵。
- 快速实验、调试以及检查上下文加载内容的 CI 流水线。

#### 6.3.2 命令形式

```bash
engram context pack \
  --task="为认证服务添加 OAuth2 支持" \
  --budget=4000 \
  [--model=qwen2.5-7b] \
  [--output=prompt.txt] \
  [--format=markdown|json|plain]
```

`--model` 是预算分配的提示（较大模型获得更丰富的工作流片段）。`--format=json` 输出结构化数据供程序消费。`--output` 写入文件；省略则打印到 stdout。

#### 6.3.3 输出结构

各节按优先级顺序输出，并通过相关性闸门（§5.1）进行预算过滤。每个包含的资产均标注估算 token 数。末行显示已用 token 总量。

```markdown
# engram context (v0.2)

## 与你对话的用户
<用户 scope 记忆，按相关性 × scope 权重取 top-K>

## 你必须遵守的规则
<先列 mandatory 记忆，再列 default enforcement 记忆>

## 当前项目状态
<按与任务相关性排序的 project scope 记忆>

## 相关工作流
<workflow_ptr 条目及简短描述；完整工作流位于 .memory/workflows/<name>/>

## 知识库参考
<相关知识库文章的 _compiled.md 片段>

## 待处理的跨仓消息
<本仓库待处理的 inbox 消息>

## 任务
为认证服务添加 OAuth2 支持

---
# Total: 3847 / 4000 tokens
```

**预算强制执行。** 若仅 mandatory 记忆就超出预算，提示包将完整输出这些记忆并附加 `# WARNING: mandatory memories exceed budget` 标头。default 和 hint 记忆随后省略。LLM 收到的提示虽然密集但有效。

**节顺序的依据。** Mandatory 规则在项目上下文之前加载，因为 mandatory 记忆代表权威约束，不能静默缺席。项目状态紧随其后，因为它与任务相关但不具权威性。工作流和知识库条目最后，因为它们是召回成本较低的参考资料。

#### 6.3.4 管道用法

```bash
# 通过管道传给 Ollama
cat <(engram context pack --task="为认证服务添加 OAuth2 支持") my-task.md \
  | ollama run qwen2.5:7b

# 写入文件供重复使用
engram context pack --task="为认证服务添加 OAuth2 支持" --output=.context.md

# JSON 输出供脚本使用
engram context pack --task="..." --format=json | jq '.sections[].token_count'
```

---

### 6.4 Python SDK

`pip install engram` → `import engram`。

Python SDK 是进程内库，可封装 MCP 服务协议（远程场景）或直接访问文件系统（本地项目）。它以 Pythonic 形式暴露与 MCP 工具相同的接口。

#### 6.4.1 Context 与会话 API

```python
from engram import Context, memory, workflow, inbox, consistency, wisdom

# Context 自动继承 ~/.engram 配置并检测项目 cwd
ctx = Context()

# 显式指定项目路径和 scope
ctx = Context(project_root='/home/user/myproject', scope='team')
```

#### 6.4.2 读操作

```python
# 语义 + BM25 搜索
memories = ctx.memory.search('payment gateway', top_k=10)
for m in memories:
    print(m.asset_id, m.name, m.score)

# 完整资产读取
asset = ctx.memory.read('mem-20260418-abc123')

# 资产清单
all_memories = ctx.memory.list(scope='project', subtype='feedback')

# 知识库文章
article = ctx.kb.read('platform-arch')
chapter = ctx.kb.read('platform-arch', chapter='data-model')

# 打包上下文提示
system_prompt = ctx.context_pack(task='修复登录 bug', budget_tokens=4000)
```

#### 6.4.3 写操作

```python
# 创建记忆
new_id = ctx.memory.add(
    subtype='feedback',
    scope='project',
    name='合并前先 rebase',
    body='开 PR 前始终将特性分支 rebase 到 main。',
    enforcement='default',
)

# 编辑记忆
ctx.memory.update(new_id, body='始终 rebase 到 main；压缩 fixup commits。')

# 记录使用结果
ctx.memory.validate_use(new_id, outcome='helpful')
```

#### 6.4.4 工作流与收件箱

```python
# 调用工作流
result = ctx.workflow.run('release-checklist', inputs={'version': '1.2.0'})
print(result.exit_code, result.output)

# 发送跨仓消息
msg_id = ctx.inbox.send(
    to_repo='acme/service-b',
    intent='bug-report',
    severity='warning',
    message='当 email 包含加号时，/users 端点返回 500。',
    related_code_refs=['src/api/users.py:L42@abc123'],
)

# 列出并解决 inbox 消息
for msg in ctx.inbox.list(status='pending'):
    print(msg.message_id, msg.intent, msg.severity, msg.message)

ctx.inbox.resolve(msg_id, note='已在 commit abc456 中修复。', commit_sha='abc456')
```

#### 6.4.5 一致性与智慧指标

```python
# 查看待处理项
review = ctx.review()
print(f"{len(review.proposals)} 个开放 proposal，{len(review.inbox_pending)} 条待处理消息")

# 列出一致性 proposal
for proposal in ctx.consistency.list_open():
    print(proposal.proposal_id, proposal.conflict_class, proposal.summary)

# 智慧指标
report = ctx.wisdom.report(since='30d')
print(report.to_sparklines())
```

#### 6.4.6 错误分类

`engram.errors` 定义了与 CLI 退出码一一对应的扁平错误层级：

| 异常类 | CLI 退出码 | 触发条件 |
|---|---|---|
| `engram.errors.ValidationError` | 2 | 资产 frontmatter 未通过 SPEC 验证 |
| `engram.errors.ScopeError` | 3 | 操作目标 scope 超出调用方写权限 |
| `engram.errors.NotFound` | 4 | asset_id 或工作流名称不存在 |
| `engram.errors.RateLimitError` | 5 | MCP 服务速率限制超出（远程模式） |
| `engram.errors.LockTimeout` | 6 | 文件锁未在超时时间内获取 |

所有 SDK 方法均从此层级抛出异常。调用方捕获 `engram.errors.EngramError` 即可统一处理所有 engram 异常。

---

### 6.5 TypeScript SDK

`npm install @engram/sdk`。TypeScript SDK 是 Python SDK 的镜像，面向 Node.js 智能体、浏览器工具以及 Deno/Bun 运行时。

#### 6.5.1 API 接口

```typescript
import { Context } from '@engram/sdk';

const ctx = new Context();
// 或显式指定选项：
const ctx = new Context({ projectRoot: '/home/user/myproject', scope: 'team' });

// 搜索
const memories = await ctx.memory.search('payment gateway', { topK: 10 });
for (const m of memories) {
  console.log(m.assetId, m.name, m.score);
}

// 打包上下文
const systemPrompt = await ctx.contextPack({
  task: '为认证服务添加 OAuth2 支持',
  budgetTokens: 4000,
});

// 运行工作流
const result = await ctx.workflow.run('release-checklist', { version: '1.2.0' });

// 收件箱
const msgId = await ctx.inbox.send({
  toRepo: 'acme/service-b',
  intent: 'bug-report',
  severity: 'warning',
  message: '当 email 包含加号时，/users 端点返回 500。',
  relatedCodeRefs: ['src/api/users.py:L42@abc123'],
});

// 一致性
const openProposals = await ctx.consistency.listOpen();
```

#### 6.5.2 运行时支持

| 运行时 | 状态 | 说明 |
|---|---|---|
| Node.js ≥18 | 支持 | 完整文件系统访问；推荐用于 CLI 智能体 |
| Bun | 支持 | 原生文件系统 I/O；冷启动更快 |
| Deno | 支持 | 需要 `--allow-read --allow-write --allow-run` |
| 浏览器 | 通过 WASM 的本地只读模式 | 只读；无子进程；仅支持提示包 |

浏览器 WASM 包内嵌提示模板和 JSON Schema，使 `ctx.contextPack()` 无需运行 `engram mcp serve` 进程即可工作。

#### 6.5.3 发布

以 `@engram/sdk` 发布到 npm，内置 TypeScript 类型定义。包中附带提示模板（`adapters/*/template.md`）和所有 MCP 工具输入的 JSON Schema，方便调用方在发送前验证输入。

---

### 6.6 多路径共存

同一项目可同时激活全部四条接入路径，互不冲突。

#### 6.6.1 并发示例

```
Claude Code 会话：   读取 CLAUDE.md（适配器）→ 通过 `engram context pack` 加载上下文
Codex 会话：         读取 AGENTS.md（适配器）→ 同一份上下文包
Claude Desktop：     连接 `engram mcp serve`（MCP 服务）→ 实时工具调用
Ollama qwen2.5:7b：  接收 `engram context pack` 的管道输出（提示包）
```

所有四条路径同时读取 `.memory/`。所有四条路径通过 CLI 原语（`engram memory add`、`engram workflow run`、`engram inbox send`）写入。文件锁（§3.8）串行化写入操作，任何会话都不会读到部分写入的资产。

#### 6.6.2 推荐配置

| 场景 | 主要路径 | 备用路径 |
|---|---|---|
| 开发者 IDE（Claude Code / Cursor / Zed） | 适配器或 MCP 服务 | 离线时使用提示包 |
| 本地自动化（Python 脚本、CI） | Python SDK | CLI + Shell 胶水 |
| TypeScript / Node 智能体 | TypeScript SDK | 通过 `child_process` 调用 CLI |
| 气隙 / 离线环境 | 提示包 | — |
| 多工具同时使用 | MCP 服务作为中枢 | 各 IDE 工具使用适配器 |

#### 6.6.3 写入一致性保证

无论哪条路径发起写入，以下条件均成立：

1. 每次写入均通过 `engram-cli` 原语（或通过委托给相同原语的 MCP 服务）进行。没有任何路径直接向 `.memory/` 写入未经 frontmatter 验证的裸文件。
2. 文件锁防止并发写入发生内容交织。
3. 每次写入均向 `~/.engram/journal/<date>.jsonl` 追加审计事件。
4. 一致性引擎（启用时）能感知所有路径产生的写入——因为它从第 1 层读取，而非从特定路径的日志读取。

---

## 7. 第 5 层 — 观测层（Web UI）

### 7.0 定位与技术选型

观测层是 engram 面向人类的界面。其目的是让人类以人类所需的方式查看 engram 存储——而非 LLM 所看到的方式。LLM 接收打包好的提示词；人类需要空间全局视图、逐层下钻、时间序列以及交互式控制。Web UI 通过 10 个页面提供以上能力，涵盖总览面板、知识图谱、资产详情（记忆、工作流、知识文章）、池管理、收件箱、项目总览、上下文预览、智慧曲线以及自学习控制台。

**使用 engram 不要求 Web UI。** 仅使用 CLI（第 1–4 层）即可实现完整功能并符合 SPEC 规范。Web UI 是可选附加组件，提供可观测性和运维工具。仅使用 CLI 的部署并非受损状态，只是缺少图形化视图。

**技术栈：**

| 层次 | 技术 | 备选方案 | 选型理由 |
|------|------|----------|----------|
| 后端 | Python + FastAPI | Node + Express | 与 CLI 共用 Python 运行时；异步 I/O；自动生成 OpenAPI 文档 |
| 前端 | Svelte + SvelteKit | React / Vue | 构建产物体积小，无虚拟 DOM 开销，编译期响应式 |
| 图表 | D3 + Observable Plot | Chart.js / Recharts | 可定制力导向图；轻量 |
| 图示 | Mermaid | D2 / PlantUML | 原生 Markdown；工作流状态图 |
| 编辑器 | CodeMirror 6 | Monaco | 更轻量；以 Markdown 为主 |
| 实时推送 | SSE（服务器发送事件） | WebSockets | 单向推送；开销更低；无握手复杂度 |
| 认证 | Basic auth + 本地绑定 | OAuth / JWT | 默认绑定 127.0.0.1；无需显式配置即无网络暴露 |

**启动方式：** `engram web serve [--port=8787] [--bind=127.0.0.1] [--auth=<user:pass>]`。通过 `engram web open` 在默认浏览器中打开。

---

### 7.1 10 页面地图

每个页面条目涵盖：用途、主要数据来源（graph.db 表或文件）、关键交互以及实时触发器。

#### /dashboard（总览面板）

- **用途：** 项目级全局概览——运维人员首先打开的页面。
- **数据：** 按类型/作用域/生命周期的资产计数；最近收件箱消息；待处理一致性提案；智慧曲线迷你图（最近 30 天，全部四条曲线）。
- **交互：** 点击任意计数 → 跳转至过滤后的 `/graph`；点击收件箱条目 → `/inbox/<msg-id>`；点击提案 → 一致性审查弹窗；点击迷你图 → `/wisdom`。
- **实时：** SSE 监听 `asset_changed`、`proposal_created`、`inbox_message` 事件——计数和迷你图无需刷新即可更新。

#### /graph（知识图谱）

- **用途：** 可视化资产图谱——资产为节点，引用关系为有向边。
- **数据：** `graph.db` 中的 `assets` 和 `references_` 表；作用域 + 子类型过滤器驱动 SQL WHERE 子句。
- **交互：** 平移/缩放（鼠标滚轮 + 拖拽）；点击节点 → 滑出详情面板；右键节点 → 跳转至 `/memory/<id>` 或 `/workflow/<name>`；过滤侧边栏（作用域、子类型、生命周期）；搜索框高亮匹配节点。
- **实时：** SSE 监听 `asset_changed`——无需重新布局即可在图中添加或更新节点/边。
- **技术说明：** ≤ 1000 个节点使用 D3 力导向布局；> 1000 个节点使用 WebGL（regl），不支持 WebGL 时降级为 SVG。

#### /memory/\<id\>（记忆详情）

- **用途：** 查看并编辑单个记忆资产。
- **数据：** 磁盘上的 `.memory/<scope>/<file>.md`（通过 `engram memory read <id>` 加载）；来自 `graph.db` 的入站引用。
- **交互：** frontmatter 编辑器（id、subtype、scope、lifecycle、tags、confidence 的结构化表单）；正文编辑器（CodeMirror 6，Markdown 模式）；保存按钮 → 触发 `engram memory update`；归档按钮 → 触发 `engram memory archive`；删除按钮（软删除——移至归档）。
- **实时：** SSE 监听该 asset-id 的 `asset_changed`——若 CLI 并发编辑，页面显示"文件已被外部修改——是否重新加载？"横幅。
- **"使用于"侧面板：** 按来源 asset-id 列出入站引用；来自 `journal/*.jsonl` 的最近 10 次包含该资产的上下文打包事件（LLM 使用记录）。

#### /workflow/\<name\>（工作流详情）

- **用途：** 工作流资产查看器与自学习控制面板。
- **数据：** `workflow.md`；`spine.md` 或 `spine.yaml`；fixture 文件；`metrics.yaml`；`evolution.tsv`；`rev/` 目录。
- **交互：** 标签页——概览 / 脊柱 / Fixtures / 指标 / 修订版本；自学习区域含启动 / 停止 / 继续按钮；修订版本标签页中每行显示差异查看器（脊柱变更的统一差异格式）以及接受/拒绝图标；指标图表（Observable Plot，展示各轮次 `confidence` 和 `pass_rate` 折线）。
- **实时：** SSE 监听 `autolearn_round` 事件——修订版本标签页追加新行；指标图表向右延伸。
- **修订版本图：** 水平时间线 `r0 → r1 → r2 → … → rN`，带接受/拒绝/当前状态图标。

#### /kb/\<topic\>（知识文章）

- **用途：** 知识文章阅读器与编辑器。
- **数据：** `README.md`（文章根目录）；各章节文件；`_compiled.md`（生成输出）；静态资产。
- **交互：** 目录侧边栏（从章节标题自动生成）；点击章节 → 在主面板加载；编辑模式切换 → 对应章节的 CodeMirror 编辑器；编译按钮 → 调用 `engram kb compile <topic>` 并刷新 `_compiled.md` 面板；左右对比视图（左侧源章节，右侧编译输出）。
- **实时：** SSE 监听 `kb/<topic>/` 下任意文件的 `asset_changed` → 显示"摘要已过期——是否重新编译？"横幅。

#### /inbox（收件箱）

- **用途：** 跨仓库消息中心。
- **数据：** `graph.db` 中的 `inbox_messages` 表；`~/.engram/inbox/<repo-id>/` 文件。
- **交互：** 过滤栏（status、intent、severity、to_repo、from_repo）；每条消息的操作——确认 / 解决 / 拒绝按钮（各调用对应的 `engram inbox` 命令）；发送新消息表单（to_repo、intent、severity、主题、正文）；线程视图（通过 `reply_to` 链接渲染为缩进对话）。
- **实时：** SSE 监听 `inbox_message` 事件——无需刷新即可出现新消息行；确认/解决时状态徽章实时更新。
- **可视化：** 消息线程通过 `reply_to` 关联；超过 3 条消息时默认折叠。

#### /pools（池管理）

- **用途：** 池订阅管理器。
- **数据：** `graph.db` 中的 `subscriptions`；`~/.engram/pools/*/`；池远端元数据。
- **交互：** 每个池的订阅/取消订阅开关；传播模式下拉菜单（`auto-sync` / `notify` / `pinned`）；修订版本固定器（模式为 `pinned` 时从 `rev/` 列表选择）；差异查看器（本地副本与最新池修订版本对比）；立即同步按钮。
- **实时：** SSE 监听 `pool_updated` 事件——相应池行出现"有新修订版本"徽章。
- **可视化：** 池依赖图——显示哪些池依赖哪些池（用于 org → team → project 传播链）。

#### /projects（项目总览）

- **用途：** 多项目总览——面向在同一台机器上管理多个 engram 项目的用户。
- **数据：** `~/.engram/projects.toml`；各项目的 `graph.db` 汇总统计。
- **交互：** 项目卡片网格，显示汇总统计（资产数量、待处理提案、未读收件箱、最新智慧采样）；切换活跃项目按钮；批量同步所有池按钮；在终端中打开按钮（在项目根目录打开终端）。
- **实时：** 每个项目的迷你图通过 SSE 更新（单一事件流跨所有项目复用）。

#### /context-preview（上下文预览——最关键的调试页面）

- **用途：** 在调用任何 LLM 之前，精确模拟 LLM 在给定任务描述下所能看到的内容。Web UI 中最重要的诊断页面。
- **数据：** `graph.db` + 缓存 + 实时相关性门调用（调用 `engram context pack --dry-run`）。
- **交互：** 任务输入框（多行）；Token 预算滑块（默认 4000，范围 500–32000）；模型选择器（影响预算启发式——不同模型有效上下文窗口不同）；作用域过滤器（project / team / org / user / pool）；运行按钮 → 触发实时打包模拟。
- **输出面板：** 排名候选列表，列包含——排名、asset-id、subtype、scope、分数、纳入原因（相关性门选择该资产的理由）、Token 数量、累计 Token；清晰标记纳入/排除边界。
- **实时：** 逐键预览（防抖 500 毫秒）——随任务描述输入实时更新候选列表。
- **特殊功能：**
  - 复制到剪贴板——将完整打包提示词（与发送给 LLM 的内容完全一致）复制到剪贴板。
  - A/B 对比模式——两个任务描述并排显示；高亮在其中一个中出现但另一个中未出现的资产。
- **为何关键：** 当运维人员怀疑相关性门选择了错误的记忆时，此页面精确显示哪些资产被评分、每个资产被纳入或排除的原因，以及 Token 边界落在何处。它也是理解 engram 上下文打包机制的主要教学工具。

#### /wisdom（智慧曲线）

- **用途：** 可视化四条智慧曲线，并支持下钻至源数据。
- **数据：** `graph.db` 中的 `metrics_wisdom` 表（每资产、每天、每条曲线一行）。
- **交互：** 时间范围选择器（7天 / 30天 / 90天 / 全部）；每条曲线下钻 → 源数据行（asset-id、日期、值、贡献事件）；导出任意曲线原始数据为 CSV；回归警报横幅（任意曲线周环比下降 > 10% 时显示）。
- **实时：** SSE 监听 `wisdom_sample` 事件（由每小时指标聚合作业发出）——图表实时向右延伸。

#### /autolearn（自学习控制台——全局总览及各工作流子页面）

- **用途：** 实时自学习控制台——既是全局总览，也可从 `/workflow/<name>` 进入各工作流详情。
- **数据：** `evolution.tsv`；工作区日志（`~/.engram/journal/*.jsonl` 中的自学习事件）。
- **交互：** 启动 / 暂停 / 中止按钮（按工作流）；当前轮次的实时日志尾流（通过 SSE 流式传输子进程输出行）；历史运行表格，含每轮接受/拒绝结果和指标增量。
- **实时：** SSE 监听 `autolearn_round` 事件——日志尾流逐行更新；轮次完成时历史运行表格追加新行。

---

### 7.2 路由与 URL 方案

所有路由均为简洁 URL，支持深度链接和书签收藏。SvelteKit 基于文件的路由直接映射：

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

所有路由均采用服务器端渲染（SvelteKit SSR），便于无障碍访问和直接 URL 分享。查询参数保存过滤状态，因此过滤后的图谱视图或特定上下文预览任务均可通过书签或 URL 共享。

---

### 7.3 基于 SSE 的实时推送

**监听守护进程**——在 `engram web serve` 启动时自动运行——使用操作系统原生文件系统通知监控 engram 存储：

- `<项目根目录>/.memory/`（所有作用域）
- `~/.engram/pools/`、`~/.engram/team/`、`~/.engram/org/`、`~/.engram/user/`
- `~/.engram/inbox/`
- `~/.engram/journal/*.jsonl`

操作系统后端：Linux 使用 `inotify`；macOS 使用 `FSEvents`；Windows 使用 `ReadDirectoryChangesW`。检测到变更时，守护进程向所有活跃 SSE 流发布事件。监听器作为后台线程运行于 `engram web serve` 进程中；当 Web UI 未运行时，也可通过 `engram daemon start` 作为独立后台服务运行。

**前端订阅：** `EventSource('/events?filter=asset_changed,inbox_message,...')`。`filter` 查询参数限制向给定页面推送的事件类型——`/graph` 仅订阅 `asset_changed`；`/inbox` 订阅 `inbox_message`；`/dashboard` 订阅全部。

**线上 JSON 事件格式：**

```json
{"type":"asset_changed","id":"local/feedback_foo","change":"updated","ts":"2026-04-18T10:30:00Z"}
{"type":"inbox_message","msg_id":"m-abc","to":"this-repo","change":"created"}
{"type":"proposal_created","proposal_id":"cp-xyz","class":"factual-conflict","severity":"warning"}
{"type":"autolearn_round","workflow":"release-checklist","round":5,"status":"accepted","metric_delta":0.03}
{"type":"wisdom_sample","curve":"workflow_mastery","scope":"release-checklist","value":0.87}
{"type":"pool_updated","pool":"design-system","revision":"r8","change":"new_revision"}
```

**背压：** 服务器为每个连接缓冲最多 100 个事件；溢出时丢弃最旧的事件，并发送 `{"type":"overflow","dropped":N}` 哨兵，客户端据此可强制全量重载。

**降级方案：** 如客户端不支持 SSE（罕见情况），前端降级为每 10 秒轮询 `GET /api/sync?since=<ts>`。

---

### 7.4 认证

**默认：无认证，绑定 127.0.0.1**——安全，因为只有本地进程才能连接回环地址。典型单开发者工作流无需任何凭据。

**可选模式**（在 `~/.engram/config.toml` 的 `[web].auth_mode` 中配置）：

| 模式 | 描述 | 配置项 |
|------|------|--------|
| `none` | 无认证（默认）；仅绑定 127.0.0.1 | — |
| `basic` | HTTP Basic 认证 | `[web].auth_user`、`[web].auth_pass_hash`（argon2id） |
| `token` | Bearer Token | `[web].tokens`（指向每行一个 Token 的文件路径；可撤销） |

**局域网暴露安全门：** 若 `bind = "0.0.0.0"`（或任何非回环地址），`engram web serve` 在 `auth_mode` 为 `none` 时拒绝启动。错误信息明确说明：`"拒绝启动：非回环绑定要求 auth_mode != none。请将 [web].auth_mode 设置为 basic 或 token。"` 此检查无法绕过。

**Web UI 绝不执行的操作：** 不在任何请求体中接收 LLM API 密钥、机密或凭据。所有密钥保留在服务器端的 `config.toml` 和环境变量中。来自浏览器的请求仅携带 asset-id、参数和会话 Token。

**会话：** 包含签名会话 Token 的 HTTP-only Cookie；默认超时 8 小时；可通过 `[web].session_timeout_hours` 配置。

---

### 7.5 国际化

首日发布两种语言：英语（`en`）和中文（`zh`）。

**选择优先级（从高到低）：**

1. URL 查询参数 `?lang=zh`
2. 用户偏好 Cookie（`engram_lang`）
3. `Accept-Language` HTTP 请求头
4. `config.toml` 中的 `[web].default_locale`（默认：`en`）

**翻译文件结构：**

```
web/frontend/src/i18n/
├── en.json
└── zh.json
```

所有面向用户的字符串均已外部化。Svelte 组件中不出现硬编码文本——每个标签、按钮文字、aria-label 和错误消息均引用一个键名。键名与词汇表对齐（例如 `memory.subtype.feedback`、`scope.team`、`page.context_preview.title`），使翻译文件同时作为机器可读的词汇表索引。

如需添加额外语言，只需在目录中新增 `<locale>.json` 文件，无需修改代码。

---

### 7.6 无障碍访问与键盘导航

- **合规目标：** WCAG 2.1 AA。
- **键盘导航：** Tab 顺序遵循 DOM 阅读顺序；`j` / `k` 在列表和表格中移动到下一条/上一条；`/` 聚焦全局搜索框；`g g`（双击）导航至 `/dashboard`（vim 风格全局快捷键）；`Esc` 关闭弹窗和侧面板。
- **屏幕阅读器支持：** 所有纯图标按钮添加 `aria-label`；全程使用语义化 HTML（`<nav>`、`<main>`、`<article>`、`<section>`、`<aside>`）；为 SSE 驱动的更新设置实时区域（`aria-live="polite"`），使辅助技术可以宣读新消息和轮次完成通知。
- **颜色：** 信息传达不单纯依赖颜色（每个状态同时使用图标或文字标签）；所有文本最低对比度 4.5:1；页眉提供深色/浅色主题切换（偏好保存在 Cookie 中）。

---

### 7.7 打包与部署

**分发选项：**

1. **pip 可选依赖（主要方式）：** `pip install 'engram[web]'`——安装 FastAPI、Uvicorn 及 SvelteKit 运行时依赖；前端构建产物在打包时预先构建（运行时无需 Node.js）。
2. **单一可执行文件（未来，v0.2 之后）：** 通过 PyOxidizer 或 Nuitka；嵌入前端构建产物的自包含可执行文件。
3. **Docker 镜像：** `ghcr.io/tbosos/engram-web:latest`——容器化；通过卷挂载 `~/.engram` 和项目目录；暴露端口 8787。

**静态资产：** SvelteKit `build` 输出打包进 Python 包的 `engram/web/static/` 目录。FastAPI 通过 `StaticFiles` 提供服务。终端用户机器无需 Node.js、npm 或 Vite。

**资源使用目标：**

| 资源 | 目标 |
|------|------|
| 内存（稳定状态） | < 100 MB |
| CPU（空闲） | < 5% |
| 磁盘（二进制文件 + 构建产物 + graph.db 缓存） | < 200 MB |
| 冷启动时间 | < 1 秒至首次 HTTP 响应 |

**启动：** `engram web serve`——开放端口，启动监听守护进程，打印 `Engram web UI running at http://127.0.0.1:8787`。`engram web open` 在默认浏览器中打开该 URL。

**优雅关闭：** 收到 SIGTERM 后——完成正在处理的请求，关闭 SSE 连接（发送 `{"type":"shutdown"}` 事件，客户端可显示"服务器已停止"横幅），停止监听器，刷新日志，以 0 退出。若关闭未在 5 秒内完成，则发送 SIGKILL 强制终止。

---

### 7.8 测试策略

详情延至 §10；Web UI 关键测试要点：

- **单元测试：** 使用 Vitest + `@testing-library/svelte` 测试 Svelte 组件；使用 pytest + httpx 测试 FastAPI 路由处理器。
- **集成测试：** 对真实（内存中）SQLite graph.db 测试 API 路由；使用异步 httpx 客户端读取事件流测试 SSE 事件流。
- **E2E 测试：** Playwright 场景覆盖全部 10 个页面——冒烟测试（加载每个页面，无控制台错误，无损坏的 aria 角色）；关键流程交互测试（保存记忆、运行上下文预览、发送收件箱消息、启动自学习轮次）。
- **视觉回归：** CI 中的 Percy 截图（可选；通过 `CI_PERCY=1` 环境变量控制）。
- **无障碍：** Playwright 中的 axe-core 断言（`@axe-core/playwright`）在每个页面加载测试中运行，以捕获 WCAG 回归。

---

### 7.9 Web UI 自身的可观测性

- **访问日志：** 所有 HTTP 请求记录至 `~/.engram/web.log`（Apache Combined Log Format）；默认情况下仅回环地址，无 PII 超出 IP 范围。
- **错误日志：** 未捕获的异常及 5xx 响应附带堆栈跟踪记录至 `~/.engram/web.log`。
- **无遥测：** Web UI 不发出任何出站网络请求。无分析、无崩溃报告、无外部 CDN。所有资产本地提供。
- **健康检查：** `GET /healthz` → `{"status": "ok", "version": "0.2.x", "watcher": "running", "db": "ok"}`。适用于 Docker/systemd 健康检查。
- **调试页面：** `GET /debug`（仅在 `auth_mode = basic` 或 `token` 时可访问，且仅限已认证会话）——显示：监听器统计（监控文件数、事件/秒）、graph.db 缓存命中率、各事件类型的 SSE 订阅者数量、活跃会话数、运行时间以及服务器版本。

---

### 7.10 实现优先级

并非全部 10 个页面在首次 Web UI 发布时上线。优先级在 TASKS.md 里程碑 M4–M7 中跟踪：

**P0——M7 MVP（必须上线）：**

| 页面 | P0 理由 |
|------|---------|
| `/dashboard` | 首个打开的页面；一览系统健康状态 |
| `/memory/<id>` | 核心资产编辑——人类最频繁的交互 |
| `/workflow/<name>` | 自学习控制需要 UI；仅 CLI 过于不透明 |
| `/kb/<topic>` | 知识文章编译 + 编辑循环受益于左右对比视图 |
| `/inbox` | 跨仓库协作在消息量较大时需要 UI |
| `/context-preview` | 关键调试工具；无此工具运维人员无法信任系统 |

**P1——M7 完善阶段（M7 关闭前上线）：**

| 页面 | P1 理由 |
|------|---------|
| `/graph` | 价值高但复杂；D3 力导向布局的调优非易事 |
| `/pools` | 团队池投入使用后才需要；非首日要求 |
| `/projects` | 仅当用户有 ≥ 2 个 engram 项目时才相关 |
| `/wisdom` | 可通过 CLI `engram wisdom report` 查看曲线；UI 为便利功能 |
| `/autolearn` | 全局视图；`/workflow/<name>` 中的工作流标签页已覆盖 P0 用例 |

---

## 8. 关键不变量

### 8.0 引言

前几章在各自的局部范围内分别介绍了不变量：§2.3 列出了数据独立性、日志追加、智能层开关、确定性冲突解决、禁止自动删除五条"不可改变量"；§5.0.3 阐述了智能层的六条设计原则；SPEC §11 声明了一致性非目标。§8 将它们全部汇总为十二条不可妥协的不变量，作为单一权威参考。

每一个实现——参考实现 engram-cli、第三方工具、未来新增的组件，以及本文档写成之后添加的任何子系统——都必须满足以下所有不变量，并同时满足所有 SPEC 规则。满足其中十一条的实现仍属不符合规范。

---

### 8.1 十二条不变量

**1. 数据独立性**

Layer 1 文件绝不引用任何工具专有路径、二进制格式或 engram 私有字段。一个符合 SPEC 规范的 `.memory/` 目录无需安装 engram-cli 即可正常使用：任何 LLM 可读取它，任何文本编辑器可编辑它，任何版本控制系统可追踪它，任何人类可理解它。

- 理由：存储的生命周期长于工具本身；用户不应被锁定。
- 执行方式：SPEC 前置字段中不存在以 `engram_` 为前缀且在 engram 之外毫无意义的命名空间字段；`engram validate` 通过 SPEC §12 FM 校验器检测工具专有命名空间。

**2. 真实文件唯一性**

每个资产的规范文件恰好存在于一个位置（其作用域根目录）。所有其他表观路径均为指向该规范位置的符号链接。禁止在多个非符号链接路径上存在重复内容的普通文件。

- 理由：消除"哪份是真相？"的歧义；简化同步、备份和验证。
- 执行方式：`engram validate` 检测多个具有相同 `asset_id` 或相同内容哈希的普通文件；运维人员须在验证通过前修复该问题。

**3. 禁止自动删除**

任何层级都不得在未经运维人员明确操作的情况下删除资产数据。归档是必经的中间步骤。物理删除要求资产在 `archive/` 中已驻留至少六个月，且 `engram archive gc` 命令须携带显式的 `--past-retention` 标志并通过交互式确认提示。

- 理由：用户只有在做出有意识的决策时才会丢失记忆；误操作可以恢复。
- 执行方式：归档保留下限是硬编码常量（非可配置项）；任何将其配置为低于 180 天的 PR 在评审环节即被拒绝。

**4. 智能层可禁用**

每个智能层组件（相关性网关、一致性引擎、自学习引擎、演化引擎、跨仓库消息器、智慧度量）都拥有 `enabled = false` 配置开关。当所有开关均设为 false 时，系统仍须通过 `engram validate`、`engram memory retrieve` 和 `engram review`。

- 理由：智能层是可选增强，而非基础；服务器部署、离线环境和极简主义用户均为一等公民。
- 执行方式：CI 在每次提交时运行"全部智能关闭"测试配置文件；完整命令套件须在该配置文件下全部通过。

**5. 观察层可选**

仅凭 CLI（`engram-cli`）就必须能够提供完整的 engram 使用体验。Web UI（Layer 5）是一种便利功能。`pip install engram` 不得引入 FastAPI、Svelte 构建产物或任何 GUI 依赖。

- 理由：无头部署（服务器、CI 流水线、终端极简主义者）是一等公民。
- 执行方式：`engram-cli` 包中的 Web UI 为可选附加项（`pip install engram[web]`）；每次发布时对基础包依赖列表进行审查。

**6. 适配器再生不破坏用户内容**

`engram adapter <tool> --regenerate` 保留所有被 `engram:begin`/`engram:end` 标记块包裹的用户自定义内容，绝不覆盖用户文本。标记对缺失或格式错误属于错误，而非静默覆盖。

- 理由：用户会对适配器文件进行自定义；工具版本更新不得摧毁其工作成果。
- 执行方式：标记缺失时发出错误码 `E-ADP-001` 并以非零退出；再生函数具有覆盖标记存在、标记缺失、标记格式错误三种情况的单元测试。

**7. MCP 服务器无状态**

每个 MCP 请求从头重新读取文件系统状态。调用之间不保留任何内存会话状态。每个工具函数是文件系统上的纯函数：相同输入加上相同文件系统状态，产生相同输出。

- 理由：可预测性和并发会话安全性。多个 LLM 会话同时访问同一存储时，相同输入必须产生相同结果。
- 执行方式：MCP 服务器架构审查禁止实例级可变状态；集成测试对共享存储并发运行两个 MCP 会话并断言结果等价。

**8. CLI 命令默认幂等**

连续执行同一 `engram` 命令两次，与执行一次产生相同的可观测结果。例外情况是被明确标注为可变更的命令（如 `engram workflow run`、`engram journal append`），这些命令在其手册页条目中注明为非幂等。

- 理由：脚本和自动化安全；重试不会损坏状态。
- 执行方式：CLI 命令设计检查表要求对每条新命令进行幂等性评估；非幂等命令在 CLI 模块中携带 `# NON-IDEMPOTENT` 注释。

**9. 日志仅追加**

`~/.engram/journal/*.jsonl` 文件从不原地编辑。新事件始终以追加方式写入。压缩（用于存储管理）将完整的日志文件移动至 `archive/journal/` 并启动新文件；绝不删除事件或修改现有行。

- 理由：审计跟踪完整性。完整的事件历史使得在任意历史时间点重建状态成为可能。
- 执行方式：`engram validate` 通过比较文件 mtime 与文件中最早事件时间戳来检测原地编辑；任何不匹配均为验证错误。

**10. 规范先于实现**

任何影响磁盘格式（Layer 1）、有线协议（Layer 4 MCP）或跨作用域行为的功能，必须先出现在 SPEC 变更中，再出现在 DESIGN 中，最后才出现在代码中。当涉及磁盘格式时，任何实现层中均不存在"由实现决定"的行为。

- 理由：多实现兼容性。只有当 SPEC 始终领先于代码时，第三方工具才能以信心构建在 SPEC 之上。
- 执行方式：PR 审查检查表要求为任何新的磁盘字段提供 SPEC 引用或 SPEC 变更；SPEC 变更须在合并前至少开放讨论一周的议题。

**11. 无容量上限**

engram 对任何作用域中的资产数量、作用域数量或任何资产类的大小不设硬性上限。质量由一致性引擎（§5.2）和用户主动归档来维护，而非通过淘汰或大小限制来实现。

- 理由：用户的知识存储可以跨越数十年增长。淘汰机制会在未经用户同意的情况下销毁记忆，违反不变量 3。
- 执行方式：`engram validate` 规则拒绝组件代码中任何硬编码大小检查；MEMORY.md 模板没有行数限制；性能要求以延迟 SLO 表达，而非容量限制。

**12. 跨进程安全**

并发运行的 `engram` 调用——多个 LLM 会话、GUI + CLI 同时使用、并行 CI 任务——绝不损坏共享状态。SQLite 在 WAL 模式下运行。资产文件写入使用原子写临时文件后重命名的模式。独占操作（archive gc、模式迁移）通过 `fcntl` 建议锁进行保护。

- 理由：真实使用场景涉及多个进程同时访问。
- 执行方式：集成测试套件包含 N 并发操作压力测试（N ≥ 4）；CI 测试组合分别覆盖 POSIX 文件锁定（Linux、macOS）和 Windows 文件锁定。

---

### 8.2 不变量的可组合性

十二条不变量并非相互独立的规则——它们共同构成一个相互强化的基础。移除其中任意一条都会动摇其他条：

| 若移除… | …则破坏 |
|---|---|
| 不变量 3（禁止自动删除） | 用户无法信任归档；记忆丢失变得无声无息 |
| 不变量 9（日志仅追加） | 一致性引擎无法审计历史；状态重建功能失效 |
| 不变量 7（MCP 无状态） | 并发会话产生分歧；不变量 12 变得无法执行 |
| 不变量 1（数据独立性） | 存储不再可移植；第三方工具无法符合规范 |
| 不变量 4（智能层可禁用） | 不变量 5（CLI 充分性）在离线环境下遭到破坏 |
| 不变量 11（无容量上限） | 淘汰机制静默删除记忆，违反不变量 3 |

**新增不变量**需要：开放供讨论的议题至少两周、至少两位维护者达成共识，以及在本节中添加一条理由条目说明若该不变量被移除会破坏什么。不变量易加难减；移除须证明没有任何现有不变量依赖于被移除的那条。

---

---

## 9. 源码仓库结构

### 9.0 概述

§9 规定了 engram GitHub 仓库本身的源码树结构，以及在用户机器上创建的运行时布局（位于 `~/.engram/` 下以及各 `<project>/.memory/` 目录中）。阅读本节的实现者将清楚了解每个部分的归属位置——无论是开发阶段（仓库中存放什么）还是运行阶段（CLI 在用户系统上创建什么）。

两种布局相辅相成：仓库树定义了发布内容；机器布局定义了运行内容。二者不重复。

### 9.1 GitHub 仓库目录树

```
engram/                                     # GitHub 仓库根目录
├── README.md / README.zh.md                # 双语简介
├── SPEC.md / SPEC.zh.md                    # 格式规范 (v0.2)
├── DESIGN.md / DESIGN.zh.md                # 本文档
├── METHODOLOGY.md / METHODOLOGY.zh.md      # LLM 应如何写入记忆（第 4 阶段编写）
├── TASKS.md / TASKS.zh.md                  # 里程碑看板（第 3 阶段）
├── CONTRIBUTING.md / CONTRIBUTING.zh.md    # （第 4 阶段）
├── LICENSE                                 # MIT
├── CHANGELOG.md                            # （v0.2.0 发布时创建）
├── pyproject.toml                          # 根目录（cli/、web/ 的工作区）
├── .pre-commit-config.yaml                 # lint/format 钩子
├── .github/
│   ├── workflows/
│   │   ├── ci.yaml                         # 测试 + lint + 类型检查组合
│   │   ├── release.yaml                    # 打 tag 时发布至 PyPI
│   │   ├── benchmark.yaml                  # 依照 SPEC Amendment B — 仅在发布时运行
│   │   └── pages.yaml                      # GitHub Pages 部署（已从 /docs 服务）
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── cli/                                    # Layer 2 + Layer 3、4 的部分功能
│   ├── pyproject.toml
│   ├── engram/                             # Python 包
│   │   ├── __init__.py
│   │   ├── __main__.py                     # `python -m engram` 入口点
│   │   ├── cli.py                          # click CLI 调度器
│   │   ├── core/                           # Layer 1 访问
│   │   │   ├── paths.py                    # ~/.engram/ + 项目根目录解析
│   │   │   ├── frontmatter.py              # YAML 解析 + 验证
│   │   │   ├── fs.py                       # 原子写入、锁、符号链接
│   │   │   ├── graph_db.py                 # SQLite 模式 + 查询
│   │   │   ├── journal.py                  # 仅追加 jsonl 辅助函数
│   │   │   └── cache.py                    # 向量嵌入 + FTS5 + 相关性缓存
│   │   ├── memory/                         # memory 子命令
│   │   │   ├── commands.py                 # add/list/read/update/archive/search
│   │   │   └── render.py                   # MEMORY.md 生成
│   │   ├── workflow/
│   │   │   ├── commands.py
│   │   │   ├── runner.py                   # spine 调用
│   │   │   └── fixtures.py                 # fixture 测试框架
│   │   ├── kb/
│   │   │   ├── commands.py
│   │   │   └── compiler.py                 # _compiled.md 生成
│   │   ├── pool/
│   │   │   ├── commands.py
│   │   │   ├── propagation.py              # 自动同步/通知/pinned 逻辑
│   │   │   └── git_sync.py                 # 基于 git 的团队/组织/pool 同步
│   │   ├── team/                           # 与 pool 相同，适用于 team 作用域
│   │   ├── org/                            # 适用于 org 作用域
│   │   ├── inbox/
│   │   │   ├── commands.py
│   │   │   ├── messenger.py                # SPEC §10 实现
│   │   │   ├── dedup.py
│   │   │   └── rate_limit.py
│   │   ├── consistency/
│   │   │   ├── commands.py
│   │   │   ├── engine.py                   # DESIGN §5.2 四阶段扫描
│   │   │   ├── phase1_static.py
│   │   │   ├── phase2_semantic.py          # DBSCAN
│   │   │   ├── phase3_llm.py
│   │   │   ├── phase4_execution.py
│   │   │   └── resolve.py                  # apply_update/supersede/merge/archive/dismiss
│   │   ├── relevance/                      # Layer 3 §5.1
│   │   │   ├── gate.py                     # 7 阶段混合管道
│   │   │   ├── embedder.py                 # 提供者：本地 bge / openai / cohere
│   │   │   ├── bm25.py
│   │   │   └── temporal.py                 # "N 周前"解析
│   │   ├── autolearn/                      # §5.3
│   │   │   ├── engine.py                   # Darwin 8 学科循环
│   │   │   ├── proposer.py
│   │   │   ├── judge.py
│   │   │   └── ratchet.py
│   │   ├── evolve/                         # §5.4
│   │   │   └── engine.py                   # ReMem 行动-思考-精炼
│   │   ├── wisdom/                         # §5.6
│   │   │   ├── aggregator.py
│   │   │   └── curves.py
│   │   ├── context/                        # §6.3 提示词打包
│   │   │   └── pack.py
│   │   ├── mcp/                            # §6.2 MCP 服务器
│   │   │   ├── server.py
│   │   │   └── tools.py                    # 带类型的 pydantic 模式
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
│   │   ├── adapter/                        # §6.1 适配器
│   │   │   └── commands.py
│   │   ├── playbook/                       # §6/§8 playbook 安装
│   │   │   └── commands.py
│   │   └── config.py                       # ~/.engram/config.toml
│   └── tests/                              # pytest
│
├── web/                                    # Layer 5 engram-web
│   ├── backend/                            # FastAPI
│   │   ├── pyproject.toml
│   │   ├── engram_web/
│   │   │   ├── app.py                      # FastAPI 应用工厂
│   │   │   ├── routes/
│   │   │   ├── sse.py                      # Server-Sent Events
│   │   │   ├── watcher.py                  # inotify/FSEvents
│   │   │   └── auth.py                     # 无认证/基本认证/令牌
│   │   └── tests/
│   └── frontend/                           # Svelte
│       ├── package.json
│       ├── svelte.config.js
│       ├── src/
│       │   ├── routes/                     # SvelteKit 页面（§7.1）
│       │   ├── lib/
│       │   │   ├── components/
│       │   │   ├── stores/
│       │   │   └── api/
│       │   └── i18n/                       # en.json、zh.json
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
├── adapters/                               # §6.1 模板
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
├── seeds/                                  # 初始化种子
│   ├── base/                               # 中性默认值
│   ├── opinionated/                        # 可选基准反馈
│   └── profiles/
│       ├── embedded-systems/
│       ├── web-platform/
│       └── data-eng/
│
├── playbooks/                              # 社区贡献的 playbook
│   └── README.md                           # 提交指南
│
├── tests/                                  # 跨组件测试
│   ├── conformance/                        # SPEC §12 fixture
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
└── docs/                                   # GitHub Pages 根目录（/docs）
    ├── .nojekyll
    ├── index.html                          # 语言选择页
    ├── en/index.html
    ├── zh/index.html
    ├── assets/                             # fonts.css + anthropic.css + app.css
    ├── WEBSITE-MAINT.md
    ├── glossary.md / glossary.zh.md
    ├── archive/v0.1/                       # 已冻结
    └── superpowers/
        ├── plans/
        └── specs/
```

### 9.2 顶层目录职责

每个顶层条目的单行摘要；读者可扫描此表并跳转至上方对应子树。

| 目录 | 职责 |
|---|---|
| `cli/` | Python CLI — 参考实现，以 `engram` 包形式发布至 PyPI |
| `web/` | engram-web — FastAPI 后端 + SvelteKit 前端；通过 `engram[web]` 额外依赖可选安装 |
| `sdk-ts/` | TypeScript SDK — `@engram/sdk` npm 包 |
| `adapters/` | 提示词模板文件（源文件）；`engram adapter <tool>` 将实例渲染至用户项目 |
| `seeds/` | `engram init` 的模板记忆内容；包含 base（中性）+ opinionated + 领域 profile |
| `playbooks/` | 社区贡献的 Playbook 提交（集中于此以便发现） |
| `tests/` | 跨组件测试（一致性 + E2E + 手动）；各组件自测位于各自目录中 |
| `benchmarks/` | 自建 + LongMemEval + evolution — 可复现；结果按 Amendment B 提交 |
| `docs/` | GitHub Pages（落地页 + 规范文档）；从 `main/docs` 服务 |

### 9.3 用户机器布局

以下路径由 `engram init` / 运行时操作在用户机器上创建。这独立于仓库，描述了实现者必须在磁盘上生成的内容（摘自 SPEC §3.2 / DESIGN §3）。

```
~/.engram/
├── version                                 # "0.2"
├── config.toml
├── org/<org>/                              # 作用域：org
├── team/<team>/                            # 作用域：team
├── user/                                   # 作用域：user
├── pools/<pool>/                           # 可订阅（作用域：pool）
├── playbooks/<name>/                       # 已安装的 playbook
├── inbox/<repo-id>/                        # 跨仓库消息
├── archive/                                # 已标记删除的资产（保留期内）
├── workspace/                              # autolearn / evolve / consistency 沙箱
├── cache/                                  # 向量嵌入 + FTS5 + 相关性
├── journal/                                # *.jsonl 仅追加
├── graph.db                                # SQLite 索引
└── web.log                                 # 若 web 服务器已运行

<project>/
├── .memory/                                # 项目作用域存储
│   ├── MEMORY.md
│   ├── pools.toml
│   ├── local/                              # 作用域：项目资产
│   ├── pools/                              # 符号链接至 ~/.engram/pools/<name>/
│   ├── workflows/
│   ├── kb/
│   └── index/                              # 可选主题子索引
├── .engram/
│   └── version
├── CLAUDE.md / AGENTS.md / GEMINI.md       # 适配器文件（若已生成）
└── .cursor/rules                           # 若使用 cursor 适配器
```

### 9.4 代码风格与工具链

**Python（`cli/`、`web/backend/`）：**
- 代码检查：`ruff`（合并替代 flake8/isort/pylint）
- 格式化：`ruff format`（非 black — ruff 已覆盖）
- 类型检查：对 `cli/engram/` 和 `web/backend/engram_web/` 执行 `mypy --strict`
- 行宽：100 列
- Python 版本：最低 3.10+（在 3.10、3.11、3.12、3.13 上测试）

**TypeScript（`web/frontend/`、`sdk-ts/`）：**
- 代码检查：`eslint` 配合 `@typescript-eslint`
- 格式化：`prettier`（100 列，单引号）
- 类型严格度：`tsconfig strict: true`
- Node：≥18（用于 `sdk-ts`）；尽力兼容 Bun/Deno

**Shell 脚本（`adapters/*/hooks/`）：**
- CI 中运行 `shellcheck`
- Shebang：`#!/usr/bin/env bash`，设置 `set -euo pipefail`

**提交约定：** Conventional Commits（`type(scope): subject`）。类型：`feat / fix / docs / refactor / test / chore / perf / ci / spec / design / website`。

**分支模型：**
- `main` — 稳定；每次提交均通过 CI
- `feat/<topic>` — 功能分支（通过 PR 合并）
- 发布标签：`v0.2.0`、`v0.2.1`……

### 9.5 包发布

| 包 | 注册表 | 安装方式 |
|---|---|---|
| `engram`（CLI + 智能层 + MCP） | PyPI | `pip install engram` |
| `engram[web]`（+ FastAPI + Svelte 构建包） | PyPI 额外依赖 | `pip install 'engram[web]'` |
| `@engram/sdk` | npm | `npm install @engram/sdk` |
| `engram`（Homebrew） | `brew tap TbusOS/engram` | `brew install engram`（M3+） |
| GitHub Pages 站点 | 静态 | 推送至 `main/docs` 后自动部署 |

---

## 10. 测试策略

### 10.0 测试金字塔与测试哲学

**五种测试类型，按反馈速度排序：**

| 层级 | 范围 | 速度 | 外部依赖 |
|---|---|---|---|
| 单元测试 | 纯函数、数据结构 | 总计 < 1s | 无 |
| 集成测试 | 组件交互（graph.db + fs + cli） | 秒级 | 本地数据库、文件系统 |
| E2E 测试 | 全栈场景（init → add → search → review） | 分钟级 | 临时目录中的 CLI |
| 合规性测试 | SPEC 合规性夹具（可移植，第三方可复用） | 分钟级 | 无 |
| LLM 行为测试 | 适配器与上下文打包对真实 LLM 的正确性 | 小时级 / 按需执行 | LLM 提供商 |

**测试哲学：** 单元测试提供最快的反馈循环，以最低成本捕获最多回归。E2E 测试捕获单元测试遗漏的集成缺陷。合规性夹具使 SPEC 具备可移植性——任何符合 engram 规范的工具（Go 移植版、Rust 移植版）均可运行这些夹具以认证合规性。LLM 行为本质上具有概率性，完全自动化不切实际，因此采用带黄金记录（golden records）和发布节点人工检查点的半自动模式。

### 10.1 覆盖率目标

- **Python（`cli/engram/`）：** ≥ 80% 行覆盖率，通过 `pytest-cov --fail-under=80` 强制执行
- **TypeScript SDK（`sdk-ts/`）：** ≥ 80% 行覆盖率，通过 `vitest --coverage` 强制执行
- **Svelte 前端（`web/frontend/`）：** ≥ 70% 组件覆盖率，通过 `vitest` + `@testing-library/svelte` 强制执行
- **CI 强制执行：** 若覆盖率相对当前基线（存储于 `tests/.coverage-baseline.json`）下降超过 2%，PR 将被阻断
- **基准测试脚本（`tests/perf/`）：** 无覆盖率要求——非生产代码
- **强制覆盖路径：** 每个 CLI 子命令（`init`、`add`、`search`、`review`、`migrate`、`pool`、`inbox`、`context pack`、`validate`、`consistency scan`、`mcp serve`、`web serve`、`export`、`conformance`）至少有一个覆盖正常路径的 E2E 测试

### 10.2 合规性夹具（`tests/conformance/`）

一套 SPEC 级测试套件，任何符合 engram 规范的工具均可运行。每个夹具包含一个完整的 `.memory/` 目录，以及与之对应的预期 `validate` JSON 输出（一同提交至仓库）。

```
tests/conformance/
├── healthy/
│   ├── minimum-viable/             # SPEC §14.A 示例
│   ├── mid-size/                   # 跨子类型约 50 个资产
│   └── large-with-pools/           # 约 500 个资产 + 3 个池
├── edge-cases/
│   ├── unicode-names/
│   ├── symlink-chains/
│   ├── empty-workflows/
│   └── long-memory/                # 单条记忆 > 10K 行（无上限）
├── v0_1_legacy/
│   ├── flat-memory/                # 需要迁移
│   └── shared-pool-v0_1/
├── broken/
│   ├── missing-frontmatter/
│   ├── mandatory-override-conflict/
│   ├── circular-supersedes/
│   ├── dangling-symlink/
│   └── wrong-scope-location/
└── expected/
    └── <fixture-name>.json         # 规范化 validate 输出
```

**运行方式：** `engram conformance test tests/conformance/<fixture-name>` — 运行 `validate`，与预期 JSON 做差异比对，返回通过/失败。

**编写规范：** 每条新增的 SPEC 规则至少对应一个夹具（位于 `healthy/`、`edge-cases/` 或 `broken/` 中）。规则删除或放宽时，对应夹具移至 `deprecated/` 目录并从 CI 中移除（而非直接删除），以保留迁移历史。

**第三方可移植性：** Go 和 Rust 移植版通过一个薄适配层运行本套件，该适配层调用各自的 `validate` 实现并将输出与 `expected/*.json` 比对。夹具格式在次版本之间保持稳定；破坏性变更需引入新的夹具版本前缀（`v2/`）。

### 10.3 E2E 测试场景（`tests/e2e/`）

基于 pytest 构建。每个场景创建独立的临时目录，以子进程方式运行 CLI，并对标准输出/标准错误/文件系统状态进行断言。不对 CLI 本身进行模拟（mock）。

```
tests/e2e/
├── test_init_and_review.py              # 空目录 → init → review：全部绿色
├── test_migrate_from_v0_1.py            # 构建 v0.1 存储 → 迁移 → validate 干净
├── test_multi_adapter.py                # 以 claude+codex+gemini 初始化 → 验证 3 个适配器文件 + 同一 .memory/
├── test_pool_subscribe_notify.py        # 发布池 → 订阅者收到通知 → 接受 → 同步
├── test_pool_subscribe_pinned.py        # 订阅固定版本 → 发布新版本 → 不自动更新 → 手动更新
├── test_inbox_roundtrip.py              # A 发送 → B 确认 → B 解决 → A 看到通知
├── test_consistency_scan_seven_classes.py  # 注入合成冲突 → 扫描检测 → 解决
├── test_autolearn_smoke.py              # 最小工作流 → 3 轮自学习 → 验证单调改进
├── test_mcp_stdio.py                    # 启动 MCP 服务器 → 调用每个工具 → 验证响应
├── test_web_smoke.py                    # 启动 web serve → playwright 点击 10 个页面 → 无 500 错误
└── test_export_formats.py              # 导出 markdown/prompt/json — 验证输出结构
```

**运行时目标：** 完整 E2E 套件在消费级笔记本电脑（Apple M 系列或同等 x86-64 配置）上运行时间 < 3 分钟。默认不发起 LLM 调用。需要真实 LLM 的场景使用 `@pytest.mark.llm_live` 装饰，仅在传入 `--llm-live` 参数时执行。

**隔离性：** 每个测试通过 pytest 的 `tmp_path` 夹具获得独立的临时目录。通过 `pytest-xdist -n auto` 实现并行执行是安全的——各测试不共享文件系统状态或端口（`web serve` / `mcp serve` 各自随机选择空闲端口）。

### 10.4 LLM 行为验证（半自动）

CLI 是确定性的；LLM 响应是概率性的。采用两级方案在控制 CI 成本的同时保留行为覆盖。

**第一级——自动化提示打包验证**（当环境变量中存在提供商 API 密钥时在 CI 中运行）：

- 固定存储 + 固定任务 → `engram context pack --task="..."` → 将打包提示字节与已提交的基线比对
- 当资产集和预算固定时，输出是确定性的（此步骤无 LLM 调用）
- 50 个规范任务 × 稳定资产集 → 与 `tests/llm-eval/baselines/pack/*.txt` 中的基线进行逐字节比较
- 打包输出发生变化时测试失败；审阅者须通过 PR 批准基线更新

**第二级——半自动化 LLM 行为评估**（`tests/llm-eval/`）：

- 固定存储 + 固定任务 → 真实 LLM 调用（参考模型：Claude Sonnet 4.6）→ 结构化 JSON 输出
- 断言：LLM 是否引用了预期的记忆？（检查响应中是否包含特定资产 ID 或关键短语）
- 仅按需运行（`make llm-eval`）；不随每次 PR 执行（避免 API 预算消耗）
- 结果以黄金记录形式存储于 `tests/llm-eval/golden/`；变更需人工审批

**示例评估场景：**

| 场景 | 预期 LLM 行为 |
|---|---|
| "用户询问推送规则" | 响应引用 `feedback_push_confirmation` 资产 |
| "Agent 在兄弟仓库中发现 Bug" | LLM 发出包含正确 `intent` 字段的 `engram_inbox_send` 工具调用 |
| "任务与 3 条最近记忆属于同一主题" | LLM 加载全部 3 条记忆并保持内部一致 |
| "用户请求添加新团队成员" | LLM 在回答前查阅 `onboarding_checklist` 工作流 |

### 10.5 性能测试（`tests/perf/`）

基于规模的回归防护。不随每次 PR 执行；在 CI 中每周运行一次，并在发布前按需执行。

**测试资产规模：**

| 规模 | 代表场景 |
|---|---|
| 100 个资产 | 最低可行性 |
| 1,000 个资产 | 用户使用约 3 个月后的典型规模 |
| 10,000 个资产 | 用户使用约 2 年后的典型规模 |
| 100,000 个资产 | 高级用户 / 长期存储 |

**目标值（依据 SPEC §20 性能预算）：**

| 操作 | 目标 |
|---|---|
| `engram init`（空项目） | < 1s |
| `engram context pack --budget=900`（冷缓存，10K 资产） | < 100ms |
| `engram context pack --budget=900`（冷缓存，100K 资产） | < 500ms |
| `engram context pack --budget=900`（热缓存，任意规模） | < 50ms |
| `engram validate`（1K 资产） | < 2s |
| `engram validate`（100K 资产） | < 20s |
| `engram consistency scan --phase=1+2`（10K 资产） | < 10min |
| `engram consistency scan --phase=1+2`（100K 资产） | < 90min（日常 cron 可接受） |
| `engram memory search`（任意规模） | < 100ms（graph.db 索引 + FTS5） |

**测试框架：** `tests/perf/bench_*.py` — 通过 `engram conformance gen --count=N` 生成合成存储，使用 `time.perf_counter` 对每个操作计时，并与 `tests/perf/baselines.json` 中已提交的基线比对。若相对基线回归超过 20%，每周任务失败并自动创建 GitHub Issue。

### 10.6 CI 测试组合

`.github/workflows/ci.yaml`：

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ['3.10', '3.11', '3.12', '3.13']
    exclude:
      # macOS + Python 3.10 仅按月频率测试（节省 CI 时间）
      - {os: macos-latest, python: '3.10'}
```

**每个组合：** 单元测试 + 集成测试 + 合规性套件。

**E2E 测试：** 仅在 `ubuntu-latest` + Python 3.12 上运行（快速路径）。为 E2E 添加额外的系统/版本组合需要明确理由（CI 成本较高）。

**Web E2E（Playwright）：** 仅在 ubuntu-latest 上运行。macOS 和 Windows runner 上不安装 Playwright 浏览器二进制文件。

**TypeScript SDK：** Node 18、20、22 × ubuntu-latest + macos-latest；跳过 Windows（部署场景较少；通过单独的计划工作流每月测试一次）。

**计划任务：**

| 任务 | 周期 | 触发方式 |
|---|---|---|
| 性能基准测试 | 每周（周一 02:00 UTC） | Cron |
| macOS + Python 3.10 组合 | 每月 | Cron |
| TypeScript SDK Windows 测试 | 每月 | Cron |
| LLM 评估黄金记录刷新 | 按需 | 手动 `workflow_dispatch` |

### 10.7 人工发布检查清单

`tests/manual-checklist.md` — 在每个发布标签发布至 PyPI 前由人工执行：

- [ ] 在全新虚拟环境中通过 `pip install 'engram'` 安装——除 LLM 提供商调用外，离线可用
- [ ] 在全新目录中执行 `engram init`——生成所有预期文件，结构正确
- [ ] 在项目中打开 Claude Code——`CLAUDE.md` 自动加载，`.memory/` 无错误引用
- [ ] Web UI 冒烟测试：打开 10 个不同页面，确认无控制台错误，键盘导航正常
- [ ] 迁移真实的 Claude Code 记忆存储——零数据丢失，迁移后 `validate` 报告干净
- [ ] 回归健全性：对新版本二进制文件运行上一发布版本的 E2E 套件——所有测试通过
- [ ] 性能仪表板：将基准测试输出与上一发布版本比对——无曲线回归
- [ ] 合规性套件：对三个参考实现（Python、Go、Rust）全部运行——全部通过

---

## 11. 开发者陷阱与应对措施

### 11.0 引言

§11 列举了实现者必须防范的 8 个系统性陷阱。每个陷阱都是在类似系统（MemPalace、Letta、mem0、v0.1 engram）中已经出现过的失败模式。防御措施分散在各章节中；本节将其集中映射，以便工程师在生产环境中遇到问题之前就能内化失败模式。这些陷阱相互独立，但共享一套通用的横切防御措施，详见 §11.9。

### 11.1 陷阱 1 — 写放大

**触发场景：** 每次用户更正都会产生一条新的记忆条目。经过数月使用，`.memory/` 目录中充满了措辞略有不同的近似重复反馈条目。

**症状：** `engram review` 显示 500+ 条类似反馈条目；相关性门控将冗余内容打包到上下文窗口中；LLM 收到关于哪条规则是当前规则的互相冲突信号，因而犹豫不决而非果断行动。

**根本应对：**

- **写入时去重：** `engram memory add` 在写入前检查与同范围内现有条目的语义相似度（余弦 > 0.85 + 关键词重叠）；若相似则提示用户"已存在类似记忆——更新还是新建？"
- **演化引擎合并（§5.4）：** 每月的 `merge` 提案扫描自动聚合语义相近的条目，并提出单一规范替代版本。
- **超越链优先于重复：** 优先使用带 `supersedes:` 链接的现有资产更新，记录演化过程而非完整历史。

**监控信号：** 同一范围内资产数量增长率 > 50/周，但唯一语义簇数量未相应增长（由一致性引擎的 `topic-divergence` 检测器测量）。

**回退方案：** 运行 `engram consistency scan --phase=2`，然后运行 `engram evolve scan` 以显示激进的合并提案；操作员通过 `engram evolve scan` 交互界面批量接受。

### 11.2 陷阱 2 — 指标博弈（自动学习）

**触发场景：** LLM 生成的骨架修改通过捷径最大化声明的接受指标——跳过边界情况分支、硬编码测试夹具输出，或简单满足成功谓词。

**症状：** 指标每轮改善；真实任务性能下降；夹具测试通过但生产工作流在夹具集之外的输入上失败。

**根本应对：**

- **复杂度下限（SPEC §5 / DESIGN §5.3 G2）：** 提议骨架需满足最少 N 步要求；简单单分支改写直接拒绝。
- **简洁性标准：** 对于指标增益 < 5% 的修改，拒绝超过 `complexity_budget_factor`（默认 1.5×）净行数的差异。
- **独立评判（DESIGN §5.3 G3）：** 独立于提议者的 LLM 实例对差异进行评分；评判者对提议者的推理链保持盲目，以发现自我强化的偏见。
- **密钥泄漏正则表达式扫描（G2 静态检查）：** 检测骨架中嵌入的硬编码 API 响应或精确夹具输出。
- **夹具多样性要求：** 每个工作流必须至少包含一个成功案例夹具、一个失败案例夹具，以及至少一个从生产遥测中发现的边界案例。

**监控信号：** 连续 20 轮接受率 > 90%（难度下限过低）；自动学习修改后的工作流部署后失败率比自动学习前基线高出 5% 以上。

**回退方案：** `engram workflow autolearn --abort <name>` 终止运行；`engram workflow rollback <name> --to=<rev>` 恢复到最后已知良好的骨架版本。

### 11.3 陷阱 3 — 过时级联（跨引用腐烂）

**触发场景：** 上游资产池删除或重命名了被 50+ 下游订阅者引用的记忆资产。订阅者的 `references:` 前置数据现在悬空，其在下次同步时的验证失败。

**症状：** 资产池维护者推送破坏性版本后，`engram validate` 立即在多个项目中发出 `W-REF-001` 错误。

**根本应对：**

- **引用图强制执行（SPEC §3.3 MUST 4 + DESIGN §3.2 `references_` 表）：** 被引用资产的删除在 CLI 层被阻止；资产必须经过 `deprecated → archived` 生命周期状态转换后才允许删除。
- **传播 `notify` 模式（SPEC §9.3）：** 非破坏性变更（内容更新）静默传播给订阅者，但破坏性变更（重命名、删除、类型更改）需要操作员明确决策后才能传播。
- **警告级联（DESIGN §5.2 第 1 阶段）：** 下游验证发出 `W-REF-001 reference-rot`；操作员在 `engram review` 中看到警告；资产保持有效但被标记，直到解决为止。

**监控信号：** 资产池版本发布后 24 小时内多个项目中 `W-REF-001` 警告激增；CI 仪表板上可见的跨项目验证失败率峰值。

**回退方案：** 资产池维护者恢复或重命名资产；若资产池资产携带 `supersedes:` 链接，订阅者的 `references:` 条目将自动跟随重命名。对于灾难性破坏性版本：`engram pool rollback <name> --to=<prev-rev>` 将整个资产池回滚到先前版本。

### 11.4 陷阱 4 — 并发写入损坏

**触发场景：** 两个 CLI 调用（或 CLI 进程、MCP 服务器进程和 Web UI 进程）同时写入同一资产。非原子性的部分写入导致 YAML 前置数据截断或图数据库与文件系统不同步。

**症状：** YAML 前置数据格式错误（下次读取时解析错误）；资产文件截断；`graph.db` 索引条目与磁盘上的文件内容不再匹配。

**根本应对：**

- **原子重命名模式（DESIGN §3.1）：** 所有写入遵循"写入临时文件 → fsync → 重命名"流程；重命名在 POSIX 下是原子性的，保证读取者始终看到完整文件。
- **`fcntl` 独占锁（DESIGN §3.8）：** 所有变更操作均获取 `.engram/.lock`；第二个尝试获取锁的进程会阻塞而非竞争。
- **SQLite WAL 模式（DESIGN §3.2）：** `graph.db` 通过 WAL 允许并发读取并序列化写入；读取路径无需手动加锁。
- **资产写入的乐观并发：** 写入路径记录文件读取时的 sha256；若提交时 sha256 已更改，操作在重新加载后重试。
- **仅追加日志（不变量 §8.1 #9）：** 日志从不重写，仅追加；并发写入无法损坏日志。

**监控信号：** 日志单调计数器不连续；`graph.db` 完整性检查失败（`PRAGMA integrity_check`）；`engram validate` 发现资产文件的 mtime 比 graph.db 索引条目晚超过 2 秒时钟偏差容忍度。

**回退方案：** `engram graph rebuild` 从文件系统完整重建索引（文件系统具有权威性）；任何歧义以文件系统内容为准。最后手段：`engram snapshot restore <snapshot-id>` 恢复到先前备份快照。

### 11.5 陷阱 5 — 循环订阅

**触发场景：** 资产池 A 订阅资产池 B 以获取共享规范；维护者后来让资产池 B 订阅资产池 A 以获取另一组共享内容。订阅图现在包含一个环路。

**症状：** 无限传播循环；`engram pool sync` 期间图遍历不终止；同步守护进程消耗 100% CPU 直到被终止。

**根本应对：**

- **订阅时的环路检测：** `engram pool subscribe` 在写入 `pools.toml` 之前深度优先遍历拟议的订阅图；若检测到环路，命令以 `E-POOL-004 circular_subscription` 拒绝，不写入任何更改。
- **图完整性强制执行（DESIGN §3.2 subscriptions 表）：** 定期完整性作业在 subscriptions 表上断言 DAG 属性；任何环路均为告警级别。
- **传播迭代上限：** 传播守护进程拒绝处理单个传播链中超过 10 跳的情况，为绕过 DAG 检查的 bug 提供硬性安全网。

**监控信号：** 订阅图深度 > 5 跳通常表明设计问题；CLI 在订阅时深度超过此阈值时发出 `W-POOL-002` 警告。

**回退方案：** 对一个参与者执行 `engram pool unsubscribe <pool>` 立即打破环路；操作员重构资产池层次结构并以正确方向重新订阅。

### 11.6 陷阱 6 — 嵌入漂移

**触发场景：** 用户升级配置的嵌入模型（例如 `bge-reranker-v2-m3` → `v3`）。由旧模型生成的缓存向量与新模型的查询在维度或语义上不兼容。

**症状：** 检索质量静默下降；相关性门控对熟悉的查询返回错误或不相关的资产；用户数天内未发现，因为降级是渐进的而非硬性错误。

**根本应对：**

- **嵌入模型版本戳（DESIGN §3.3 `cache/embedding/version`）：** JSON 文件存储 `{model_name, version, embed_date}`；每次查询操作在使用缓存前检查与当前配置的匹配性。
- **版本不匹配时完整缓存重建：** 不匹配自动触发后台重建；进度显示在 `engram review` 中；旧缓存保留在 `.bak` 位置，直到新缓存完成并验证。
- **按资产 sha256 重嵌入检查：** 重建期间，仅对自上次索引以来内容 sha256 已更改的资产重新嵌入，最小化 LLM 提供商成本。

**监控信号：** 配置变更后嵌入缓存命中率突然下降；相关性门控报告查询的 top-K 余弦分数异常低（平均低于 0.4，而此前高于 0.7）。

**回退方案：** `engram cache rebuild --embedding` 强制从头完整重建。若新模型效果更差，`engram config set embedding.model=<prev>` 后重建可回退到先前模型。最坏情况：`engram config set embedding.enabled=false` 完全禁用嵌入缓存，回退到纯 BM25 检索（相关性门控离线模式，§5.1.7）。

### 11.7 陷阱 7 — 跨范围引用导致的隐私泄漏

**触发场景：** 私有项目记忆引用了 `pool/secret-rotation-schedule`（一个包含敏感运维数据的团队内部资产池资产）。项目仓库后来被公开。引用文本或渲染的 wiki 链接暴露了资产池内容。

**症状：** 私有资产池的敏感内容通过公开仓库或公开 engram 导出的 wiki 链接渲染泄漏。

**根本应对：**

- **显式跨范围引用声明（SPEC §3.3 MUST 3）：** 任何跨越范围边界的 `references:` 条目必须在前置数据中声明；未声明的跨范围引用被 `engram validate` 捕获为 `E-MEM-007`。
- **跨范围发布防护（DESIGN §9.6）：** `engram pool publish` 扫描资产池资产中指向 `scope: project` 或 `scope: user`（私有范围）的 `references:` 条目，除非显式传递 `--allow-private-refs` 否则拒绝发布。
- **项目共享防护：** `engram export --format=markdown` 在导出的项目包含未清除共享授权的团队、组织或资产池范围引用时发出警告。

**监控信号：** 任何资产的 `references:` 列表在没有显式 `--allow-cross-scope` 确认标志（记录在 `graph.db` 中）的情况下跨越范围边界。

**回退方案：** 删除或重定向跨范围引用；若引用内容确实可安全共享，将源资产池资产的范围更新为 `public` 并重新发布。

### 11.8 陷阱 8 — LLM 幻觉订阅

**触发场景：** LLM 编写的记忆资产在正文中写道"此项目订阅资产池 kernel-work"。`pools.toml` 中不存在此类条目。后续 LLM 会话读取正文并相信该声明，期望来自该资产池的资产存在。

**症状：** 记忆正文声明项目不具备的能力或资产池成员资格；后续会话中的 LLM 基于声明的订阅行动；用户根据 LLM 相信的声明看到意外的上下文注入或缺失的上下文。

**根本应对：**

- **仅前置数据具有订阅权威性（SPEC §8.2）：** 资产池订阅仅存在于 `pools.toml` 中；正文文本对订阅状态不具权威性，从不被解析为订阅声明。
- **验证规则 `E-MEM-008 phantom_subscription`（DESIGN §5.2）：** `engram validate` 扫描记忆正文中匹配"订阅了"、"资产池成员"等模式的内容；与 `pools.toml` 交叉检查；若声明与实际情况不符则发出错误。
- **LLM 编写纪律（METHODOLOGY.md）：** LLM 编写指南明确教导资产池成员声明只属于 `pools.toml`，永远不属于正文散文。
- **审阅 UI 高亮：** `engram review` 以独特的视觉样式渲染引用资产池名称的正文文本，提示人工审阅者与实际订阅进行核对。

**监控信号：** 验证输出中出现 `E-MEM-008` 命中；用户在询问 LLM 项目上下文时对实际订阅了哪些资产池感到困惑的报告。

**回退方案：** 若声明的订阅是有意为之，运行 `engram pool subscribe <name>` 使其成真。若是错误的，更新幻觉记忆正文以删除该声明，并运行 `engram validate` 确认干净。

### 11.9 横切防御摘要

本章中的许多陷阱共享通用的底层防御措施，使各个缓解措施可以组合：

- **记录一切（不变量 §8.1 #9）：** 所有变更操作后均可观察；为陷阱 1、4 和 8 提供取证重建能力。
- **禁止自动变更（不变量 §8.1 #3）：** 智能层提出建议；人类确认；防止陷阱 2 和 8 导致静默损坏。
- **跨进程安全性（不变量 §8.1 #12）：** 加锁 + 原子重命名 + WAL；陷阱 4 的机械基础。
- **验证优先流水线（§12）：** 每个读取记忆的 `engram` 命令在执行前都运行结构性和语义验证；在最早时刻发现陷阱 3、5、7 和 8。

修复一个陷阱的防御措施不会削弱另一个陷阱的防御，因为每种防御都在不同层面运作（文件系统、图、验证规则、传播守护进程）。添加新功能的工程师应将其映射到此表，并验证不会引入这 8 种模式的新实例。

---

## 12. 与替代系统的对比

### 12.0 前言

本节将 engram 与八个替代系统进行对比。目的是工程层面的清晰认知，而非市场推广。每个竞品都解决了记忆/上下文问题的一个明确子集；对比表映射各自覆盖的子集、其已发布的约束条件，以及 engram 设计决策的差异所在。

本节的基本规则：

1. 仅引用已发布的属性。不作"engram 比 X 更快"之类的声明，除非有基准测试数据支撑。不作"X 无法做 Y"之类的声明，除非引用 X 自身的文档。
2. 凡 engram 借鉴竞品之处，均明确标注（§12.3）。
3. 凡 engram 与竞品存在差异之处，以设计目标来解释差异，而非宣称优越性。
4. 所有竞品 URL 和能力描述反映截至 2026 年 4 月公开可获取的信息。

### 12.1 对比表

下表在 13 个维度上评估 8 个系统。单元格保持 ≤20 个字符：✅ = 是/已实现，❌ = 否/未实现，"partial" = 部分实现或有附加条件，简短限定词说明具体情况。

| 维度 | engram v0.2 | claude-mem | basic-memory | Karpathy LLM Wiki | mem0 | MemGPT / Letta | ChatGPT Memories | MemPalace |
|---|---|---|---|---|---|---|---|---|
| **存储格式** | Markdown + TOML | SQLite / ChromaDB | Markdown | Markdown（手动） | 托管数据库 | 托管 / SQLite | 托管（不透明） | Markdown |
| **工具无关性** | ✅ | ❌ 仅 Claude | ✅ | ✅ 方法论 | ❌ 按提供商 API | partial（LLM-as-OS） | ❌ 仅 ChatGPT | partial |
| **本地优先** | ✅ | ✅ | ✅ | ✅ | ❌ 云端锁定 | partial | ❌ 托管 | ✅ |
| **作用域 / 层级模型** | ✅ 双轴模型 | ❌ | ❌ 单层级 | ❌ | ❌ | ❌ | ❌ | ❌ |
| **显式强制执行** | ✅ mandatory/default/hint | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **一致性检测** | ✅ 7 类分类体系 | ❌ | ❌ | ❌ | partial（去重） | partial（去重） | partial（去重） | ❌ |
| **可执行工作流（spine）** | ✅ | ❌ | ❌ | ❌ | ❌ | partial | ❌ | ❌ |
| **知识库（多章节）** | ✅ | ❌ | partial（wiki 链接） | ✅ 方法论 | ❌ | ❌ | ❌ | ❌ |
| **Web UI（一等公民）** | ✅ | ❌ | ❌ | ❌ | ✅ 托管仪表板 | partial | ✅ | ❌ |
| **MCP 协议服务器** | ✅ | partial | ❌ | ❌ | partial | ❌ | ❌ | partial |
| **跨仓库收件箱** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **量化自我改进** | ✅ 4 条智慧曲线 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | partial（LongMemEval） |
| **开源** | ✅ | ✅ | ✅ | ✅（gist） | partial（SDK 开源） | ✅ | ❌ | ✅ |

**说明：** engram 是本表中唯一同时满足本地优先、工具无关、多作用域显式强制执行，并将一致性检测、可执行工作流、跨仓库协作作为一等原语的系统。

### 12.2 各系统简要评估

**claude-mem** — Claude Code 的原生记忆层。优势：与 Claude Code 深度集成，无需用户配置即可工作，会话期间自动捕获记忆。局限性：仅限 Claude（无其他 LLM 或 IDE 适配器），SQLite/ChromaDB 后端对 Claude Code 以外的工具不透明，无跨项目作用域模型，无一致性引擎，无 Workflow 资产类。engram v0.2 设计为其超集：engram 的 Claude Code 适配器生成与原生 Claude Code 记忆共存的 `CLAUDE.md` 文件。用户可通过 `engram migrate --from=claude-code` 迁移（SPEC §13.4）。

**basic-memory**（github.com/basic-machines-co/basic-memory）— 基于 Markdown 的记忆系统，配有 wiki 链接图导航。优势：可移植的纯文本，本地优先，git 友好，无需工具即可人工阅读。局限性：单层级（无作用域/强制执行模型），无一致性引擎，无 Workflow 资产类，单用户模型，无跨仓库原语。engram 认同其可移植性理念（所有资产均为可读 Markdown），并在此基础上扩展了多层级作用域、强制执行语义和智能层。

**Karpathy LLM Wiki** — 一种方法论，而非产品（以 gist/演讲形式发布）。优势：展示了人工撰写、LLM 编译的知识库的复利价值；证明结构化整理随时间推移优于原始检索。局限性：无工具支持；操作者需手动维护一切；无强制执行、一致性检测或自动化演进。engram 的 KB 资产类（SPEC §6，`_compiled.md` 合约）通过自动化编译工具直接将这一理念产品化。

**mem0**（mem0.ai）— 托管代理记忆服务，采用嵌入 + 知识图谱检索。优势：零配置，通过混合嵌入 + 图谱实现强检索，按用户隔离记忆。局限性：云端锁定（用户不拥有数据），使用量计费，按提供商 API（存储层非工具无关）。engram 是需要数据所有权的团队的本地优先替代方案。用户可通过 `engram migrate --from=mem0` 导入。

**MemGPT / Letta**（letta.com）— 将记忆视为操作系统虚拟内存，使用 LLM-as-OS 抽象在上下文窗口和外部存储之间分页信息。优势：优雅的分层隐喻，能很好地处理长上下文；清晰的分页合约。局限性：绑定 Letta 运行时（LLM-as-OS 框架）；无多作用域模型；无一致性引擎；无 Workflow 资产类；外部存储非文件系统原生 Markdown。engram 从 MemGPT 借鉴了 L0–L3 分层隐喻（DESIGN §5.1），但将所有资产保持为无需运行时即可访问的文件系统原生 Markdown 文件。

**ChatGPT Memories** — OpenAI 为 ChatGPT 会话提供的个人记忆功能。优势：在 ChatGPT UI 中无缝集成，用户零配置。局限性：仅限 ChatGPT（非工具无关），托管且无导出路径，用户无法检查或版本化其记忆，无作用域/强制执行/一致性模型。engram 是需要数据所有权和跨工具可移植性的用户的开放、可移植对应方案。

**MemPalace**（github.com/MemPalace/mempalace）— 逐字对话存储，配有 Zettelkasten 结构和 Claude Code 钩子集成。优势：在 LongMemEval 上 R@5 达 96.6%（见已发布的 BENCHMARKS.md），本地优先，Claude Code 钩子，git 可差异比较存储，混合检索结合 BM25 + 向量 + 时序信号 + 两阶段重排序。局限性：针对逐字记录存储优化，而非精心整理的结构化知识；无 Workflow 资产类；无多作用域强制执行；无跨仓库收件箱；单作用域模型。engram 直接采用 MemPalace 的混合检索算法（修正案 B §B.2，DESIGN §5.1）及其 BENCHMARKS.md 测量规范，并弥补了 MemPalace 未针对的结构化知识 + 多作用域 + 强制执行缺口。

### 12.3 engram 从各系统借鉴的内容

| 来源 | engram 借鉴内容 | engram 中的位置 |
|---|---|---|
| Karpathy LLM Wiki | 人工撰写 + LLM 编译的 KB 模式；整理优于原始检索原则 | SPEC §6 |
| autoresearch（Karpathy） | 棘轮循环 + 工作流演进的 8 个规范 | DESIGN §5.3 |
| Agent Factory | Workflow = 文档 + 可执行 spine（将经验编码化） | SPEC §5, DESIGN §5.3 |
| evo-memory | 搜索→合成→演进生命周期；ReMem 行动-思考-精炼循环 | DESIGN §5.4 |
| MemoryBank | Ebbinghaus 启发的置信度衰减（基于证据的遗忘曲线） | SPEC §4.8, §11 |
| MemGPT / Letta | 记忆分层隐喻（L0–L3 唤醒栈） | SPEC §7, DESIGN §5.1 |
| Claude Code memory | 直接前身；子类型 + 前置数据模式；会话记忆捕获 | SPEC §4 |
| MemPalace | 混合检索（BM25 + 向量 + 时序 + 两阶段重排序）；BENCHMARKS.md 规范 | DESIGN §5.1, benchmarks/ |
| Darwin.skill | 自动学习棘轮（git 原生）+ 双重评估 + 独立评判 + 阶段门控 | DESIGN §5.3 |
| Nuwa.skill | `limitations:` 前置数据字段（诚实的边界声明） | SPEC §4 |
| `npx skills add` 约定 | 剧本安装 URL 方案 | SPEC §4, DESIGN §6 |

以上所有 11 项借鉴均明确标注，而非隐式引用。凡 engram 的实现与来源有所不同之处（例如 MemPalace 的检索被适配至 engram 的多作用域图而非平面索引），差异均在所引用章节中说明。

### 12.4 engram 独有的新增内容

以下功能在 §12.1 评估的八个系统中均未单独或组合出现：

1. **双轴作用域模型** — 成员资格层级（用户 → 项目 → 团队 → 组织）结合正交资产池订阅 — SPEC §8。所评估的系统中没有任何一个同时实现两个轴。
2. **具有确定性冲突解决的显式 `enforcement` 语义** — mandatory/default/hint 三级，配有定义的优先级顺序和覆盖审计轨迹 — SPEC §8.3–8.4。
3. **三种独立的资产类** （Memory / Workflow / Knowledge Base），各有独立的格式、生命周期规则和作者模型 — SPEC §3。竞品将所有存储内容视为无差别的记忆。
4. **七类一致性分类体系** — 七种命名的矛盾/过时类型，配有"建议，绝不变更"合约 — SPEC §11。
5. **跨仓库收件箱** — 跨仓库边界的点对点代理协作，支持优先级排序和结构化确认 — SPEC §10。
6. **量化自我改进** — 四条智慧曲线（记忆健康评分、工作流适应度、KB 新鲜度、作用域一致性），配有自动化回归检测 — DESIGN §5.6。
7. **一等公民观测层** — Web UI 配有上下文预览调试页面，供人工在会话开始前检查 LLM 将看到的内容 — DESIGN §7。

这七项属性的组合，使 engram 成为本对比中第一个同时满足可移植性（所有资产均为纯 Markdown，无运行时锁定）、智能性（一致性引擎 + 自动学习 + 演进流水线）和多作用域性（双轴成员资格 + 订阅，配有显式强制执行）的系统。

---

## 13. 非 MVP 范围边界

### 13.0 目的

本章明确列出 v0.2 中包含哪些内容、不包含哪些内容。对于需要判断某功能是否属于 v0.2 里程碑的实现者，以及对正式承诺有明确预期的用户而言，本章消除了模糊性。条目按四个层级分组：

- **P0** — 必须在 v0.2.0 标签发布时完成。未完成的工作是发布阻断项。
- **P1** — 目标为首轮发布后（v0.2.1 至 v0.3.0）。已完整规划；不阻断发布。
- **P2** — 未来考虑。列出以避免日后重复设计；无里程碑承诺。
- **Non-goals（非目标）** — 永久超出范围的设计性排除项。这些是有意的排除，而非积压工作。

### 13.1 P0 — v0.2 开源发布（M1–M7 里程碑）

以下组件必须在打出 v0.2.0 标签前完成并通过测试。

| 组件 | 范围 | 章节 |
|---|---|---|
| 第 1 层数据格式 | 完整 SPEC §1–§14 合规 | SPEC |
| 第 2 层 CLI 核心 | `init / status / version / config / review / validate / migrate --from=v0.1 / memory（完整） / pool（subscribe/publish/sync/list/unsubscribe） / team（完整） / org（完整） / inbox（完整） / context pack/preview / graph rebuild / cache rebuild / archive list/restore / snapshot create/list/restore / export` | §4 |
| 第 3 层智能——部分 | Relevance Gate 完整；Consistency Engine 第 1 阶段（静态）+ 第 2 阶段（语义聚类）；Inter-Repo Messenger 完整 | §5 |
| 第 4 层接入 | Claude Code + Codex + Gemini CLI + Cursor + raw-api 适配器；MCP 服务器含读取 + 收件箱工具；prompt pack；Python SDK 基础 | §6 |
| 第 5 层观测——子集 | Web UI 页面：Dashboard、Memory Detail、Workflow Detail（仅查看）、KB Article（只读）、Inbox、Context Preview — 共 11 页中的 6 页 | §7 |
| 基准测试 | `benchmarks/consistency_test/` + `benchmarks/scope_isolation_test/` 自建套件 | 修正案 B §B.3 |

所有 P0 条目映射到 `TASKS.md` 中的 M1 至 M7 里程碑。当某条目的单元测试通过、集成测试通过，且其出现在 CLI `--help` 输出中或可通过 §6 中文档化的 MCP 服务器访问时，视为完成。

### 13.2 P1 — v0.2 发布后首轮（MVP 后 M5–M8）

以下功能已完整设计，将在首轮发布后的开发周期中推进。它们不阻断 v0.2.0，但预期在 v0.3.0 之前落地。

| 组件 | 范围 | 章节 |
|---|---|---|
| Workflow 资产 + Autolearn Engine | 完整 spine 执行 + Darwin 棘轮 + 阶段门控 + 独立评判 | §5, DESIGN §5.3 |
| Knowledge Base + 编译 | 完整 `_compiled.md` 生成 + 过期检测 | §6, DESIGN §6.2 |
| Consistency Engine 第 3 阶段 | LLM 辅助审查（可选，按配置 opt-in） | DESIGN §5.2 |
| Consistency Engine 第 4 阶段 | 工作流夹具执行验证 | DESIGN §5.2 |
| Evolve Engine | 用于记忆资产精炼提案的 ReMem 循环 | DESIGN §5.4 |
| Pool propagation 完整 | notify + pinned 模式，超越自动同步 | SPEC §9, DESIGN §5.2 |
| Web UI 剩余 5 页 | Graph（D3 力导向布局）、Pools、Project Overview、Wisdom、Autolearn Console | §7 |
| TypeScript SDK | Python SDK 的 `@engram/sdk` 镜像 | §6 |
| Wisdom Metrics 仪表板 | 完整 4 条曲线 + 回归告警 | DESIGN §5.6 |
| 额外迁移来源 | chatgpt、mem0、obsidian、letta、mempalace、markdown | SPEC §13.6 |
| Playbook pack/install | `engram playbook` 命令族 | SPEC §4, DESIGN §6 |

P1 条目在 `TASKS.md` 的 `v0.3.0` 里程碑中跟踪。每项的设计均已稳定；实现在 v0.2.0 打标签后开始。所有 P1 条目均不需要规格变更——所有格式和合约均已在 SPEC.md 中定义。

### 13.3 P2 — 未来考虑（尚无里程碑）

以下想法值得记录，以避免将来重复设计。它们未承诺于任何发布，可能被取代或放弃。列入 P2 并不意味着其会最终实现。

- **多机同步守护进程** — 超越 rsync/git 的 `~/.engram/user/` 跨设备同步（可能基于 CRDT）。当前设计假设单一主机；多机使用仅通过手动 git 同步支持。
- **本地小模型重排器** — Relevance Gate 中基于设备端模型的可选 LLM 重排步骤（当前仅使用 cross-encoder）。在不经过云端往返的情况下提升检索质量，但需要硬件性能剖析。
- **Obsidian 插件** — 用于从 Obsidian 编辑 `.memory/` 并进行实时校验的官方插件。磁盘格式已与 Obsidian 兼容；这是一个 UI 层扩展。
- **IDE 深度集成** — 用于内联 Memory 创作 + 编辑器边栏一致性告警的 VS Code 扩展。优先级低于 CLI 和 Web UI。
- **多语言嵌入** — 面向非英语 Memory 检索的非英语嵌入模型。嵌入模型可插拔（见 §5.1）；这是一项配置和文档任务。
- **协作编辑** — 当两个人类 + 两个代理几乎同时编辑同一资产时的结构化合并。v0.2 假设同一时间只有单一写入者；冲突通过 Consistency Engine 升级给人类处理。完整的 OT 或 CRDT 合并是独立项目。
- **运行时一致性强制执行** — 实时（而非事后）拦截 LLM 操作，以阻断违反活跃 `enforcement=mandatory` 规则的输出。需要 v0.2 中不存在的代理或钩子层。
- **联邦池** — 用于发现社区池的池注册服务，超越原始 GitHub URL 安装。需要本地优先设计范围之外的可信注册基础设施。

### 13.4 非目标 — 永久超出范围

以下是设计性排除项。它们不会被添加到任何积压列表。如果贡献者在 PR 中提出以下任一项，回应是指向本节的链接，而非"也许以后"。

- **云/SaaS 服务。** engram 是本地优先的。我们不会建立用户将数据存储在 Anthropic 或任何第三方服务器上的托管版 engram。如果其他人基于开放格式构建此类服务，那是他们的项目，而非本项目。
- **移动应用。** 当前 Web UI 面向桌面浏览器。没有原生移动应用。从移动浏览器进行只读浏览可能偶然可用，但这不是受支持的目标，也不会获得移动端专项设计投入。
- **专有模型捆绑。** engram 不随附或要求任何特定 LLM。Relevance Gate 使用本地嵌入模型（默认 bge-reranker-v2-m3）——这些模型是可选的且可由用户替换。我们不会打包或重新分发任何专有模型权重。
- **自动运行时代码生成。** engram 不生成或修改 LLM 推理代码。Workflow 使用操作者创作的 spine（或 Autolearn 从操作者创作的基线演进而来）；我们不提供在没有人类参与的情况下生成可执行代码的 LLM 端自动化。
- **跨仓库锁管理器。** Inbox 基于消息（异步、尽力而为）。我们不保证跨仓库的分布式锁或一致的顺序。分布式协调是操作者的职责；请使用 git 或外部协调原语。
- **实时操作转换。** 两个用户同时编辑同一 Memory 资产的情况足够罕见，我们使用文件系统原子重命名 + 乐观并发 + 冲突升级给人类的方式处理。我们不会为 Memory 内容添加 CRDT 或 OT。其复杂性不值得为使用频率投入。
- **自动解决一致性提案。** Consistency Engine 的不变量是"建议，绝不变更"（DESIGN §5.2，SPEC §11）。自动化解决将违反此合约并破坏用户对系统的信任。没有例外，即使对于明显安全的情况也不行。
- **游戏化。** 没有连胜、没有经验值、没有任务、没有排行榜。Wisdom Metrics 的存在是为了提供系统健康信号，而非驱动用户参与。添加参与性机制会污染信号，并与设计前提——人类是作者，而非玩家——相矛盾。

---

**DESIGN v0.2 草稿完成。** 章节 §0 至 §13 涵盖完整的 5 层架构、智能层合约、接入路径、观测层、源码结构、测试、陷阱及范围边界。配套文档：

- [`SPEC.md`](SPEC.md) — 磁盘格式合约（v0.2 完整）
- [`METHODOLOGY.md`](METHODOLOGY.md) — LLM 应如何撰写记忆（待补充）
- [`TASKS.md`](TASKS.md) — 里程碑与任务看板（待补充）
- [`docs/glossary.md`](docs/glossary.md) — 权威术语表

本草稿之后的设计变更须通过 PR + GitHub Discussions 页面的设计评审。
