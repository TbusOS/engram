[English](SPEC.md) · [中文](SPEC.zh.md)

# engram 记忆系统规范

**版本**: 0.2（草案）
**状态**: 公开征求意见
**最后更新**: 2026-04-18
**权威版**: https://github.com/TbusOS/engram/blob/main/SPEC.md
**术语表**: [docs/glossary.zh.md](docs/glossary.zh.md) — 本文档中所有术语遵循该表

---

<!-- engram glossary lock: 本文档所有术语必须与 docs/glossary.zh.md 一致 -->

## 0. 目的

engram v0.2 是一个本地、可移植、不绑定任何 LLM 的记忆系统，目标是成为**业界最好的开源永久记忆系统**，服务于任何在 LLM 之上进行构建的开发者。版本号本身就是一种方向声明：本文档中的每一个设计决策，都是为了弥合今天生态系统现状与一个严肃记忆系统所应具备能力之间的差距。

现有系统——claude-mem、basic-memory、Karpathy 的 LLM Wiki、mem0、MemGPT、Letta、ChatGPT Memories——各自解决了问题的某一个切面。但没有任何一个系统同时做到以下五点：

1. **LLM 优先，工具无关。** 任何模型，无论本地还是云端，都以同样的方式读取 `.memory/` 目录。不需要专有 SDK，不需要托管端点，不存在厂商锁定。
2. **对人可观察。** 一流的 Web UI 让你看到完整的知识图谱、每个资产随时间的演化过程，以及在任何给定任务下 LLM 实际会加载什么——在它加载之前就能看到。
3. **团队与组织共享而不相互污染。** 两轴 Scope 模型（四级归属层级加上正交的主题池）配合显式的 `enforcement` 语义（`mandatory` / `default` / `hint`），让知识流到它应该去的地方，并在它不应越过的边界处停止。
4. **三类资产，不止 Memory。** 用于 LLM 预热的短篇记忆（Memory）；包含文档、可执行 spine、fixtures、metrics 及版本历史的中篇工作流（Workflow）；由人撰写、LLM 编译摘要的长篇知识库文章（Knowledge Base）。每类资产有独立的格式、生命周期和加载路径。
5. **可量化地变聪明。** 四组定量智慧指标曲线（工作流掌握度、任务复现效率、记忆策展比率、上下文效率）提供了系统持续自我改进而非单纯积累的证据。

质量的维护不是通过设置容量上限，而是通过**一致性引擎**：它在整个存储库中检测七类冲突——`factual-conflict`（事实冲突）、`rule-conflict`（规则冲突）、`reference-rot`（引用失效）、`workflow-decay`（工作流衰变）、`time-expired`（时间过期）、`silent-override`（静默覆盖）、`topic-divergence`（同题分歧）——并提出而非自动执行修复建议。删除操作从不静默发生；一切删除都通过 `archive/` 路径进行，物理删除前的保留期下限为六个月。

跨项目和跨团队的知识协调通过两种互补机制实现：主题池（共享的 `~/.engram/pools/<name>/` 目录，配合显式的 `subscribed_at` 声明将每个 pool 定位到归属层级中）和跨仓传信器（位于 `~/.engram/inbox/<repo-id>/` 的点对点收件箱，用于仓库之间的直接通信）。二者合力，使 engram 能够服务于不同规模的团队，而无需对所有人强制同一种共享模式。

### 文档范围

本文档 `SPEC.md` 定义 engram 记忆存储的**磁盘格式**：目录布局、文件命名、YAML frontmatter 模式、校验规则、版本控制，以及兼容性契约。它是格式决策的权威来源；对任何字段、命名规则或结构不变量的破坏性变更都必须升级主版本号。

配套文档覆盖系统的其余部分：

- **`DESIGN.md`** — 第 2 至第 5 层的实现：CLI 架构、智能层组件、接入层适配器与 MCP 服务，以及观察层 Web UI。
- **`METHODOLOGY.md`** — LLM 应如何撰写、演化和退役记忆资产：让存储库持续变聪明的行为纪律。

本文档刻意不涉及 LLM 应在何时写入记忆、相关性闸门如何给候选资产打分，或自学习引擎如何演化工作流。这些属于设计和方法论关注点，不属于格式关注点。

### 目标读者

将本文档加载进上下文的任何 LLM 代理、实现 engram 兼容读写器的任何工具作者，以及任何希望理解磁盘上存储了什么以及为何如此设计的人。

读完本文档，LLM 应能回答：什么样的文件集合构成一个合法的 engram 存储库？每种资产类型需要哪些 frontmatter？`enforcement: mandatory` 在冲突解决中意味着什么？读完本文档，工具作者应能实现一个校验器：接受所有合法存储库，拒绝所有非法存储库，无需参考任何其他文档。

### 关于 v0.1 兼容性的说明

v0.1 存储库——使用三层架构（适配器 / CLI / 数据），四种 Memory 类型（`user`、`feedback`、`project`、`reference`），不含 scope 模型——在 v0.2 下是合法存储库，解释如下：所有现有文件视为 `scope: project`，所有 `feedback` 文件隐含 `enforcement: default`，缺失的 `MEMORY.md` 格式字段使用默认值填充。完整迁移契约在 §13 中规定。

---

## 1. 范围

本文档范围限于五层架构中的第 1 层数据层关注点。第 2 至第 5 层（控制层、智能层、接入层、观察层）在 `DESIGN.md` 中规范，在此刻意排除，使格式契约在无论使用何种智能层或接入层实现的情况下都保持稳定。符合本文档的存储库，可以与任何兼容的 CLI、任何兼容的适配器、任何兼容的智能层一同运作——或者完全不需要任何这些组件。

### 范围内

以下主题在本文档中有完整规范。engram 兼容工具必须正确实现所有范围内的条目。本文档中的"必须（MUST）"遵循 RFC 2119 约定。

- **目录布局。** 项目级 `.memory/` 层级结构和用户全局 `~/.engram/` 层级结构，包括子目录名称及其语义。
- **文件命名与 YAML frontmatter 契约。** 每种资产类型的必填字段和可选字段、数据类型，以及向前兼容规则（工具在重写时必须保留未知字段）。
- **六种 Memory 子类型及其正文约定。** `user`（用户型）、`feedback`（反馈型）、`project`（项目型）、`reference`（引用型）、`workflow_ptr`（工作流指针）、`agent`（代理元指令）六种子类型，各有其用途、必填 frontmatter 和正文结构。子类型与 scope 正交。
- **Workflow 资产格式。** `workflow.md` 文档、`spine.*` 可执行文件、`fixtures/` 测试用例、`metrics.yaml` 结果跟踪器，以及 `rev/` 写时复制版本历史。
- **Knowledge Base 资产格式。** `articles/` 源文件目录、`assets/` 二进制附件目录，以及 `_compiled.md` LLM 生成摘要。
- **MEMORY.md 分层 landing 索引。** 格式、分组、排序、行长限制，以及每个资产文件必须出现在索引中的规则。
- **两轴 Scope 模型。** 四级归属层级（`org` > `team` > `user` > `project`）和正交的订阅轴（`pool`，由 `subscribed_at` 定位）。冲突解决规则。Enforcement 语义。
- **Pool 传播模式。** 三种订阅者模式——`auto-sync`（自动同步）、`notify`（通知式）、`pinned`（钉版）——以及决定 pool 对特定订阅者有效层级的 `subscribed_at` 字段。
- **跨仓 inbox 消息协议。** `~/.engram/inbox/<repo-id>/` 的目录布局、消息 frontmatter 字段、五种 `intent` 值（`bug-report`、`api-change`、`question`、`update-notify`、`task`），以及 `acknowledged`（已确认）/ `resolved`（已解决）生命周期。智能层的跨仓传信器组件实现投递和路由逻辑；本文档只规范消息格式和目录契约。
- **一致性契约。** 一致性引擎检测的七类冲突、为其证据模型提供数据的置信度字段（`validated_count`、`contradicted_count`、`confidence_score`、`staleness_penalty`），以及引擎永不自动 mutate 资产的不变量。四阶段扫描算法属于 `DESIGN.md` 的内容；引擎不得 mutate 的契约在此固定。
- **校验规则与错误码表。** 结构、内容、索引、符号链接、时间、scope 和一致性校验规则，每条规则附机器可读错误码。
- **版本控制与 v0.1 → v0.2 迁移契约。** `.engram/version` 文件、语义化版本升级规则，以及 v0.1 存储库的逐字段迁移指南。

### 范围外

以下主题明确推迟到其他文档处理。以与这些文档不一致的方式实现它们是项目错误，但不在本文档的关注范围内。

- **CLI 用户界面与命令设计。** `engram memory add` 接受哪些参数、`engram consistency scan` 如何渲染报告、`engram review` 输出格式是什么样的——这些是 `DESIGN.md` 的主题（第 2 层）。
- **Embedding 算法与模型选型。** 相关性闸门使用 BM25、bge-reranker-v2-m3 还是托管 re-ranker，这是运行时关注点，在 `DESIGN.md` 和适配器指南中规定。本文档不要求也不禁止任何 embedding 策略。
- **LLM 撰写纪律。** 何时写入记忆、如何措辞、何时将 `draft`（草稿）提升为 `active`（活跃）、演化引擎多久提出一次修订建议——参见 `METHODOLOGY.md`。
- **Web UI 页面设计与交互模式。** 上下文预览模拟、自学习控制台、池管理界面、知识图谱力导向布局——参见 `DESIGN.md §7`。
- **一致性引擎算法。** 四阶段扫描序列、评分权重、建议排序——参见 `DESIGN.md §5`。本文档只固定冲突分类法、七类名称，以及非 mutate 不变量。
- **剧本打包与分发。** 可分发的 Playbook 包格式（`engram playbook pack`）——推迟到待 schema 稳定后的未来 SPEC §15。

---

## 2. 设计哲学与差异化

以下五条原则是设计公理，而非愿景声明。每条原则都对本文档后续决策产生具体影响："永不自动删除"原则是 `archived`（已归档）和 `tombstoned`（已删除）生命周期状态存在的原因；"证据驱动演化"原则是 `validated_count` 和 `confidence_score` 成为 Memory 资产必填 frontmatter 字段的原因；"可移植性优于花哨功能"原则是格式采用纯 markdown 而非二进制或图格式的原因。如果后续章节的某个选择看似武断，回溯到这五条原则中的某一条，就能找到解释。

### 核心原则

**原则一：记忆是数据资产，不是产品功能。**

engram 中的每一个设计决策都从同一个前提出发：记忆存储库属于其所有者，而不是写入它的工具。这并不是一个显而易见的立场。大多数 LLM 工具将记忆视为它们提供的一项功能——数据以它们的格式存储在它们的系统中，通过它们的 API 检索。其后果是：换工具意味着失去上下文，放弃一个工具意味着失去多年积累的知识。

engram 将此反转。存储库是一个由纯 markdown 文件加 YAML frontmatter 构成的目录。任何文本编辑器都能打开它。任何 LLM 都无需插件即可读取它。任何版本控制系统都能追踪它。如果 engram 明天被放弃，存储库作为知识库仍然完全可用，面向任何继任工具。工具可替换，数据不可替换。

**原则二：可移植性优于花哨功能。**

在技术上，完全可以构建更复杂的存储格式：带类型化节点和边的图数据库、支持语义搜索的向量存储、亚毫秒读取的二进制格式。engram 刻意选择了这些之外的方案。磁盘格式是 markdown 加 YAML——一种已稳定数十年的组合，人类无需工具即可阅读，可以无修改地通过 git diff、grep、Obsidian、Logseq 以及其他任何文本处理系统。

相关性闸门、一致性引擎和自学习引擎在这个格式之上增加了智能层。但智能层是可选的、可抛弃的。剥离它，存储库仍然运转。格式是永久性的赌注；智能是可组合的投资。在十年尺度的竞争中，可移植性每次都胜过花哨功能。

**原则三：质量优于数量。**

engram 对存储库大小不设硬性限制。磁盘空间便宜，遗忘代价高昂。但无限积累而不策展，会使存储库随时间变得越来越嘈杂：相互矛盾的规则堆积，过期的引用残留，已完成工作的项目记忆占用上下文预算。

答案不是容量上限。容量上限销毁信息并制造任意截断。答案是主动的质量维护：一致性引擎持续扫描七类冲突，并向所有者呈现修复建议。智慧指标将策展比率——存储库中活跃、经过验证、无冗余的资产比例——作为头等健康信号追踪。质量靠证据驱动的策展来维护，不靠强制清退。

**原则四：永不自动删除。**

未经人类或 LLM 的明确决策，资产绝不会从存储库中删除。当一致性引擎或演化引擎提议退役某个资产时，该提议会创建一个 `deprecated`（待退）生命周期标记，并在 `engram review` 中呈现该条目。由所有者做出决定。已接受的退役操作会将文件移动到 `~/.engram/archive/`，物理删除前的保留期下限为六个月。`enforcement: mandatory` 的强制级资产无法被项目级决策归档；归档操作需要在创建该资产的 scope 层级上进行。

这个不变量的存在是因为：错误的退役比错误的添加更难恢复。如果一条记忆是错的，一致性引擎会将其呈现出来供修正。如果它只是过时了，置信分公式中的陈旧惩罚会降低其优先级。没有任何紧急情况需要静默删除。

**原则五：证据驱动演化。**

记忆不只是单纯积累。每次 LLM 根据某个资产采取行动并记录结果，该资产的 `validated_count`（验证次数）或 `contradicted_count`（证伪次数）就会递增。置信分公式——`(validated - 2×contradicted - staleness_penalty) / max(1, total_events)`——产生一个单一数字，汇总存储库的证据对每个资产的支持程度。置信分下降的资产会在 `engram review` 中浮现，供人类决策。持续保持高置信分的资产被提升为 `stable`（稳定），在未来的审查中降低优先级。

这套机制——在术语表中记录为证据驱动演化——汲取了多条先验研究线索。MemoryBank 将艾宾浩斯遗忘曲线应用于 LLM 记忆优先排序。Karpathy LLM Wiki 展示了持久、LLM 编译的知识随时间产生复利价值。autoresearch 的 agent 循环表明，有纪律的自我批评循环能在自动化系统中产生可靠的自我改进。DeepMind 的 evo-memory 搜索-综合-演化框架证明，让记忆系统变聪明的是综合与演化，而不仅仅是检索。engram 将这些融合进一致性引擎、演化引擎和自学习引擎——它们全部运作在本文档定义的纯 markdown 存储库之上，不改变其基础格式。

### 差异化对比

下表将 engram v0.2 与其所要改进的各类系统进行对比。单元格使用 ✅（完全支持）、❌（不支持）或简短说明词（对于部分支持或有条件支持需要上下文的情况）。

| 能力 | engram v0.2 | claude-mem | basic-memory | Karpathy LLM Wiki | mem0 | MemGPT / Letta | ChatGPT Memories |
|---|---|---|---|---|---|---|---|
| 纯 markdown 存储 | ✅ | ❌ SQLite | ✅ | ✅ gist | ❌ 托管 | ❌ 托管 | ❌ 托管 |
| 工具无关（任意 LLM） | ✅ | ❌ 仅 Claude | 部分 | 部分 | 部分 API | 部分 API | ❌ 仅 ChatGPT |
| 两轴 Scope（归属层级 + 池） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 显式 enforcement（mandatory/default/hint） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 一致性检测（7 类冲突） | ✅ | ❌ | ❌ | ❌ | 部分 | ❌ | ❌ |
| 可执行工作流 | ✅ | ❌ | ❌ | ❌ | ❌ | 部分 | ❌ |
| 知识库资产类别 | ✅ | ❌ | ❌ | ✅ 手动 | ❌ | ❌ | ❌ |
| 一流 Web UI | ✅ | ❌ | ❌ | ❌ | 部分托管 | 部分托管 | 部分托管 |
| MCP 服务 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 跨仓 inbox | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 可量化自我改进 | ✅ 智慧指标 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 开源 | ✅ | ✅ | ✅ | ✅ | 部分 | ✅ | ❌ |

engram 做出的差异化押注是一种没有其他系统尝试过的特定组合：数据资产可移植性（你拥有的纯 markdown，任何工具均可读取），加上主动的质量维护（一致性引擎、证据驱动的置信度、证据驱动的策展），再加上可量化的自我改进（智慧指标将"随时间变聪明"从营销声称变成可测量的数据）。大多数系统只选其一：可移植但不维护质量；维护质量但不可移植；托管提供质量但完全不可移植。engram 押注严肃用户三者都需要，而唯一能同时交付三者的架构，就是将格式作为永久承诺、将智能作为其上可组合层的架构。

表格注释："claude-mem"指 v0.2 之前形态的 Claude Code 项目记忆系统（SQLite 存储，仅限 Claude）。"basic-memory"指同名开源项目。"工具无关"行中的"部分"意味着该系统支持多个工具，但格式不开放。"Web UI"行中的"部分托管"意味着存在某种托管仪表板，但与厂商平台绑定。标记为 ❌ 的单元格反映的是该系统的设计意图，而非暂时的缺口——这些是结构性局限，不是路线图上待补的功能。

### 设计灵感

engram v0.2 从多个先行系统中汲取了思路，每个系统都出色地解决了问题的某一部分。

- **Karpathy LLM Wiki** — 证明了持续的、LLM 编译的知识制品会随时间产生复利价值，而这是短暂的聊天上下文所不具备的。engram 将这一点扩展到全部三类资产，并使编译步骤明确、可复现。
- **MemoryBank** — 将艾宾浩斯遗忘曲线应用于 LLM 记忆优先排序。engram 采纳了证据驱动的置信度模型（验证 / 证伪次数 + 陈旧衰减），但将其应用范围从简单的记忆检索扩展到资产生命周期决策。
- **autoresearch** — 表明有纪律的 agent 自我批评循环能在自动化系统中产生可靠的自我改进。自学习引擎对 Workflow 资产的演化循环参考了 autoresearch 的八条纪律周期进行结构化。
- **evo-memory（DeepMind，2025）** — 证明了搜索-综合-演化比单纯检索更强大。一致性引擎的建议周期和演化引擎的 ReMem action-think-refine 循环，是 engram 对这一洞见的具体落地。
- **MemGPT / Letta** — 开创了将记忆视为结构化 OS 式虚拟内存（带分页）的理念。engram 保留了结构化思路，但去掉了托管：存储库在磁盘上，不在托管服务里。

---

## 3. 三类资产

### §3.0 概述

engram v0.2 不是单一资产类型的系统。三类资产——记忆（Memory）、工作流（Workflow）、知识库（Knowledge Base）——存在的原因，是持久化存储中需要承载三种性质截然不同的知识，而将三者强行塞进同一格式，要么产生臃肿的单用途工具，要么产生弱类型的大杂烩，三者都服务不好。

这一区分在撰写、加载和演化三个环节上都有实质影响：

- **LLM 应在每个相关会话中持有的短小断言**属于记忆（Memory）。Memory 资产是一个原子断言——一条可以独立被 supersede 的事实、规则、偏好或指针。它被设计为通过相关性闸门（Relevance Gate）加载到每个相关会话的系统提示词中。
- **必须可执行且可量化的可复用过程**属于工作流（Workflow）。Workflow 资产有一个可运行的 spine、fixture 测试用例和指标跟踪器。仅仅写下步骤是不够的；spine 必须能真正运行，fixture 必须能验证，指标必须能证明过程在随时间改进。
- **人会专门坐下来翻阅的领域参考材料**属于知识库（Knowledge Base）。KB 资产是由人撰写的多章节文档，并附有 LLM 生成的 `_compiled.md` 摘要——当完整文章太长无法直接加载时，摘要可以高效地进入上下文预算。

**资产类别按功能区分，不按尺寸区分。** 任何类别都没有硬性行数限制。一条 300 行的 Memory 资产，只要它编码的是一个独立可 supersede 的断言，它就是 Memory 资产。Workflow 资产始终是 Workflow，不论其 spine 多么简短，因为它承载着可执行性的结构契约。KB 文章是 KB 文章，因为它是人会专程翻阅的参考材料。

尺寸管理以自适应方式处理，而非强加上限。三种信号在不阻塞或警告的前提下，将值得 review 的候选呈现给所有者：**动态预算分配**（Relevance Gate 根据观察到的 utilization rate 动态调整各类型的 token 预算）、**百分位长度信号**（某资产长度达到同类型 95 百分位时，出现在 `engram review` 的"建议 review"列表中）、以及演化引擎（Evolve Engine）的**拆分 / 升级 / 降级建议**（拆分密集记忆、将记忆群升级为 KB 文章、将不再执行的 workflow spine 降级为记忆、将包含过程步骤的记忆升级为工作流）。三种信号均在术语表 §16 中定义，均只建议，永不强制执行。

---

### §3.1 三类资产速览

下表是权威摘要。后续章节（§4、§5、§6）将每类资产展开为完整的 frontmatter 模式和校验规则。

| 类别 | 功能 | 必备结构 | 撰写模式 | 主要生命周期状态 | 在 LLM 上下文中的角色 |
|---|---|---|---|---|---|
| **记忆（Memory）** | 一个**原子断言**——能独立被 supersede 的事实 / 规则 / 偏好 / 指针 | 一个带 YAML frontmatter + 正文的 `.md` 文件 | LLM 起草候选，人确认后提升为 `active` | `draft → active → stable → deprecated → archived → tombstoned` | 通过相关性闸门进入系统提示词；每次会话按相关性得分阈值加载 |
| **工作流（Workflow）** | 一个**可执行过程**——有可运行的 spine 和验证 fixture 及结果指标 | `workflow.md`（文档）+ `spine.*`（可执行）+ `fixtures/`（测试用例）+ `metrics.yaml`（结果跟踪）+ `rev/`（写时复制版本历史）| LLM 与人共同撰写；自学习引擎（Autolearn Engine）提议 spine 修订；人确认阶段闸门 | 同上六个状态 | 在任务匹配时加载；spine 调用返回结构化结果，写入 `metrics.yaml`；自学习引擎随时间演化 |
| **知识库（Knowledge Base）** | 一块**领域参考**——人会专门翻阅的多章节文档 | `README.md`（入口）+ 若干章节 `.md` 文件 + `assets/`（二进制附件）+ `_compiled.md`（LLM 生成摘要）| 人撰写章节；LLM 通过 `engram kb compile` 编译摘要；人在提升前 review 摘要 | 同上六个状态 | `_compiled.md` 按需检索，优先进入上下文预算；LLM 明确请求时再获取完整章节 |

**选择类别的唯一决策树。** 撰写新资产时，按顺序应用以下判断：

1. **我是否在陈述一件可独立被 supersede 的事？** → 记忆（Memory）。即便正文有 300 行，只要它编码的是一个独立的断言，其退役或替换不影响其他任何内容，它就是 Memory 资产。
2. **它是否有必须执行的步骤，且结果可量化？** → 工作流（Workflow）。如果你发现自己想附上测试用例或成功 / 失败指标，这个资产需要一个 spine。一段对过程的文字描述不是 Workflow；可运行的 spine 才是它的本质。
3. **它是否是让人专程坐下来翻阅的领域参考材料？** → 知识库（Knowledge Base）。如果这个资产是那种你会在浏览器里打开、滚动浏览、按章节标题导航的内容，它属于 `kb/`。

如果三个判断都无法定论，默认使用 Memory。当一条 Memory 资产积累足够多的相关联兄弟资产时，演化引擎最终会提出 *promote to KB*（升级为知识库）建议。

---

### §3.2 目录布局

engram v0.2 存储的完整磁盘布局由两棵目录树构成：项目级目录树位于单个项目内，用户全局目录树在该用户的所有项目间共享。

**项目级存储：`<project>/.memory/`**

```
<project-root>/
└── .memory/                            # 项目级存储根目录
    ├── MEMORY.md                       # landing 索引（LLM 首先读取；§7）
    ├── pools.toml                      # 池订阅配置（每个 pool 的 subscribed_at）
    ├── local/                          # 项目级 Memory（scope: project）
    │   ├── user_*.md
    │   ├── feedback_*.md
    │   ├── project_*.md
    │   ├── reference_*.md
    │   ├── workflow_ptr_*.md           # 轻量指针，指向 ../workflows/<name>/
    │   └── agent_*.md                  # LLM 自学的启发式（agent 子类型）
    ├── pools/                          # 已订阅池的符号链接 → ~/.engram/pools/<name>/
    ├── workflows/                      # 项目自有 Workflow 资产
    │   └── <name>/
    │       ├── workflow.md             # 过程文档（人可读的入口）
    │       ├── spine.py                # 可运行 spine（或 spine.sh / spine.toml）
    │       ├── fixtures/
    │       │   ├── success-case.yaml   # 预期成功的 fixture
    │       │   └── failure-case.yaml   # 预期失败的 fixture
    │       ├── metrics.yaml            # 结果跟踪器（运行次数、成功率等）
    │       └── rev/                    # 写时复制版本历史
    │           ├── r1/ ...
    │           └── current → r7/       # 指向当前活跃版本的符号链接
    ├── kb/                             # 项目自有 Knowledge Base 资产
    │   └── <topic>/
    │       ├── README.md               # 文章入口
    │       ├── 01-overview.md          # 章节文件（编号以保证稳定排序）
    │       ├── 02-details.md
    │       ├── assets/                 # 二进制附件（图片、图表等）
    │       └── _compiled.md            # LLM 生成的摘要（由 engram kb compile 重新生成）
    └── index/                          # （可选）主题子索引（§7 详述）
        └── <topic>.md
```

**目录命名说明：** `local/` 文件夹是存放项目级 Memory 资产的文件系统路径；这些文件的 frontmatter `scope:` 标签是 `project`，而不是 `local`。这两个标识符相互独立：一个是路径，另一个是参与冲突解决的 scope 标签。不要混淆。

`pools/` 文件夹包含指向用户全局 `~/.engram/pools/<name>/` 的符号链接。池内资产的 frontmatter `scope:` 标签是 `pool`，每个订阅项目在 `pools.toml` 中声明 `subscribed_at: org | team | user | project`。`subscribed_at` 的值决定该池内容在该订阅者的冲突解决中所处的有效层级——这是订阅的属性，不是池本身的属性。

**用户全局存储：`~/.engram/`**

```
~/.engram/                              # 工具私有、用户私有；永远不纳入项目 git
├── version                             # 纯文本文件："0.2"
├── config.toml                         # 用户级 engram 配置
├── org/<org-name>/                     # scope: org（git 同步；公司 / 组织规则）
│   └── *.md（+ workflows/、kb/ 按需）
├── team/<team-name>/                   # scope: team（git 同步；团队 / 部门约定）
│   └── *.md（+ workflows/、kb/ 按需）
├── user/                               # scope: user（本人跨项目基线）
│   └── *.md
├── pools/<name>/                       # scope: pool（规范位置；项目通过符号链接订阅）
│   └── *.md（+ workflows/、kb/）
├── inbox/<repo-id>/                    # 跨仓传信器（Cross-Repo Messenger）收件箱（每个远端仓库一个目录）
├── archive/                            # 已 tombstone 的资产；物理删除前保留 ≥ 6 个月
├── playbooks/<name>/                   # 可安装的 Playbook 包（github:owner/repo 克隆）
├── graph.db                            # SQLite：订阅图、引用图、索引
├── cache/                              # 嵌入索引、FTS5 全文索引（可从文件重建）
├── journal/                            # append-only 事件日志
│   ├── evolution.tsv                   # 自学习 / 演化引擎运行记录
│   ├── propagation.jsonl               # 池更新传播事件
│   ├── inter_repo.jsonl                # 跨仓 inbox 收发事件
│   └── consistency.jsonl               # 一致性引擎扫描结果
└── workspace/                          # 自学习引擎的每次运行隔离沙箱
```

**用户全局不变量。** 任何合规工具都必须遵守以下三条不变量：

- `~/.engram/` 永远不纳入项目的 git 仓库。它是工具私有、用户私有的。组织和团队内容通过 `~/.engram/org/` 和 `~/.engram/team/` 进行 git 同步——这些子目录有自己独立的 git 远端，而不是项目的 git 远端。
- `journal/` 目录下的每个文件严格追加写入（append-only）。任何工具都不得截断、重写或删除 journal 文件。日志压缩（为回收磁盘空间）仅由 `engram snapshot` 在创建经过验证的归档后执行。
- 资产的删除不能直接操作文件系统。退役一个资产会将其移动到 `~/.engram/archive/`，在物理删除前至少保留六个月。直接对资产文件执行 `rm` 是协议违规行为。

---

### §3.3 跨资产引用规则

以下五条规则规定了三类资产之间、以及跨 scope 边界的引用方式。前四条是 MUST 规则——违反任意一条将导致 `engram validate` 报错。第五条是 SHOULD 规则——推荐实践，工具应支持，但缺席不产生校验错误。

**MUST 1 — Memory-to-Memory 内部引用使用 wiki-link 语法。**

引用另一条 Memory 资产的 Memory 资产，必须使用语法 `[[<memory-id>]]`，其中 `<memory-id>` 是相对于最近一个 scope 根目录的文件路径，不含 `.md` 后缀。示例：`[[local/feedback_push_confirm]]` 表示项目级资产；`[[pools/kernel-work/reference_linux_lts]]` 表示已订阅池中的资产。这是规范引用格式。合规工具在渲染 Memory 资产时，必须将 wiki-link 解析为其目标文件。

**MUST 2 — Workflow spine 代码只能通过 CLI 读取 Memory。**

Workflow spine（`spine.py`、`spine.sh`、`spine.toml` 或任何其他可执行文件）必须通过 `engram memory read <id>` CLI 命令读取 Memory 资产，不得直接访问文件系统。直接文件系统读取绕过了 scope 执行模型和向 `usage_count` 写入的访问日志。直接通过路径读取 `.memory/local/feedback_push_confirm.md` 的 spine 是不合规的；调用 `engram memory read local/feedback_push_confirm` 的 spine 是合规的。

**MUST 3 — 跨 scope 引用必须在 frontmatter 中声明。**

任何引用不同 scope 下资产的资产，必须在 frontmatter 的 `references:` 字段（YAML 列表）中列出目标资产的 ID。跨 scope 引用声明为 `graph.db` 的完整性模型提供数据，并使一致性引擎能够检测 `reference-rot`（引用失效）。示例：

```yaml
references:
  - pools/kernel-work/reference_linux_lts
  - user/feedback_code_style
```

**MUST 4 — 有入站引用的资产不能被直接删除。**

删除一条被其他资产的 `references:` 字段所引用的资产，会被 `engram validate` 阻止。在删除能继续之前，该资产必须先转换为 `deprecated` 状态，所有引用方必须更新各自的 `references:` 字段，或通过 `supersedes:` 字段确认接受这次 supersede。该规则确保 `reference-rot` 在发生之前被检测到，而不是发生之后。

**SHOULD 1 — KB 和 Memory 之间使用带类型的跨类别引用语法。**

引用 Memory 资产的 KB 文章，应使用语法 `@memory:<id>`。引用 KB 章节的 Memory 资产，应使用 `@kb:<topic>/<section>`。这些是 wiki-link 格式的带类型语法糖：合规工具可以将 `@memory:local/feedback_push_confirm` 与 `[[local/feedback_push_confirm]]` 以相同方式渲染。带类型语法使跨类别引用可以被机器发现，而无需解析正文内容。

**引用失效检测。** 一致性引擎会检测悬空引用——目标资产已被 tombstone 或 ID 无法再解析的引用——并在 `reference-rot` 冲突类别下呈现（见 §11）。引擎不会自动修复悬空引用；它提出修复建议，并将决策留给所有者。

---

### §3.4 后续阅读

以下各节将每类资产和共享基础设施展开为完整的格式契约。

- **§4 — Memory 子类型与 frontmatter。** 六种 Memory 子类型（`user`、`feedback`、`project`、`reference`、`workflow_ptr`、`agent`）、各自的必填和可选 frontmatter 字段、每种子类型的正文约定，以及 `confidence` 证据块的完整 schema。
- **§5 — Workflow 资产格式。** `workflow.md` 文档 schema、`spine.*` 契约（什么使 spine 合规）、`fixtures/` 测试用例格式、`metrics.yaml` 结果跟踪器 schema，以及 `rev/` 写时复制版本协议。
- **§6 — Knowledge Base 资产格式。** `README.md` 入口 schema、章节文件约定、`assets/` 目录契约，以及 `_compiled.md` 摘要格式和重新生成规则。
- **§7 — MEMORY.md 分层 landing 索引。** 格式、分组规则、行长限制，以及项目存储中每个资产必须在索引中恰好出现一次的不变量。
- **§8 — Scope 模型。** 完整的两轴 scope 模型：四级归属层级（`org > team > user > project`）、正交的订阅轴（`pool` 与 `subscribed_at`）、冲突解决规则，以及 `enforcement` 语义。

---

## 4. Memory 子类型与 Frontmatter Schema

### §4.0 概述

记忆（Memory）是 §3 所定义的三类资产之一。§3 确立了类别边界——Memory 是一条可独立被 supersede 的原子断言——本节在此基础上定义 Memory 的内部分类法：六种子类型、每条 Memory 资产都携带的 v0.2 扩展 frontmatter 字段，以及区分各子类型的正文约定。

核心组织概念是**认识论状态**（epistemic status）：子类型表达的是*谁写了这条资产、以及我们凭什么认为它为真*，而不是它涵盖什么主题或它有多大。`feedback`（反馈型）资产是人下达的规则；`agent`（代理元指令）资产是 LLM 自己推断出的启发式规则。同一个声明，若出自人则是 `feedback`，若出自 LLM 则是 `agent`——二者的默认置信度不同、一致性引擎的审查力度不同、置信度的起步方式也不同。子类型与 scope 正交——任何子类型都可以存在于任何 scope 层级。团队级强制规则是 `feedback` + `scope: team` + `enforcement: mandatory`，而不是一个独立的 `team` 子类型。

六种子类型——`user`（用户型）、`feedback`（反馈型）、`project`（项目型）、`reference`（引用型）、`workflow_ptr`（工作流指针）、`agent`（代理元指令）——对应 `local/` 及各 scope 目录中使用的六种文件前缀。前四种从 v0.1 延续而来，略有扩展；后两种是 v0.2 新增。全部六种子类型参与相同的生命周期（`draft → active → stable → deprecated → archived → tombstoned`）和相同的证据模型（§4.8 所述的 `confidence` 块）。

§4.1 规定完整的 frontmatter schema：必填字段、scope 条件字段和可选字段。§4.2–§4.7 依次定义每种子类型。§4.8 定义 `confidence` 对象 schema 和置信分公式。§4.9 解决常见的子类型边界争议。§4.10 是快速参考汇总表。

---

### §4.1 Frontmatter Schema

每条 Memory 资产文件以 `---` 界定的 YAML frontmatter 块开头。下表列出所有已知字段。工具在重写时**必须**保留未识别字段——工具**不得**删除它不认识的 frontmatter 键。

#### 必填字段（所有 Memory 资产）

| 字段 | 类型 | 引入版本 | 语义 |
|---|---|---|---|
| `name` | string | v0.1 | 简短的人可读标题。显示在 `MEMORY.md` 中。 |
| `description` | string | v0.1 | 一行相关性钩子（≤150 字符）。相关性闸门（Relevance Gate）扫描 `MEMORY.md` 时用来决定是否加载完整资产。 |
| `type` | enum | v0.1 | 六选一：`user / feedback / project / reference / workflow_ptr / agent`。 |
| `scope` | enum | v0.2 | 五选一：`org / team / user / project / pool`。v0.1 存储库迁移时默认为 `project`（见 §13）。 |
| `enforcement` | enum | v0.2 | 三选一：`mandatory / default / hint`。`feedback` 子类型必填；其他子类型可选，默认为 `hint`。语义见术语表 §5。 |

#### Scope 条件必填字段

以下字段仅在 `scope` 取特定值时为必填。

| 字段 | 何时必填 | 语义 |
|---|---|---|
| `org` | `scope: org` | 组织名称，与 `~/.engram/org/<name>/` 匹配。 |
| `team` | `scope: team` | 团队名称，与 `~/.engram/team/<name>/` 匹配。 |
| `pool` | `scope: pool` | 池名称，与 `~/.engram/pools/<name>/` 匹配。 |
| `subscribed_at` | `scope: pool` | 此订阅者的有效归属层级：`org / team / user / project` 之一。在 `pools.toml` 中声明，此处引用以提升每条资产的可读性。 |

#### 可选字段（所有 Memory 资产）

| 字段 | 类型 | 引入版本 | 语义 |
|---|---|---|---|
| `created` | ISO 8601 | v0.1 | 首次写入日期。 |
| `updated` | ISO 8601 | v0.1 | 最后编辑日期。 |
| `tags` | list[string] | v0.1 | 自由格式主题标签，用于分组和搜索。 |
| `expires` | ISO 8601 | v0.1 | 单点提示：此日期后资产可能过期。触发 review 提示；不自动归档。 |
| `valid_from` | ISO 8601 | v0.2 | 该事实从此日期起成立。支持 `graph.db` 中的时间过滤查询。 |
| `valid_to` | ISO 8601 | v0.2 | 该事实在此日期停止成立。与 `expires` 有别：`valid_to` 标记历史闭合，`expires` 触发未来 review。 |
| `source` | string | v0.1 | 声明来源——对话日期、事件 ID、URL，或 `agent-learned`（用于 `agent` 子类型）。 |
| `references` | list[string] | v0.2 | 本资产所依赖的资产 ID 列表。跨 scope 引用**必须**在此声明（见 §3.3 MUST 3）。为 `graph.db` 完整性提供数据。 |
| `overrides` | string | v0.2 | 本资产所覆盖的上级 scope 资产 ID。覆盖 `default`-enforcement 资产时必填；**不得**用于覆盖 `mandatory`-enforcement 资产。 |
| `supersedes` | string | v0.2 | 本资产所替代的旧资产 ID。构建溯源链；防止 `silent-override`（静默覆盖）冲突。 |
| `limitations` | list[string] | v0.2 | 本资产不适用的条件列表。推荐 `feedback`、`project`、`agent` 子类型在适用范围有限时使用。 |
| `confidence` | object | v0.2 | 证据驱动的置信度块。Schema 定义见 §4.8。`agent` 子类型实际上为必填；所有资产进入 `active` 状态后均推荐填写。 |

#### 子类型特有必填字段

各子类型章节（§4.2–§4.7）列出该子类型在上述通用必填集之外额外要求的字段。

---

### §4.2 `user`（用户型）子类型

**用途。** 关于人的事实：其角色、技能、工作背景、偏好，以及 LLM 应据此调整行为的各种约束。这是"我在和谁说话"的基线。由人撰写，相对于其他子类型变化较少。

**正文约定。** 至少 20 字符的自由散文。无需固定小节结构。用第三人称从 LLM 视角书写（"用户负责……"、"他们偏好……"），使文本注入系统提示词时读起来自然流畅。

**无额外必填 frontmatter。** `enforcement` 默认为 `hint`——用户上下文是建议性的，不是强制规则。

**示例：**

```markdown
---
name: 用户是 acme 平台团队 lead
description: 负责 acme 平台团队；主要技术栈为 Go 和 Kubernetes；偏好简洁的技术解释
type: user
scope: user
created: 2026-04-18
tags: [角色, 上下文]
---

用户是 Acme Corp 平台团队的 lead，负责内部基于 Kubernetes 的部署基础设施，服务约四十名产品工程师。他们有七年 Go 经验和四年 Kubernetes operator 经验，主要领域是集群网络、准入 webhook 和自定义 controller。

解释时假设对方已熟知 Go 和 Kubernetes 内部原理。跳过"Kubernetes 是容器编排系统"这类铺垫。提出方案时先给 Go 代码或 YAML，动机放后面。

他们保持严格的工作生活边界：不要建议可能在夜间或周末无人监控情况下运行的批处理操作，除非明确加入调度守卫。
---
```

---

### §4.3 `feedback`（反馈型）子类型

**用途。** LLM 必须遵守的规则——可以是用户在观察到失败后给出的纠正，也可以是用户确认过的有效方法。这些是人写的行为约束。`enforcement` 字段对此子类型为必填且不可省略：它决定该规则是否可在本地被覆盖。

**此子类型额外必填 frontmatter：** `enforcement`（`mandatory / default / hint` 之一）。与其他子类型的 `enforcement` 默认为 `hint` 不同，`feedback` 必须显式声明。

**必需正文结构：**

```
<一行规则陈述>

**原因：** <与某事件、偏好或明确指令绑定的理由>

**如何应用：** <此规则在何时何处生效；包含边界情况>
```

"原因"和"如何应用"这两个小节是必需的，不是可选散文。知道*为什么*，未来的读者——无论人还是 LLM——才能对边界情况进行推理，而不是盲目套用规则。没有"原因"的规则不是 `feedback` 资产，而是一条笔记。真正没有例外的规则应设为 `enforcement: mandatory`。作为良好默认值但可被项目覆盖的规则应设为 `enforcement: default`。用户不希望强制执行的个人风格偏好应设为 `enforcement: hint`。

**示例——组织级强制规则：**

```markdown
---
name: 所有提交必须包含 SPDX 许可证头
description: 提交到任何 acme-org 仓库的所有源文件必须带有 SPDX-License-Identifier 头
type: feedback
scope: org
org: acme
enforcement: mandatory
created: 2026-01-15
tags: [合规, 许可证]
source: 2026-01-14 法务团队指令
---

提交到 acme-org 任何仓库的每个源文件，必须在文件第一或第二行包含 `SPDX-License-Identifier:` 头。

**原因：** 法务团队在 2026-01-14 的 IP 审计发现三个仓库存在无许可证文件，因此发出该指令。违规现在会在所有组织仓库中阻塞 CI。

**如何应用：** 生成或修改任何源文件（`.go`、`.py`、`.ts`、`.sh` 等）前，检查是否已有 SPDX 头。若无，在文件开头添加 `// SPDX-License-Identifier: Apache-2.0`（或项目声明的许可证）。不得提交没有该头的文件。如果项目许可证不是 Apache-2.0，先与用户确认再填写。
---
```

**示例——用户级建议规则：**

```markdown
---
name: Go 中优先使用表驱动测试
description: 编写 Go 测试时使用表驱动子测试，除非测试只有一个平凡用例
type: feedback
scope: user
enforcement: hint
created: 2026-03-02
tags: [go, 测试, 风格]
source: 2026-03-02 明确表达的偏好
---

编写 Go 测试时使用表驱动子测试（`for _, tc := range cases { t.Run(tc.name, ...) }`），不要用一连串平铺的断言调用。

**原因：** 表驱动测试更容易扩展，失败消息按用例名称标识失败点更清晰，且与 Go 标准库自身的风格一致。用户明确表达了这一偏好。

**如何应用：** 任何新的 Go 测试，或重构现有测试时，默认使用表驱动风格。例外：如果确实只有一个用例且不太可能增加更多，平铺测试也可以。
---
```

---

### §4.4 `project`（项目型）子类型

**用途。** 关于当前工作的事实：进行中的计划、活跃决策、截止日期、事件复盘，或任何无法从代码或 git 历史中恢复的上下文。这些是人对当前项目状态的观察，由人撰写。随项目阶段演进而频繁变化，项目阶段结束时到期。

**必需正文结构：**

```
<一行事实或决策陈述>

**原因：** <动机——约束、截止日期、干系人要求>

**如何应用：** <这条事实如何影响 LLM 的后续建议或计划>
```

**只用绝对日期。** "下周四"或"Q2 末"这类相对表述，必须在写入时转换为 ISO 8601 日期（`2026-04-23`、`2026-06-30`）。相对表述一旦资产跨越原始会话就会变得模糊。对于时间受限的项目事实，强烈建议填写 `expires` 字段。

**无额外必填 frontmatter。** `enforcement` 默认为 `hint`——项目决策是上下文，不是规令。

**示例：**

```markdown
---
name: acme 平台迁移至 Go 1.23，面向 Q2 发版
description: 所有平台服务须在 2026-06-30 前以 Go 1.23 为目标；此后停止对 1.22 的支持
type: project
scope: project
created: 2026-04-10
updated: 2026-04-18
tags: [迁移, go, 截止日期]
expires: 2026-07-01
valid_from: 2026-04-10
valid_to: 2026-06-30
source: Q2 规划文档，2026-04-10
---

所有平台服务须在 2026-06-30 前以 Go 1.23 为构建目标。此后内部 CI 基础镜像将完全移除 Go 1.22 工具链。

**原因：** Go 1.22 工具链存在已知漏洞（CVE-2026-0001），无法通过 backport 修复。安全团队已将 2026-06-30 定为硬截止日期。错过截止日期意味着必须强制回退到预发布构建。

**如何应用：** 为平台服务建议任何代码更改或依赖更新时，以 Go 1.23 语法和标准库为目标。不要建议将 `go mod` 固定在 1.22。如某依赖尚未发布 1.23 兼容版本，应明确标出，而不是静默降级。
---
```

---

### §4.5 `reference`（引用型）子类型

**用途。** 指向外部系统、文档、仪表板、工单、权威代码库或存储库外任何资源的指针——LLM 需要知晓其存在并在适当时查阅。引用由人撰写。它不是关于项目状态的（那是 `project`），也不是关于规则的（那是 `feedback`）——它是"这里是找到 X 的地方"。

**正文约定。** 自由散文。内容须足以：(1) 无歧义地定位资源；(2) 解释*为何*该资源重要以及何时使用；(3) 注明访问要求或注意事项。只有 URL 没有使用说明和涵盖范围的引用，在相关性排名中得分会很低。

**无额外必填 frontmatter。** `enforcement` 默认为 `hint`。

**示例：**

```markdown
---
name: acme 内部延迟仪表板（Grafana）
description: 团队主要 SLO 仪表板；按区域展示所有平台服务的 p50/p95/p99 延迟
type: reference
scope: team
team: platform
created: 2026-02-20
updated: 2026-04-18
tags: [可观测性, slo, grafana, 延迟]
source: 平台值班手册 v3
---

平台团队的主要延迟与 SLO 仪表板托管在公司内部 Grafana 实例。覆盖所有平台服务的 p50、p95、p99 延迟，按区域和端点划分，时间窗口为 30 天滚动。

在针对平台服务提出任何性能相关建议前，请先查阅此仪表板。"SLO 违约风险"面板显示当前错误预算消耗速率——如果超过 50%，则将任何增加请求扇出或添加同步 RPC 的方案视为高风险。

访问需要内部 VPN 并加入 `grafana-platform-team` 组。本周值班轮转人员显示在右上角面板中。
---
```

---

### §4.6 `workflow_ptr`（工作流指针）子类型——v0.2 新增

**用途。** 从 Memory 存储库指向完整 Workflow 资产（见 §5）的轻量指针。`MEMORY.md` 设计为在每次 LLM 会话中加载；完整 Workflow 文档只在任务匹配时加载。`workflow_ptr` 充当桥梁：扫描 `MEMORY.md` 的 LLM 看到这个指针，就知道有一个完整的、可执行的过程存在于引用路径，而无需提前将整个 `workflow.md` 占用上下文预算。

此子类型使 `MEMORY.md` 保持小巧可扫描，同时让 LLM 能够发现可用工作流。当 LLM 判断某工作流相关时，再从 `workflow_ref` 路径加载完整的 `workflow.md`。

**此子类型额外必填 frontmatter：**

| 字段 | 类型 | 语义 |
|---|---|---|
| `workflow_ref` | string | 相对于 scope 根目录的 `workflows/<name>/` 路径。完整过程文档位于 `<scope-root>/<workflow_ref>/workflow.md`。 |

**正文约定。** 一至三段，概述：(1) 工作流做什么；(2) 何时使用；(3) 预期产出结果。不要复制完整过程步骤——那些在 `workflow.md` 中。正文是"我是否需要加载这个工作流？"的判断辅助材料。

**示例：**

```markdown
---
name: git 合并工作流（平台团队标准）
description: feature 分支合并的完整步骤：squash、changelog 条目写入、团队通知
type: workflow_ptr
scope: team
team: platform
workflow_ref: workflows/git-merge-standard/
created: 2026-03-15
updated: 2026-04-10
tags: [git, 工作流, 合并, 发版]
---

`git-merge-standard` 工作流覆盖平台服务 feature 分支合并到 `main` 的完整生命周期：合并前检查（测试通过、覆盖率门控、diff 大小 review）、带规范 commit 消息的 squash 合并、CHANGELOG.md 条目自动生成，以及发布到 `#platform-releases` 的 Slack 通知。

凡是涉及平台服务代码的分支合并，都使用此工作流。纯文档分支走更轻量的路径，hotfix 分支有独立的 `git-hotfix` 工作流，带有不同的发版门控，不使用本工作流。

预期产出：分支被 squash 合并到 `main`，`CHANGELOG.md` 追加一条条目，格式化的发版摘要在合并后两分钟内发送到 `#platform-releases`。指标跟踪器记录本次合并事件并更新工作流成功率。
---
```

---

### §4.7 `agent`（代理元指令）子类型——v0.2 新增

**用途。** LLM 自学到的元启发式规则：LLM 从观察结果中推断出的行为模式，而非人陈述的规则。这与 `feedback` 在一个关键点上不同：来源是 LLM 自身。这一区别产生三个具体影响。

**LLM 撰写状态的含义：**

1. **默认置信度更低。** 一致性引擎对 `agent` 资产的审查频率高于 `feedback` 资产。`feedback` 规则背后有人的权威；`agent` 启发式规则是一个假设。
2. **`source` 为必填。** `source` 字段必须标明来源：对于无具体溯源的启发式用 `agent-learned`，对于来自特定工作流修订的用更具体的引用，如 `source: autolearn/git-merge-standard/r5`。
3. **`confidence` 实际上为必填。** `agent` 资产是假设，其证据基础必须显式表达。创建时以 `validated_count: 0` 和 `contradicted_count: 0` 起步。只有积累足够多的正向结果后，资产才能晋升为 `stable`。

**必需正文结构：**

```
<一行启发式规则陈述>

**原因：** <具体观察结果——"使用此方法后观察到 N 次成功"；引用修订版本或会话>

**如何应用：** <此启发式在何时何处适用；包含已知的失效场景>
```

"原因"必须引用具体证据，而非直觉。"采用此方法在 r5 版本后观察到 5 次成功合并"是有效的原因。"这看起来更干净"则不是。

**示例：**

```markdown
---
name: 合并前 squash 可防止平台 CI 的不稳定性
description: 推送到合并队列前在本地 squash 提交，可降低平台服务的 CI 重跑率
type: agent
scope: project
source: autolearn/git-merge-standard/r5
enforcement: hint
created: 2026-04-12
tags: [git, ci, 合并, agent-learned]
confidence:
  validated_count: 5
  contradicted_count: 0
  last_validated: 2026-04-17
  usage_count: 7
limitations:
  - 仅在平台服务仓库中观察到；未在 SDK 或文档仓库中验证
  - 可能不适用于提交需携带独立 authored-by 署名要求的场景
---

在推送到合并队列前，在本地将提交 squash 为一个提交；不要依赖合并队列来执行 squash。

**原因：** 在 `git-merge-standard` 修订版 r5 采用此方法后，连续 5 次合并的 CI 重跑率从约 40% 降至零。可能原因是：合并队列的 squash 会以本地 squash 所不会触发的方式使 Go 构建缓存失效，因为合并队列 squash 改变了提交树结构，而构建缓存无法识别这一变化。

**如何应用：** 推送任何平台服务分支前，执行 `git rebase -i origin/main` 并 squash 为单个提交。如果分支太大无法干净 squash，拆分为更小的块，而不是不 squash 就推送。仅对平台服务仓库适用；其他位置的行为尚未观察。
---
```

---

### §4.8 Confidence（置信度）字段 Schema

`confidence` 块是嵌套在 frontmatter 中的 YAML 对象。`agent` 子类型必填，所有 Memory 资产进入 `active` 状态后推荐填写。当 `confidence` 块存在时，以下四个子字段均为必填。

```yaml
confidence:
  validated_count: 12         # LLM 根据此资产行动、现实验证其正确的次数
  contradicted_count: 0       # 现实与此资产声明或规则矛盾的次数
  last_validated: 2026-04-15  # 最近一次正向结果事件的 ISO 8601 日期
  usage_count: 38             # 此资产进入任意 LLM 上下文的总次数
```

**子字段语义：**

| 子字段 | 类型 | 语义 |
|---|---|---|
| `validated_count` | 整数 ≥ 0 | 每次 LLM 根据此资产采取行动，且结果日志记录成功或确认，则递增。 |
| `contradicted_count` | 整数 ≥ 0 | 每次日志记录遵循此资产产生错误结果或被明确纠正，则递增。 |
| `last_validated` | ISO 8601 | 最近一次正向结果事件的日期。用于计算陈旧惩罚（`staleness_penalty`）。 |
| `usage_count` | 整数 ≥ 0 | 此资产进入任意类型 LLM 上下文的总次数（预热、引用或 review 均计入）。用于对置信分加权。 |

**置信分公式**（由 §11 中的一致性引擎应用；此处为权威定义）：

```
score = (validated_count - 2 × contradicted_count - staleness_penalty) / max(1, total_events)

其中：
  total_events      = validated_count + contradicted_count
  staleness_penalty = 0.0   若 last_validated 在今天 90 天内
                   | 0.3   若 last_validated 在今天 365 天内
                   | 0.7   若 last_validated 距今超过 365 天
```

资产首次创建时，所有计数从零开始。经过可配置次数的使用且无证伪（默认 N = 3），资产具备晋升为生命周期状态 `stable`（稳定）的条件。

**不变量：** 低置信分不触发自动归档。它使资产浮现在 `engram review` 中，由人做决策。一致性引擎只建议；永不自动 mutate。完整的一致性契约见 §11。

---

### §4.9 子类型边界规则

下表解决最常见的子类型边界争议。撰写新资产时，用此表确定正确的子类型。

| 场景 | 正确子类型 |
|---|---|
| "每次遇到 Y 都做 X"——用户教给你的规则 | `feedback` |
| "遇到 Y 通常做 X"——LLM 从结果中推断的启发式 | `agent` |
| 团队级规则，如"所有文件必须带 SPDX 头" | `feedback` + `scope: team` + `enforcement: mandatory` |
| 以后还会查阅的外部文档 URL | `reference` |
| 进行中的项目决策，如"本次发版使用 Go 1.23" | `project` |
| 用户是谁、做什么、偏好怎么工作 | `user` |
| 指向完整 Workflow 过程的轻量指针 | `workflow_ptr` |
| 用户偶然提到的个人风格偏好 | `feedback` + `enforcement: hint` |
| LLM 观察到 N 次有效、但用户尚未确认的模式 | `agent` |
| 团队用于可观测性的内部仪表板 URL | `reference` + `scope: team` |

**关于 `team` 是 scope 而非子类型。** v0.1 没有 scope 模型，团队级约定的归属曾是模糊地带。v0.2 中，`team` 是 scope 标签（`scope: team`），从不是子类型。团队级强制规则是 `feedback` + `scope: team` + `enforcement: mandatory`。v0.1 的四种子类型（`user`、`feedback`、`project`、`reference`）延续至今；v0.2 新增 `workflow_ptr` 和 `agent`。

**关于 `limitations`（局限说明）。** 当一条 `agent` 或 `feedback` 资产已知在某些条件下不适用时，应声明 `limitations:`，而不是将注意事项埋在正文散文中。一致性引擎在评估资产时会查看 `limitations`，避免将局限范围内的否定证据误判为矛盾。

---

### §4.10 快速参考汇总

| 子类型 | 文件前缀 | 撰写者 | 通用必填之外的额外必填 frontmatter | 正文约定 |
|---|---|---|---|---|
| `user` | `user_` | 人 | — | 自由散文 |
| `feedback` | `feedback_` | 人 | `enforcement` | 规则陈述 + **原因** + **如何应用** |
| `project` | `project_` | 人 | — | 事实 / 决策 + **原因** + **如何应用**；只用绝对日期 |
| `reference` | `reference_` | 人 | — | 含资源指针、访问说明和使用时机的自由散文 |
| `workflow_ptr` | `workflow_ptr_` | 人 | `workflow_ref` | 1–3 段：工作流做什么、何时使用、预期产出 |
| `agent` | `agent_` | LLM | `source`（必须标明来源）；`confidence` 实际上为必填 | 规则陈述 + **原因**（含具体结果引用）+ **如何应用** |

---

---

## 5. Workflow 资产规范

### §5.0 概述

Workflow（工作流）是 engram 对过程性知识的回答——可靠、可重复地**完成某件事**的方法论。Memory 捕获原子断言：事实、规则、偏好、指针。Workflow 捕获可执行过程：一个能真正运行的 spine、能验证它的 fixtures、能度量它的 metrics，以及记录它如何持续改进的修订历史。

该格式受两条设计传统影响：

- **Agent Factory**（Karpathy）：经验应以可执行代码而非叙事文本的形式存储。纯文本过程悄无声息地退化；可执行 spine 则会响亮地失败，可被测试，且可被机械地改进。
- **autoresearch**（Karpathy）：自我改进的循环需要固定预算、单文件变更边界、只追加的结果日志、简洁性准则，以及人工可审查的阶段闸门。自学习棘轮（见 §5.6）直接应用了这些纪律。

三类资产互补。Memory 断言事实。Workflow 执行过程。Knowledge Base 文章解释领域知识。每类资产在 LLM 任务生命周期的不同阶段加载，在上下文预算中占据不同成本层级。

§5 定义 Workflow 资产的**磁盘格式契约**：目录布局、frontmatter 模式、spine 要求、fixtures 格式、metrics 模式，以及修订生命周期。逐轮演化 Workflow 的自学习引擎（Autolearn Engine）规范见 `DESIGN.md §5.3`；本文档不实现该算法，只约定算法必须遵守的数据契约。

---

### §5.1 目录布局

每个 Workflow 存放在其 scope 根目录下的 `workflows/<name>/` 目录中。完整布局：

```
<scope-root>/workflows/<name>/
├── workflow.md                    # 人类可读文档（必需）
├── spine.<ext>                    # 可执行入口（必需）
├── fixtures/                      # 验证场景（必需）
│   ├── success-case.yaml          # 至少一个成功 fixture
│   └── failure-case.yaml          # 至少一个失败 fixture
├── metrics.yaml                   # 指标定义与聚合规则（必需）
├── rev/                           # 写时复制修订历史
│   ├── r1/
│   │   ├── spine.<ext>
│   │   ├── workflow.md
│   │   ├── fixtures/
│   │   ├── metrics.yaml
│   │   └── outcome.tsv            # 本修订版本的逐 fixture 结果
│   ├── r2/
│   │   └── ...
│   └── current -> rN/             # 指向当前活跃修订版本的符号链接
└── journal/
    ├── evolution.tsv              # 只追加；每轮自学习一行
    └── runs.jsonl                 # 只追加；每次调用一行
```

**`workflows/<name>/` 目录的 Scope 根目录：**

| Scope | 根目录路径 |
|---|---|
| `project` | `<project>/.memory/` |
| `team` | `~/.engram/team/<team>/` |
| `org` | `~/.engram/org/<org>/` |
| `user` | `~/.engram/user/` |
| `pool` | `~/.engram/pools/<pool>/` |

**`rev/current` 符号链接。** 每轮自学习创建一个新的 `rev/rN/` 目录（N = 当前最大修订编号 + 1），包含完整快照：`spine.<ext>`、`workflow.md`、`fixtures/`、`metrics.yaml` 和 `outcome.tsv`。成功时 `current` 符号链接原子地指向 `rev/rN/`。若棘轮回滚（新修订版本未在容差范围内改进主指标），符号链接保持不变，`rev/rN/` 保留在磁盘上作为审计记录。失败的修订版本永不删除；它们是证据。

**`journal/evolution.tsv`** 严格只追加。每轮自学习无论成败均追加一行。其模式在 `DESIGN.md §5.3` 中规定；任何工具都不得截断或重写该文件，此不变量在本文档中固定。

**`journal/runs.jsonl`** 记录每次 `engram workflow run <name>` 调用——每行一个 JSON 对象，只追加，包含时间戳、inputs 哈希、结果状态以及 spine 输出的 metrics 值。

**无大小上限。** Workflow 格式对任何文件不设行数或字节数上限。大小是内容问题；格式契约不对其编码。

---

### §5.2 `workflow.md` 格式

`workflow.md` 是人类可读的入口点，也是 `workflow_ptr` 解析时 LLM 加载的文件：它提供足够的上下文，让 LLM 理解 spine 的作用、适用时机，以及成功与失败的表现。

**必填 frontmatter：**

| 字段 | 类型 | 语义 |
|---|---|---|
| `name` | string | 简短的人类可读标题。通过引用它的 `workflow_ptr` 显示在 `MEMORY.md` 中。 |
| `description` | string | ≤150 字符的摘要。由 Relevance Gate 使用。 |
| `type` | 字面量 `workflow` | 始终为 `workflow`。 |
| `scope` | enum | `org / team / user / project / pool`。 |
| `spine_lang` | enum | `python3 / bash / toml`。声明运行时调用 spine 使用哪种执行器。 |
| `spine_entry` | string | 从工作流目录根到 spine 文件的相对路径（如 `spine.py`）。 |
| `inputs_schema` | string | JSON Schema 文件的相对路径，运行时在调用前用此模式验证 spine 输入（如 `schemas/inputs.json`）。 |
| `outputs_schema` | string | JSON Schema 文件的相对路径，运行时在记录前用此模式验证 spine 输出（如 `schemas/outputs.json`）。 |
| `metric_primary` | string | 驱动自学习棘轮的指标名。必须与 `metrics.yaml` 中某条 `name` 匹配。 |
| `lifecycle_state` | enum | `draft / active / stable / deprecated / archived`。 |
| `created` | ISO 8601 | |
| `updated` | ISO 8601 | |

可选 frontmatter 字段遵循与 Memory 资产相同的规则（见 §4.1）：`tags`、`references`、`side_effects`、`expires` 以及任何未知字段（重写时必须保留）。

**`side_effects`** 是一个 YAML 列表。没有副作用的 spine 省略此字段。写文件、发起网络请求或提交 git 的 spine 必须声明：

```yaml
side_effects: [fs_write, network, git_commit]
```

运行时在调用有副作用声明的 spine 前会显示提示。有副作用但未声明的 spine 不合规。

**必需正文章节**（按顺序）：

1. **Purpose（用途）** — 此工作流解决什么问题；为什么以工作流而非 Memory 的形式存在。
2. **When to use（适用时机）** — 具体触发条件；哪些上下文信号表明此工作流相关。
3. **Expected outcome（预期产出）** — 以 `metric_primary` 表达的成功标准；当 spine 返回 `status: success` 时调用方应观察到什么。
4. **Failure modes（失败模式）** — 已知的失败模式及其逃生路径；当 spine 返回 `status: failure` 或非零退出码时调用方应怎么做。
5. **Why this approach（方法论依据）** — 设计理由；spine 编码了什么，以及为什么这样编码。本节对自学习引擎有支撑作用：它记录了不应被突变掉的内容。

---

### §5.3 Spine 契约

Spine 是唯一真正执行的工件。工作流目录中的所有其他文件都是声明性的。无论 `spine_lang` 取何值，spine 必须满足以下要求。

**通用要求（适用于所有 `spine_lang` 值）：**

1. **同输入下确定性。** 给定相同 `inputs`，spine 产生相同 `outputs` 和相同副作用。若工作流本质上与时间相关，当前时间必须包含在声明的 `inputs_schema` 中——调用方显式提供时间，而非让 spine 自行读取系统时钟。
2. **默认无副作用。** 写文件、发起网络请求或提交 git 的 spine 必须在 `workflow.md` frontmatter 中声明 `side_effects:`（见 §5.2）。未声明的副作用是合规违规。
3. **通过 CLI 读取 Memory。** Spine 必须通过 `engram memory read <id>` 读取 Memory 资产，不得直接访问 `.memory/` 路径（见 §3.3 MUST 2）。
4. **结构化产出。** Spine 必须输出符合 `outputs_schema` 的结果。最小有效输出包含 `status`（`success` 或 `failure`）和 `metrics`（指标名到值的映射）。

**Python spine（`spine_lang: python3`）：**

```python
# spine.py
def main(inputs: dict) -> dict:
    """
    入口函数。调用前 `inputs` 已按 inputs_schema 验证。
    返回值在记录前按 outputs_schema 验证。
    """
    # ... 工作流逻辑 ...
    return {
        "status": "success",     # 或 "failure"
        "metrics": {
            "merge_time_seconds": 42.1,
        },
        "artifacts": [],         # 可选：产出文件路径列表
        "trace": [],             # 可选：步骤日志字符串列表
    }
```

运行时直接调用 `main(inputs)`。不需要 `if __name__ == "__main__"` 保护（但可以有）。运行时不以子进程方式 exec 文件——而是导入并调用函数。

**Bash spine（`spine_lang: bash`）：**

```bash
#!/usr/bin/env bash
# spine.sh
# 从 stdin 读取 JSON inputs。
# 向 stdout 输出 JSON。
# exit 0 = 成功；exit 1 = 失败；exit 2 = 被阻止（前置条件未满足）
set -euo pipefail

inputs=$(cat)
# ... 工作流逻辑 ...
echo '{"status":"success","metrics":{"merge_time_seconds":38}}'
```

运行时将序列化的 `inputs` JSON 管道输入 spine 的 stdin，从 stdout 读取输出 JSON。退出码决定主状态；JSON 输出提供指标值。

**TOML spine（`spine_lang: toml`，仅声明式）：**

允许用于纯声明式工作流，将 CLI 调用与参数模板链式组合。engram 运行时读取 TOML 并按序执行声明的步骤。不支持通用计算；逻辑请使用 Python 或 bash。TOML spine 始终无副作用，除非调用的命令本身有副作用——这种情况仍须声明。

---

### §5.4 Fixtures 格式

Fixtures 是工作流的测试套件。运行时通过 `engram workflow test <name>` 执行它们。没有任何 passing fixture 的工作流无法从 `draft` 转为 `active`。

**最低要求：** 至少一个 `success-case.yaml` 和至少一个 `failure-case.yaml`。鼓励添加更多 fixtures；请使用描述性命名（如 `success-concurrent.yaml`、`failure-rebase-conflict.yaml`）。

**Fixture 文件格式：**

```yaml
# success-case.yaml
name: 无冲突的典型合并请求
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
name: 无法解决的 rebase 冲突
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
    description: 失败时 spine 必须将仓库恢复干净状态（无游离 HEAD，无部分合并）
```

**断言类型**（最小必需集；工具可定义更多类型）：

| 类型 | 语义 |
|---|---|
| `metric_threshold` | 断言 `metrics.<metric>` 满足 `<op>` `<value>`（op：`le`、`ge`、`eq`、`lt`、`gt`）。 |
| `no_exception` | 断言 spine 返回时未抛出未捕获异常。 |
| `status_equals` | 断言 `outputs.status == value`。 |
| `no_dirty_state` | 断言执行环境在运行后干净（工作流定义；`description` 字段为人类可读的理由）。 |

一次 fixture 运行在 `rev/<rev>/outcome.tsv` 中追加一行：时间戳、fixture 名称、状态（通过/失败）以及 spine 返回的 metrics 值。`outcome.tsv` 在修订版本生命周期内只追加。

---

### §5.5 `metrics.yaml` 格式

`metrics.yaml` 定义工作流追踪哪些结果度量值、如何跨运行聚合，以及哪个指标驱动自学习棘轮。

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
  tolerance: 0.02            # 小数；超出此值的回退会触发回滚

complexity_budget:
  max_lines_factor: 1.5      # 新 spine 的行数不得超过当前 spine 行数的 1.5 倍
```

**字段语义：**

- `metrics[].aggregation` — 在计算一个修订版本窗口内的指标时，单次运行值的合并方式。`p95` 适用于延迟指标；`sum` 适用于累计计数；`mean` 适用于比率。
- `metrics[].source` — `outcome_field` 表示值直接从 spine 的 `outputs.metrics.<field>` 映射读取。未来可能定义更多来源（如 `journal_aggregate`）。
- `primary` — 自学习引擎优化的指标。必须与 `metrics` 列表中某条 `name` 匹配。棘轮将新修订版本的 `primary` 指标与当前修订版本的 `primary` 指标比较；若比较不满足 `ratchet_rule`，则拒绝新修订版本。
- `ratchet_rule.direction` — `minimize` 表示值越低越好（延迟、错误数）；`maximize` 表示值越高越好（成功率、覆盖率）。
- `ratchet_rule.tolerance` — 小数宽容度。≤2% 的回退（`tolerance: 0.02`）被接受；更差则触发回滚。这防止指标噪声在渐进改进过程中被误读为回退。
- `complexity_budget.max_lines_factor` — 自学习引擎拒绝超过 `当前 spine 行数 × max_lines_factor` 的提议 spine。这实现了 autoresearch 的简洁性准则：拒绝以倍增复杂度换取微小指标收益的更改。

---

### §5.6 修订版本（`rev/`）生命周期

`rev/` 目录是工作流所有历史状态的只追加记录。engram 永不删除任何修订版本。

**规则：**

1. 每轮自学习创建 `rev/rN/`，其中 N = max(现有修订编号) + 1。
2. `rev/rN/` 是完整快照：`spine.<ext>`、`workflow.md`、`fixtures/`、`metrics.yaml` 和 `outcome.tsv`。
3. `rev/<rev>/outcome.tsv` 在修订版本内只追加。每次对该修订版本运行测试套件均追加一行；行数随多次运行累积。
4. 仅当新修订版本通过双维度评分时，`current` 符号链接才原子地指向 `rev/rN/`：静态得分 ≥ 60/100（SPEC 合规 + fixtures 可解析 + 无密钥）以及性能得分 ≥ 阈值/40（fixtures 通过 + 主指标改进超过 `tolerance`）。双维度评分标准在 `DESIGN.md §5.3` 中规定。
5. 失败的修订版本保留在磁盘上。`current` 符号链接不指向它们。它们是审计证据，可通过 `engram workflow history <name>` 查看。
6. 手动回滚：`engram workflow rollback <name> --to=rN` 将 `current` 重新指向 `rev/rN/`。不删除任何文件。
7. 修订版本不被 `engram` 删除。将其物理移至 `~/.engram/archive/workflows/<name>/rev/rN/` 需要显式的操作员操作（`engram workflow archive-rev <name> --rev=rN`）。

**棘轮不变量。** `current` 处的主指标在 `ratchet_rule.direction` 声明的方向上单调不退化。若自学习无法在容差范围内产生改进指标的修订版本，`current` 保持在现有修订版本不变。自动操作的结果不会使 `current` 处的指标在容差范围外回退；只有显式的手动回滚才能将 `current` 移至指标更差的修订版本。

**阶段闸门。** 连续 K=5 轮自学习（无论成败）后，引擎暂停并将差异摘要写入 review 队列（`engram review`）。人工确认后才能开始下一阶段。这是 autoresearch 阶段闸门在工作流演化中的具体应用。

---

### §5.7 生命周期状态

Workflow 与 Memory 资产参与相同的生命周期：

```
draft → active → stable → deprecated → archived → tombstoned
```

**工作流特定的转换规则：**

| 转换 | 触发条件 |
|---|---|
| `draft → active` | `engram workflow validate <name>` 通过：结构正确且至少一个 fixture 运行完成（不一定通过）。 |
| `active → stable` | 主指标在连续 N=10 轮自学习中保持在 5% 误差带内。指标已停止改进——工作流已收敛。 |
| `active → deprecated` | 显式操作员操作（`engram workflow deprecate <name>`），**或** 在依赖升级后 spine 在所有 fixtures 上失败。第二种情况下，engram 自动将工作流标记为 `needs-attention`；不自动降级。降级需操作员确认。 |
| `stable → deprecated` | 与 `active → deprecated` 相同。 |
| `deprecated → archived` | N=180 天内无任何调用（`runs.jsonl` 在 180 天内无条目）且操作员确认。 |
| `archived → tombstoned` | 在 `archived` 状态下保持 6 个月，无引用者（无 `workflow_ptr` Memory 资产指向它），且操作员确认。 |

**`needs-attention` 标记。** 这不是生命周期状态——而是一个布尔型 frontmatter 标记（`needs_attention: true`），当 spine 在外部变更（依赖升级、环境变更）后 fixtures 失败时由 engram 添加。它不降低生命周期状态；它表示该工作流需要人工审查，下一轮自学习在此之前不应运行。

---

### §5.8 完整示例：`git-merge` 工作流

一个完整的最小示例。文件路径相对于 `<project>/.memory/workflows/git-merge/`。

**`workflow.md`：**

```markdown
---
name: git 合并（squash、changelog、通知）
description: 将 feature 分支 squash 合并到 main，并附 changelog 条目和发版通知
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
tags: [git, 合并, 发版]
---

## 用途

编码平台团队标准的合并流程：合并前检查、带规范 commit 消息的 squash 合并、CHANGELOG.md 条目自动生成，以及发版通知。取代了之前以 `feedback` Memory 形式存储的非正式检查清单。

## 适用时机

合并任何涉及平台服务代码的 feature 分支到 `main` 时使用。纯文档分支走更轻量的路径；hotfix 分支有独立的 `git-hotfix` 工作流，带有不同的发版门控，不使用本工作流。

## 预期产出

分支被 squash 合并到 `main`。`CHANGELOG.md` 追加一条条目。格式化的发版摘要发送至配置的通知渠道。`merge_time_seconds` 记录在指标跟踪器中。目标：p95 合并时间 ≤ 90 秒。

## 失败模式

- **Rebase 冲突**：spine 以 `status: failure`、`failure_mode: rebase_conflict` 退出。仓库保持干净状态（无部分合并、无游离 HEAD）。调用方手动解决冲突后重新运行。
- **覆盖率门控失败**：spine 以 `status: failure`、`failure_mode: coverage_gate` 退出。不尝试合并。调用方修复覆盖率后重新运行。
- **通知超时**：spine 以 `status: success` 退出，但 `warnings` 中包含 `notification_timeout`。合并成功；调用方手动检查通知渠道。

## 方法论依据

该团队强制要求 squash 合并，因为线性的 `main` 历史简化了 bisect。CHANGELOG 步骤内联（而非独立工作流），因为合并与 changelog 是原子的：没有 CHANGELOG 条目的合并是不完整的完成。简洁性准则（见 `metrics.yaml`）防止自学习引擎在没有显著指标改进的情况下添加额外步骤。
```

**`spine.py`：**

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
        "trace": [f"squash 合并 {source_branch} 到 {target_branch}"],
    }

def _now_epoch() -> float:
    import time
    return time.time()
```

**`fixtures/success-case.yaml`：**

```yaml
name: 无冲突的干净合并
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

**`metrics.yaml`：**

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

### §5.9 与 `workflow_ptr` Memory 的关系

`workflow_ptr` Memory 子类型（§4.6）是 Workflow 的轻量可发现入口。`MEMORY.md` 在每次 LLM 会话中加载，必须保持精简；完整的 `workflow.md` 和 spine 只在任务真正匹配时才加载。`workflow_ptr` 充当桥梁：给 LLM 足够的信息——工作流做什么、何时使用、预期产出——以决定是否加载完整过程。

实际工作方式：`MEMORY.md` 包含对 `[[local/workflow_ptr_git_merge]]` 的引用。LLM 在启动时读取 `workflow_ptr` 正文。当任务涉及合并分支时，LLM 从 `workflows/git-merge/` 加载完整的 `workflow.md`。任务准备好执行时，它调用 `engram workflow run git-merge --inputs='{"repo_url":...}'`，该命令调用 `spine.py` 中的 `main(inputs)` 并将结果记录到 `journal/runs.jsonl`。

`workflow_ptr` 是入口；Workflow 目录是实现。两者缺一不可。

---

---

## 6. 知识库资产格式

### §6.0 概述

知识库（KB）文章是 engram 用于存放**扩展领域材料**的格式——这类参考资料供开发者有意识地阅读，按章节浏览，并在工作触及该领域时反复查阅。与 Memory（单一原子断言）不同，也与 Workflow（可执行过程）不同，KB 是多章节散文：架构指南、迁移手册、入职参考文档、设计背景说明。

**创作模型：** 人类撰写主要内容（章节），engram 工具定期将其编译为简洁的 `_compiled.md` 摘要，供相关性闸门快速加载，无需逐章读取。摘要是**缓存推导物**——始终可从章节中重新生成，本身没有权威性。章节文件是唯一的事实来源。

**设计灵感：** Karpathy 的 LLM Wiki 模式——写入侧综合，随时间累积。每次章节更新后，摘要即被重新编译；交叉引用已预先解析；LLM 拿到的是现成的综合结果，而非每次查询都从原始文档重新推导。

**KB 的定位：** 若一个主题需要多章节，它属于 KB，而非 Memory。一条规则或事实放 Memory；需要在浏览器里打开、上下滚动阅读的内容放 KB。`_compiled.md` 摘要承担 KB 的快速检索职责；它取代了"为复杂领域创建摘要 Memory"的反模式。

---

### §6.1 目录结构

KB 文章是一个**目录**，而非单个文件。`<scope-root>/kb/<topic>/` 内部结构如下：

```
<scope-root>/kb/<topic>/
├── README.md                       # 文章入口（必需）
├── 01-overview.md                  # 第一章（至少需要一章）
├── 02-architecture.md              # 其他章节（编号保证稳定顺序）
├── 03-migration-guide.md
├── assets/                         # 二进制附件（图片、PDF、图表）
│   ├── arch-diagram.svg
│   └── flowchart.png
├── _compiled.md                    # LLM 生成的摘要（自动维护）
└── _compile_state.toml             # 编译元数据（源文件哈希、时间戳）
```

`<scope-root>` 对应关系：

| Scope | 根路径 |
|-------|--------|
| `project` | `<project>/.memory/` |
| `team` | `~/.engram/team/<name>/` |
| `org` | `~/.engram/org/<name>/` |
| `pool` | `~/.engram/pools/<name>/` |
| `user` | `~/.engram/user/` |

章节文件命名为 `NN-slug.md`，其中 `NN` 为零填充两位序号，确保人类可预测的阅读顺序。新章节追加到末尾；允许跳号（如 `01`、`02`、`05`），但 MUST 在 `README.md` 的 `chapters` 列表中体现。

`assets/` 目录 MUST 是文章目录的直接子目录。章节引用中不允许使用 `../` 转义。二进制附件以路径引用存储——不得在 markdown 正文中内联为 base64。

---

### §6.2 `README.md` 格式

每篇 KB 文章都需要在文章根目录下提供 `README.md`。它是发现入口：相关性闸门读取它，决定是否加载完整文章。

**必需的前置元数据：**

```yaml
---
name: "平台可观测性手册"
description: "指标管道、告警路由和值班流程的参考文档。≤150 字符。"
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

**前置元数据字段说明：**

| 字段 | 类型 | 语义 |
|------|------|------|
| `name` | string | 文章标题；用于图谱和界面显示 |
| `description` | string | ≤150 字符；相关性闸门不打开章节即可读取 |
| `type` | 字面量 `kb` | 标识该目录为 KB 文章 |
| `scope` | 枚举 | `org` / `team` / `user` / `project` / `pool` |
| `primary_author` | string | 人类主要作者的账号或邮箱 |
| `chapters` | list[string] | 有序章节文件名列表；权威阅读顺序 |
| `compiled_from` | list[string] | 最近一次 `_compiled.md` 生成时包含的文件（由 `engram kb compile` 自动维护） |
| `compiled_at` | ISO 8601 | 最近一次 `_compiled.md` 生成的时间戳（自动维护） |
| `lifecycle_state` | 枚举 | `draft` / `active` / `stable` / `deprecated` / `archived` |

**正文结构：** `README.md` 正文包含三个部分：

1. **摘要**（1–3 段）：文章覆盖内容、范围、目标读者。
2. **目录**：指向各章节文件的链接，可由 `engram kb toc` 自动生成。
3. **`## 何时阅读本文`** 一节：为 LLM 编写的触发条件——"当任务涉及 X 或 Y 时加载本文章"。这是相关性闸门决定是否展示完整文章的主要信号。

---

### §6.3 章节文件

每个 `NN-slug.md` 是包含可选前置元数据和自由格式 markdown 正文的独立章节。

**可选前置元数据：**

```yaml
---
title: "架构概览"
updated: "2026-04-18"
sources:
  - "https://internal-wiki.example.com/observability/v2"
---
```

**正文约定：**

- 标准 markdown，支持 wiki 链接。
- 指向同级章节的交叉链接使用相对路径：`[查看架构细节](02-architecture.md)`。
- 引用 engram Memory 资产使用 `@memory:<id>`（例如 `@memory:local/feedback_alerting_policy`）。
- 引用 Workflow 资产使用 `@workflow:<name>`（例如 `@workflow:deploy-canary`）。
- Mermaid 图表内联写入围栏代码块（ ` ```mermaid ` ）。外部图表文件放入 `assets/`。

---

### §6.4 `assets/` 目录

`assets/` 目录存放章节正文引用的二进制或大文件附件。

- **支持类型：** 图片格式（`png`、`svg`、`jpg`、`webp`）、PDF、代码片段（`.py`、`.ts`、`.sh`）及其他静态文件。
- **Mermaid 内联：** Mermaid 图表属于章节正文的围栏代码块，不放入 `assets/`。
- **路径引用：** 章节通过相对路径引用附件——`![架构图](assets/arch-diagram.svg)`——不允许内联 base64。
- **禁止转义：** 所有资产引用 MUST 相对于文章目录。包含 `../` 的路径为校验错误。

---

### §6.5 `_compiled.md` 契约

编译摘要是**缓存推导物**。它不是权威来源。`README.md` 和章节文件才是权威。`_compiled.md` 存在的唯一目的是为相关性闸门提供快速、高密度的摘要，无需读取每个章节即可加载。

**`_compiled.md` 顶部必需的头部块：**

```
<!-- AUTO-GENERATED from chapters. DO NOT EDIT DIRECTLY. -->
<!-- compile-tool: engram kb compile -->
<!-- compiled_at: 2026-04-18T12:00:00Z -->
<!-- compiled_from: README.md, 01-overview.md, 02-architecture.md, 03-runbooks.md -->
<!-- source_hashes: sha256(README.md)=abc123... sha256(01-overview.md)=def456... sha256(02-architecture.md)=789abc... sha256(03-runbooks.md)=fed321... -->
```

**正文约束：**

- 为 LLM 检索优化：层级标题与章节结构对齐，密集但可导航。
- 无固定行数上限。摘要通常远小于章节合计长度——是综合，不是镜像。
- 每个章节 MUST 在摘要中有至少一个对应的标题章节，不允许静默跳过任何章节。
- 在可深入之处必须提供指向源章节的交叉链接：`[查看第 02 章](02-architecture.md)`。LLM 需要深度信息时，跟随链接而非继续读摘要。

**`_compile_state.toml` 格式：**

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
model        = "local/none"   # 或 "anthropic/claude-3-5-sonnet" 等

[stale]
is_stale    = false
detected_at = null
```

`model` 字段记录编译摘要所使用的工具。`"local/none"` 表示基于规则的（非 LLM）编译。任何 Anthropic 或第三方模型标识符同样有效。

**陈旧检测：** `engram kb compile --check` 遍历 `_compile_state.toml` 中列出的所有章节文件，计算每个文件的 sha256，并与 `[source.hashes]` 对比。任何不匹配将把 `is_stale` 设为 `true` 并在 `detected_at` 记录检测时间戳。陈旧的 `_compiled.md` 不会被删除——旧版本仍有价值。它会在 `engram review` 输出中以警告形式标记。

**重新编译触发方式：**

1. **手动：** `engram kb compile <topic>` — 重新生成摘要并更新 `_compile_state.toml`。
2. **监视器：** engram 的文件 mtime 监视器（参见 DESIGN §7.4）检测到章节变更后，调度重新编译。
3. **陈旧加载时：** 若相关性闸门加载 `_compiled.md` 时检测到它已陈旧，会向 LLM 上下文发出警告注释（"此摘要自 `<detected_at>` 起已陈旧"），但不会失败或跳过该资产。

---

### §6.6 完整示例

以下展示一篇用于计费系统迁移项目的 KB 文章，所有值均为示意。

**`kb/acme-billing-migration/README.md`**

```markdown
---
name: "ACME 计费系统迁移指南"
description: "从旧版计费系统迁移至 v2 支付 API 的端到端参考。涵盖数据模型变更、回滚流程和切换清单。"
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

## 摘要

ACME 计费系统正在从 v1 收费 API 迁移至 v2 支付 API。本指南覆盖完整的迁移弧线：迁移原因、变更后的数据模型，以及每个环境的逐步切换手册。

目标读者：计费团队工程师，以及可能需要在迁移过程中执行回滚的值班 SRE。

## 目录

- [01 概述](01-overview.md) — 背景、目标与非目标
- [02 数据模型](02-data-model.md) — Schema 差异、字段重命名、可空性变更
- [03 切换手册](03-cutover-runbook.md) — 预检、切换、回滚

## 何时阅读本文

当任务涉及以下情形时，请加载本文章：
- 对计费收费流程、订阅续期或发票生成的任何变更
- 调试可能源于 v1/v2 API 版本不匹配的支付失败
- 规划涉及 `billing-service` 或 `payment-gateway` 的部署
- 计费相关告警的值班排查
```

**`kb/acme-billing-migration/01-overview.md`**

```markdown
---
title: "概述"
updated: "2026-04-15"
sources:
  - "https://internal.acme.example.com/billing/v2-migration-rfc"
---

## 迁移原因

v1 收费 API 建于 2019 年，不支持幂等键，导致重试不安全。v2 支付 API 每次收费调用都要求传入幂等键，并返回结构化错误码而非仅靠 HTTP 状态。

## 目标

- 切换过程中零收入损失（切换前进行影子模式验证）
- 任意环境均可在 5 分钟内完成回滚
- 所有收费事件记录到 `payments.jsonl` 以备审计

## 非目标

- 变更定价逻辑（单独项目）
- 迁移历史发票 PDF（范围外）

数据模型的字段级差异请参见 [数据模型变更](02-data-model.md)。
组织级重试策略请参考 @memory:org/feedback_payment_retry_policy。
```

**`kb/acme-billing-migration/_compiled.md`**

```markdown
<!-- AUTO-GENERATED from chapters. DO NOT EDIT DIRECTLY. -->
<!-- compile-tool: engram kb compile -->
<!-- compiled_at: 2026-04-15T09:30:00Z -->
<!-- compiled_from: README.md, 01-overview.md, 02-data-model.md, 03-cutover-runbook.md -->
<!-- source_hashes: sha256(README.md)=1a2b3c... sha256(01-overview.md)=4d5e6f... sha256(02-data-model.md)=7a8b9c... sha256(03-cutover-runbook.md)=0d1e2f... -->

# ACME 计费系统迁移指南 — 摘要

**范围：** 从 v1 收费 API 迁移至 v2 支付 API。如需执行步骤请加载完整章节。

## 概述 [→ 01-overview.md](01-overview.md)

迁移到 v2 以支持幂等键和结构化错误码。目标：零收入损失，5 分钟回滚，完整审计记录。非目标：定价逻辑、历史 PDF。

## 数据模型 [→ 02-data-model.md](02-data-model.md)

关键重命名：`charge_id` → `payment_id`；`amount_cents` → `amount`（十进制）。新必填字段：`idempotency_key`（UUID）。`status` 枚举新增 `pending_capture`。可空性变更：v2 中 `description` 现为可空。

## 切换手册 [→ 03-cutover-runbook.md](03-cutover-runbook.md)

三个阶段：（1）影子模式——v2 调用影子 v1，对比响应；（2）切换——按环境（预发 → 生产）将 100% 流量路由至 v2；（3）回滚——翻转功能标志，排空在途 v2 请求，重新启用 v1 路径。回滚目标：≤5 分钟。
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

### §6.7 与 Memory 和 Workflow 的关系

KB 占据 Memory 单事实断言与 Workflow 可执行过程之间的空间。下表指导选择决策：

| 场景 | 选择 |
|------|------|
| 一条事实、规则、偏好或指针 | Memory |
| 包含可执行步骤的过程 | Workflow |
| LLM 在任务触及该领域时会阅读的多章节参考 | KB |
| KB 文章的快速查阅摘要 | 使用 KB 的 `_compiled.md`——不要创建摘要 Memory |

**编译（compile）与取代（supersede）的区别**至关重要：

- `_compiled.md` 是**推导物**——始终可从章节来源重新计算。陈旧摘要是时间差，不是错误；章节仍然正确。陈旧以警告形式暴露，不作为错误处理。
- Memory 的 `supersedes` 是**权威替换**——被取代的资产确实已错误或过时，不得再被引用。取代是永久性的；重新编译是常规操作。

避免创建正文为 KB 文章摘要的 Memory 资产。该摘要职责属于 `_compiled.md`。`workflow_ptr` Memory（§4.6）可在正文中用交叉链接引用 KB 文章，但摘要本身留在 KB 内。

---

### §6.8 生命周期

KB 文章遵循与 Memory 和 Workflow 资产相同的生命周期状态机（§4.4）：`draft → active → stable → deprecated → archived`。KB 专有的状态转换：

| 转换 | 条件 |
|------|------|
| `draft → active` | `README.md` 存在，`chapters` 列表有 ≥1 个文件且该文件存在，且已生成初始 `_compiled.md` |
| `active → stable` | 30 天内无实质性章节修改，且该文章被 ≥1 个 Memory 或 Workflow 资产引用 |
| `active/stable → deprecated` | 操作者显式设置 `lifecycle_state: deprecated`，或所有章节文件均已删除 |
| `deprecated → archived` | `engram kb archive <topic>` 将文章目录移动至 `~/.engram/archive/kb/<topic>/`；在 journal 中记录墓碑条目 |

已弃用的 KB 文章仍可读取和索引，在 `engram review` 中以弃用通知标记。活跃文章中陈旧的 `_compiled.md` 不会改变文章的生命周期状态——编译陈旧是维护问题，不是生命周期事件。

---

---

## 7. MEMORY.md 层级式落地索引

### §7.0 概述

每个 engram 会话都从同一个文件开始：`.memory/MEMORY.md`。这是**落地索引**——LLM 在启动时读取的唯一文件，之后才会考虑其他记忆资产。其余一切按需通过相关性闸门（Relevance Gate）加载。

**设计约束：** 启动上下文注入必须在 100ms 内完成（性能预算，参见术语表 §20）。注入内容的目标大小为 600–900 个 token，从而将 LLM 上下文窗口的 95% 以上保留给实际工作——与 MemPalace 对 L0+L1 内容的唤醒成本目标一致。

**核心思想：** MEMORY.md 不存放每条记忆，而是存放顶层指针。丰富的细节保存在主题子索引（`index/<topic>.md`）和独立资产文件中，只有当相关性闸门判断其与当前任务相关时才会加载。

**v0.1 兼容说明：** v0.1 强制要求 `MEMORY.md ≤ 200 行`，将所有记忆引用压入一个受限文件。随着存储规模增长，这一上限变得难以为继——用户多年积累数千条记忆，200 行根本无法有效组织。v0.2 用一个**三层层级**取代这一上限，规模可以无限扩展，而启动成本保持恒定。

MEMORY.md 保持小体量，不是因为有硬性行数上限，而是因为它存储的是指针而非内容。文件可以按需增长；`engram review` 工具通过百分位长度信号（术语表 §16）在文件相对自身历史出现异常增长时发出提示。

---

### §7.1 三层层级

该层级以 MemPalace 的四层唤醒栈为参考（L0 始终加载标识 / L1 始终加载核心内容 / L2 按需加载主题 / L3 深度搜索），并适配 engram 的 Markdown 文件系统。engram 将 L0 和 L1 合并为单一的 MEMORY.md 落地索引，将 L2 和 L3 分别映射为主题子索引和独立资产文件。

| 层级 | 内容 | 大小目标 | 加载时机 |
|------|------|----------|----------|
| **L1 — MEMORY.md** | 顶层落地索引：范围概览 + 主题子索引指针 + 内联高频项 | 约 100 条或约 150 行 | 始终在启动时加载（<100ms） |
| **L2 — `index/<topic>.md`** | 按主题组织的子索引，按资产类别列出该主题下的所有资产 | 无固定上限 | 相关性闸门选中该主题时加载 |
| **L3 — 独立资产文件** | 完整的 Memory、Workflow 和 KB 文件 | 任意大小 | 相关性闸门选中该资产时加载 |

**导航规则：**

1. 每个资产从 L1 出发最多需要 2 跳即可到达（L1 → L2 → L3），或 1 跳（对于高频项，L1 → L3）。
2. L1 应保持紧凑；启动成本目标为 L1 内容不超过 900 个 token。
3. L1 可以内联固定（pin）特定资产，使其单跳可达——适用于每个会话都需要的项，例如用户身份或关键行为规则。
4. L2 主题文件是可选的。资产数量少于 50 的小型存储，仅用 L1 + L3 即可正常工作，可完全省略 `index/` 目录。
5. 相关性闸门独立地在 L2 和 L3 层级上运行：选中一个主题子索引并不意味着无条件加载其中所有资产。

---

### §7.2 MEMORY.md 格式

MEMORY.md 采用固定的分节结构。读写 MEMORY.md 的工具必须保留此结构。重写时必须保留未知章节。

**必需的顶层分节**（按序排列）：

```markdown
# MEMORY.md

<!-- engram v0.2 landing index. See SPEC.md §7. -->

## Identity

- [用户档案](local/user_profile.md) — <一行摘要>

## Always-on rules

- [推送需要明确确认](local/feedback_push_confirm.md) — <摘要>
- [禁止破坏性 git 操作](local/feedback_no_destructive.md) — <摘要>

## Topics

### Active work → [index](index/active-work.md) — 12 entries
- [Acme 结账服务迁移](local/project_acme_checkout_migration.md) — <摘要>

### Platform conventions → [index](index/platform.md) — 23 entries

### Reference material → [index](index/reference.md) — 8 entries

## Subscribed pools

- [pool/design-system](pools/design-system/MEMORY.md) — 设计系统规范（团队级）
- [pool/kernel-work](pools/kernel-work/MEMORY.md) — Linux 内核开发知识（用户级）

## Recently added

- [2026-04-18 新规则](local/feedback_recent.md) — 3 天前
```

**格式规则：**

- 顶层分节使用 `## Identity`、`## Always-on rules`、`## Topics`、`## Subscribed pools`、`## Recently added`。
- 单条条目格式：`- [标题](相对路径.md) — 一行摘要`
- 主题分节标题：`### <名称> → [index](index/<topic>.md) — N entries`
- 一行摘要必须不超过 150 个字符。相关性闸门使用这些摘要进行打分，再决定是否加载完整资产。
- 主题标题中的 `N entries` 计数由 `engram index rebuild` 更新，仅供参考。
- 各分节可以为空，但仍须存在，以便工具定位插入点。
- **无 200 行上限。** MEMORY.md 应保持紧凑，但 engram 不会拒绝写入或校验更长的文件。百分位长度信号（术语表 §16）以建议方式指出需要审查的候选对象，不阻断写入。
- 相对路径从 `.memory/` 目录根解析。所有路径必须是相对路径，不允许绝对路径。

**受保护区块：** 位于 `<!-- engram:preserve-begin -->` 和 `<!-- engram:preserve-end -->` 标记之间的内容不会被 `engram index rebuild` 修改或删除。详见 §7.4。

---

### §7.3 主题子索引（`index/<topic>.md`）

主题子索引（L2）列出属于某一主题领域的所有资产。对于资产数量超过 50 的存储，这是可选但强烈推荐的中间层。

**格式：**

```markdown
# index/platform.md

<!-- Topic: Platform conventions. Auto-generated by `engram index rebuild --topic=platform`. -->

## Memory

- [TypeScript 配置规范](../local/feedback_ts_config.md) — 始终使用 strict 模式；tsconfig 继承基础配置
- [Monorepo 版本策略](../local/project_monorepo_versioning.md) — 各包使用独立 semver；不锁步发布

## Workflows

- [依赖升级流程](../workflows/dep-upgrade/workflow.md) — 先审计，先升补丁版本，再升次版本

## Knowledge Base

- [平台架构概览](../kb/platform-arch/README.md) — 五层架构图；从接入到 API 的数据流

## Recently modified

- 2026-04-16 [TypeScript 配置规范](../local/feedback_ts_config.md)
- 2026-04-12 [Monorepo 版本策略](../local/project_monorepo_versioning.md)
```

**主题子索引规则：**

- 主题 slug（`platform`、`data-pipelines`、`security-review` 等）是自由形式、基于约定的，engram 不强制受控词汇表。
- 内容按资产类别分组：`## Memory`、`## Workflows`、`## Knowledge Base`。如果某主题在该类别下没有资产，对应节可以省略。
- 交叉引用使用从 `index/` 目录出发的相对路径（`../local/...`、`../workflows/...`、`../kb/...`）。
- `## Recently modified` 列出该主题下最近修改的 5 个资产，便于快速定位。
- 一行摘要同样遵循不超过 150 字符的规则。
- 子索引无大小上限。拥有 200 个资产的主题对应的就是 200 条目的索引文件。

---

### §7.4 生成与维护

**自动生成命令：**

- `engram index rebuild` — 从当前资产集重新生成 MEMORY.md 及所有 `index/*.md` 文件。通过保护标记保留用户手动编辑的"固定"项。此命令是幂等的。
- `engram index rebuild --topic=<topic>` — 仅重建某个主题子索引。适用于主题已变更但不需要完整重建的场景。
- `engram index check` — 校验 MEMORY.md 和所有主题子索引中的条目是否指向实际存在的文件。将缺失目标报告为 `E-IDX-001` 错误（§12 校验）。

**自动触发：** 当 engram 监视器检测到资产添加、删除或重命名时，会自动重新生成受影响的 L1 分节以及相关的 L2 主题子索引。监视器不会在每次变更时重新生成完整的 MEMORY.md——只更新需要更新的部分。

**保留用户自定义：**

MEMORY.md 和 `index/*.md` 文件可以部分手动编辑。engram 的 rebuild 会保留所有被保护标记包裹的内容：

```markdown
<!-- engram:preserve-begin -->
## 我的自定义看板
- [我的入职笔记](local/my_onboarding_notes.md) — 手工策划的分节
- [活跃实验](local/active_experiments.md) — 不属于任何主题桶
<!-- engram:preserve-end -->
```

`<!-- engram:preserve-begin -->` 和 `<!-- engram:preserve-end -->` 之间的内容**绝不会被** `engram index rebuild` 修改或删除。标记本身也原样保留。允许存在多个保护块；每个块独立处理。

**主题分类启发式规则（由 `engram index rebuild` 使用）：**

1. **主要规则：** 按 `tags:` frontmatter 字段分组。带有 `tags: [platform, typescript]` 的资产会同时出现在 `platform` 和 `typescript` 主题子索引中。
2. **次要规则：** 如果没有 `tags:` 字段，按 Memory 子类型分组（`user` → 身份主题，`feedback` → 规则主题，`project` → 活跃工作主题，`reference` → 引用主题）。
3. **兜底规则：** 在默认主题内按字母顺序排列。
4. **手动覆盖：** 在 `.engram/topics.toml` 中定义显式主题分配。此文件是可选的；存在时，其分配优先于启发式规则。

`.engram/topics.toml` 示例：

```toml
[assignments]
"local/feedback_ts_config.md"   = "platform"
"local/feedback_no_destructive.md" = "always-on"
"local/project_checkout_migration.md" = ["active-work", "platform"]
```

`topics.toml` 中的资产可以通过数组形式归属多个主题。

---

### §7.5 v0.1 → v0.2 兼容性

v0.1 存储采用扁平的 `.memory/*.md` 布局，MEMORY.md 不超过 200 行，不包含 `index/` 子目录，也没有主题子索引。

**迁移路径（`engram migrate --from=v0.1`）：**

1. 所有现有的 `.memory/*.md` 资产文件移动到 `.memory/local/*.md`，保留文件名。
2. MEMORY.md 按 v0.2 格式重新生成，将原有的扁平列表替换为结构化的 `## Identity / ## Always-on rules / ## Topics / ...` 分节。
3. 如果 v0.1 MEMORY.md 包含无法识别为自动生成内容的手动编辑部分，迁移工具会用 `<!-- engram:preserve-begin -->` / `<!-- engram:preserve-end -->` 标记将其包裹，防止后续 rebuild 丢弃这些内容。
4. 主题子索引（`index/`）仅在存储资产数量超过 50 时创建。较小的存储保留纯 L1 导航。
5. 不删除任何数据。迁移是严格的增量操作：新建目录、新建索引文件、重构 MEMORY.md。原始资产内容不变。

**只读 v0.1 兼容窗口：v0.2 发布后 6 个月。** 在此期间，`engram` 读取 v0.1 格式存储并发出迁移警告，但不拒绝操作。兼容窗口关闭后，`engram` 在对 v0.1 格式存储执行任何写操作之前都需要先完成迁移。

存储版本通过 `~/.engram/version` 文件标识。v0.1 存储没有版本文件，或文件内容为 `0.1`；v0.2 存储文件内容为 `0.2`。

---

### §7.6 完整示例

以下示例展示一个中等规模项目存储（约 500 个资产），项目名称为虚构的 `acme-checkout-service`。示例展示了实际 MEMORY.md 的密度、主题组织方式，以及运行时的 L1 → L2 → L3 导航路径。

**`.memory/MEMORY.md`**（约 120 行）：

```markdown
# MEMORY.md

<!-- engram v0.2 landing index. See SPEC.md §7. -->

## Identity

- [用户档案](local/user_profile.md) — 资深全栈工程师；偏好 TypeScript + Go；直接沟通风格

## Always-on rules

- [禁止破坏性 git](local/feedback_no_destructive.md) — 禁止 force-push main；reset --hard 需确认
- [推送需确认](local/feedback_push_confirm.md) — 即使非 main 分支，git push 前也须询问
- [优先不可变](local/feedback_immutable.md) — 始终创建新对象；禁止原地修改
- [文件保持小型](local/feedback_file_size.md) — 典型 200–400 行；最大 800 行；大文件提取工具函数

## Topics

### Active work → [index](index/active-work.md) — 18 entries
- [结账迁移：第二阶段](local/project_checkout_migration_p2.md) — 将购物车服务迁移至新定价引擎；预计 2026-04-25 完成
- [Auth 重构](local/project_auth_refactor.md) — 替换 JWT 库；阻塞于安全审查

### Platform conventions → [index](index/platform.md) — 31 entries
- [TypeScript strict 模式](local/feedback_ts_config.md) — 始终继承基础 tsconfig；要求 strict: true
- [API 响应格式](local/feedback_api_response.md) — 始终使用含 success/data/error 字段的 ApiResponse<T> 包装

### Testing → [index](index/testing.md) — 14 entries
- [最低 80% 覆盖率](local/feedback_coverage.md) — CI 强制执行；低于阈值不得合并

### Data pipelines → [index](index/data-pipelines.md) — 22 entries

### Reference → [index](index/reference.md) — 12 entries
- [内部 API 文档](local/reference_internal_api.md) — https://internal.acme.example/api/v3/docs

## Subscribed pools

- [pool/acme-platform](pools/acme-platform/MEMORY.md) — Acme 平台级工程规范（团队级）
- [pool/security-baseline](pools/security-baseline/MEMORY.md) — 安全团队强制规则（组织级）

## Recently added

- [2026-04-18 不可变规则](local/feedback_immutable.md) — 代码审查后新增；适用于所有 JS/TS 代码
- [2026-04-16 第二阶段迁移](local/project_checkout_migration_p2.md) — 第一阶段已上线；第二阶段开始
- [2026-04-14 Auth 重构](local/project_auth_refactor.md) — 新工作项

<!-- engram:preserve-begin -->
## 我的调试笔记
- [不稳定测试排查](local/project_flaky_test_notes.md) — 个人笔记；不归属任何主题
<!-- engram:preserve-end -->
```

**`.memory/index/platform.md`**（约 35 行）：

```markdown
# index/platform.md

<!-- Topic: Platform conventions. Auto-generated by `engram index rebuild --topic=platform`. -->

## Memory

- [TypeScript strict 模式](../local/feedback_ts_config.md) — 始终继承基础 tsconfig；要求 strict: true
- [API 响应格式](../local/feedback_api_response.md) — 始终使用含 success/data/error/meta 字段的 ApiResponse<T>
- [Monorepo 版本策略](../local/feedback_monorepo_versioning.md) — 各包独立 semver；不锁步发布
- [ESLint 基准](../local/feedback_eslint.md) — 继承 @acme/eslint-config；不经审查不允许覆盖
- [错误处理模式](../local/feedback_error_handling.md) — try/catch 配合结构化日志；不允许静默吞咽错误

## Workflows

- [依赖升级](../workflows/dep-upgrade/workflow.md) — 先审计；先升补丁；跑测试；再升次版本
- [PR 审查清单](../workflows/pr-review/workflow.md) — 不可变 + 类型 + 错误处理 + 覆盖率

## Knowledge Base

- [平台架构](../kb/platform-arch/README.md) — 五层架构图；接入到 API；2026-03 更新
- [部署手册](../kb/deployment-runbook/README.md) — 蓝绿部署步骤；回滚流程

## Recently modified

- 2026-04-18 [API 响应格式](../local/feedback_api_response.md)
- 2026-04-14 [ESLint 基准](../local/feedback_eslint.md)
```

**运行时导航（L1 → L2 → L3）：**

当 LLM 开始处理涉及 TypeScript 配置的任务时，相关性闸门对 MEMORY.md 中的条目打分，选中"平台规范"主题指针，加载 `index/platform.md`（L2）。该文件列出了与 TypeScript 相关的资产及其一行摘要。相关性闸门对这些摘要再次打分，仅加载得分最高的资产——例如 `feedback_ts_config.md` 和 `feedback_error_handling.md`——而其余 29 个平台资产保持未加载状态。这就是实践中的 L1 → L2 → L3 路径。

对于涉及推送行为的任务，LLM 无需导航到任何主题：`feedback_push_confirm.md` 已直接固定在 `## Always-on rules` 分节（L1 → L3 一跳到达）。

---

### §7.7 性能预算与校验

**性能目标：**

- 启动解析（读取并解析 MEMORY.md）必须在 100ms 内完成。此要求与术语表 §20 中的"启动上下文注入"预算一致。
- MEMORY.md 内容的 L1 token 数**建议**不超过 900（软性指导；不机器强制执行）。这可确保 128k token 上下文窗口的 95% 以上可用于实际工作。
- 主题子索引文件（`index/<topic>.md`）无 token 上限，按需加载而非在启动时加载。

**校验规则：**

- `engram validate` 对 MEMORY.md 中相对路径无法解析到实际文件的条目报告 `E-IDX-001`。
- `engram validate` 对主题子索引中相对路径无法解析到实际文件的条目报告 `E-IDX-002`。
- `engram validate` 对 MEMORY.md 中主题标题引用了不存在的 `index/<topic>.md` 文件的情况报告 `E-IDX-003`。
- 如果 MEMORY.md 的行数达到或超过其滚动历史的第 95 百分位，`engram review` 发出长度警告（百分位长度信号，术语表 §16）。这是建议性的，不是校验错误。
- MEMORY.md 中主题标题的 `N entries` 计数由 `engram validate` 与对应子索引的实际数量核对。不匹配报告为 `W-IDX-001` 警告（不是错误——计数在两次 rebuild 之间会过时）。

---

---

## 8. Scope 模型 — 两轴：归属层次 + 订阅

### §8.0 概述

engram 的 scope 模型建立在**两个正交轴**之上。理解这个两轴结构是理解冲突解决、enforcement 和 pool 订阅的前提。

**轴 1 — 归属层次（hierarchy，由 membership 决定，自动继承）：**
从普遍性最高到最具体，共 4 个位置：`org > team > user > project`。每个位置的归属由用户的现实关系决定——属于哪个组织、哪些团队、本人身份、正在处理哪个项目。上层位置通过归属关系自动继承，无需显式订阅。

**轴 2 — 订阅（topic pool，主动加入，正交）：**
`pool` 是第五个标签，不是归属层次中的某一级。pool 是一种按主题共享的资产存储库，任何订阅者都可以主动加入。订阅者通过 `subscribed_at` 声明 pool 内容在冲突解决时应被视为哪一个归属层级。同一个 pool 可以被不同的订阅者以不同层级订阅。

`scope:` frontmatter 字段使用的五个标签为：`org / team / user / project / pool`。

**与 v0.1 的对比：** v0.1 只有两个层级——`local`（项目）和 `shared`（基于 symlink 的 pool，无差别处理）。v0.2 将其扩展为 4 个归属层次加上正交 pool 订阅，使团队和组织级协作成为可能，同时不牺牲项目级的精细度。一条必须适用于公司所有工程师的规则，现在可以用 `scope: org` + `enforcement: mandatory` 表达，而无需借助额外的带外机制。

---

### §8.1 归属层次轴

**4 个位置 — 从普遍性最高到最具体：**

| 标签 | 文件系统路径 | 谁写入 | 典型内容 |
|---|---|---|---|
| `org` | `~/.engram/org/<org-name>/` | 组织 maintainer（CODEOWNERS） | 公司级合规、安全策略、强制规范 |
| `team` | `~/.engram/team/<team-name>/` | 团队 maintainer | 团队工作流、review 约定、技术标准 |
| `user` | `~/.engram/user/` | 用户本人 | 跨项目个人偏好、身份、工作风格 |
| `project` | `<project>/.memory/local/` | 项目 owner | 仅此项目——事实、覆盖、项目特定规则 |

**继承规则。** 每个项目自动看到以下内容的并集：
1. `~/.engram/org/<org-name>/` 中的所有资产（如果用户属于某个 org）
2. 用户所属的每个团队的 `~/.engram/team/<team-name>/` 中的所有资产
3. `~/.engram/user/` 中的所有资产
4. `<project>/.memory/local/` 中的所有资产

这种继承基于归属关系——用户不需要"订阅"自己的 org 或 team。归属关系只需声明一次（例如 `engram org join`、`engram team join`），随后自动对所有项目生效。

**冲突解决的特化度顺序（同 `enforcement` 级别内）：**
`project > user > team > org`（project 最具体，优先获胜；org 最不具体）。

**基数约束：**
- 用户属于 **0 或 1** 个 `org`。单一 org 归属由文件系统结构强制：`~/.engram/org/` 下只有一个活跃 org 子目录。（换工作的用户迁移其 org 目录。）
- 用户可以属于 **0 或 N** 个 `team`。多个团队目录共存于 `~/.engram/team/` 下。同 enforcement 级别的两个团队资产冲突时，按 §8.4 处理。
- `user` 作用域**始终存在**且隐式可用——`~/.engram/user/` 总是存在。
- 项目始终以自身为 project 作用域——`<project>/.memory/local/` 是项目的私有命名空间。

**关于 `local/` 目录名与 `project` scope 标签的区别。** 该文件夹命名为 `local/` 是为了简洁；该文件夹中资产的 `scope:` frontmatter 值是 `project`，而非 `local`。这是两个不同的标识符：一个是路径，一个是冲突解决标签。

---

### §8.2 订阅轴

**pool 与归属层次正交。** pool 不在任何两个归属层次位置之间。它是一个独立的概念：一种按名称标识的、按主题共享的资产存储库。

**存储位置。** pool 资产的权威存储位置为 `~/.engram/pools/<pool-name>/`。项目通过 `<project>/.memory/pools/<pool-name>/` 中的 symlink 访问 pool 资产（symlink 指向权威 pool 目录）。

**订阅声明。** 订阅者在 `.memory/pools.toml`（项目级订阅）或 `~/.engram/org/<name>/pools.toml` / `~/.engram/team/<name>/pools.toml` / `~/.engram/user/pools.toml`（更高层级的订阅）中声明其 pool 订阅：

```toml
[subscribe.design-system]
subscribed_at = "team"
propagation_mode = "notify"   # auto-sync / notify / pinned；见 §9
pinned_revision = null

[subscribe.my-dotfiles-notes]
subscribed_at = "user"
propagation_mode = "auto-sync"

[subscribe.acme-checkout-playbook]
subscribed_at = "project"
propagation_mode = "auto-sync"
```

**`subscribed_at` 取值及其含义：**

| 取值 | 含义 |
|---|---|
| `org` | pool 对 org 内所有项目表现为 org 级内容。由 org maintainer 代表所有成员订阅。 |
| `team` | pool 对该团队所有项目表现为 team 级内容。由 team maintainer 订阅。 |
| `user` | pool 对该用户所有项目表现为 user 级内容。由用户本人订阅。 |
| `project` | pool 仅对该项目表现为 project 级内容。由项目 owner 订阅。 |

**pool 资产的 frontmatter。** `~/.engram/pools/<name>/` 中每个资产文件均声明 `scope: pool` 和 `pool: <name>`。文件中的 `scope: pool` 标签是固定的。冲突解决时使用的**有效归属层级**从订阅方的 `pools.toml`（`subscribed_at`）中读取，而非从资产文件本身读取。这种分离是刻意设计的：同一个 pool 文件可以被某个订阅方以 `org` 级别订阅，也可以被另一个订阅方以 `user` 级别订阅，两者的冲突解决相互独立。

**基数。** 一个项目可以订阅任意数量的 pool，以任意组合的归属层级订阅。对 pool 订阅数量没有限制。

**订阅定位示例：**
- org 以 `subscribed_at: org` 订阅 `pool: compliance-checklists` → org 内每个项目都看到这些资产作为 org 级强制内容（如果它们带有 `enforcement: mandatory`）。
- team 以 `subscribed_at: team` 订阅 `pool: design-system` → 该团队每个项目都将 pool 视为 team 级内容。
- 用户本人以 `subscribed_at: user` 订阅 `pool: my-dotfiles-notes` → 只有该用户的项目能看到，以 user 级处理。
- 单个项目以 `subscribed_at: project` 订阅 `pool: acme-checkout-playbook` → 只有该项目能看到，以 project 级内容处理。

---

### §8.3 Enforcement 级别

**三个级别**，控制高层 scope 的规则是否可被低层 scope 覆盖。

| 级别 | 含义 | 覆盖行为 | 典型用途 |
|---|---|---|---|
| `mandatory` | 不可被低层 scope 覆盖 | `engram validate` 对任何冲突的低层资产报错 | 公司安全策略、合规要求、不可妥协的规范 |
| `default` | 可覆盖，但覆盖方必须声明 `overrides: <高层资产-id>` | 缺少 `overrides:` 声明时 `engram validate` 发出 warning | 团队约定、推荐实践、技术标准 |
| `hint` | 可自由覆盖 | 无需声明 | 个人偏好、宽松建议、起步参考 |

**Frontmatter。** `enforcement:` 在 `feedback` 子类型（§4.3）中为必填字段。对其他子类型为可选，默认值为 `hint`。

**覆盖声明格式。** 当一个低层资产覆盖一个 `default` enforcement 的高层资产时，低层资产必须声明 `overrides:` 字段：

```yaml
---
type: feedback
scope: project
enforcement: hint
overrides: team/feedback_tabs_over_spaces
---

本项目使用 2 空格缩进，而非团队默认要求的制表符（tab）。

**Why:** 本项目的历史代码库在团队标准确立之前已采用 2 空格规范。迁移所有文件将在 blame 历史中产生大量噪音。

**How to apply:** 本项目所有新文件及编辑均使用 2 空格缩进。
```

`overrides:` 的值为被覆盖资产的 ID（相对路径或规范 ID）。`engram validate` 检查：
1. 引用的资产存在。
2. 引用的资产具有 `enforcement: default`（不能是 `mandatory`——无论是否声明 `overrides:`，覆盖 mandatory 始终报错）。
3. 覆盖方的 scope 比被覆盖方更具体。

**不变量：任何 scope 层级的 `mandatory` enforcement 资产不能被任何低层 scope 覆盖。** 声明 `overrides:` 不能解锁此限制。修改强制规则的唯一方式是在拥有它的 scope 处直接修改。

---

### §8.4 冲突解决决策树

当多个资产涉及同一主题或规则时，相关性闸门和 `engram validate` 按以下算法依次执行：

**决策算法：**

1. **`enforcement` 级别绝对优先。** `mandatory` 胜过 `default`，`default` 胜过 `hint`。任何 scope 下带有 `enforcement: mandatory` 的资产，胜过任何 scope 下冲突的 `enforcement: default` 或 `hint` 资产——无论特化度如何。这是绝对优先级，不是平局裁决器。

2. **同 `enforcement` 级别内，归属特化度决定胜负。** `project > user > team > org`。更具体的 scope 获胜。

3. **pool 内容以其 `subscribed_at` 作为有效归属位置参与比较。** 以 `team` 级订阅的 pool，与原生 team 级资产在 team 特化度下竞争。以 `project` 级订阅的 pool，与原生 project 资产在 project 特化度下竞争——原生 project 资产仍然优先，因为原生资产优先于同级 pool 资产。

4. **同 enforcement 级别、同归属位置、不同来源 → 由 LLM 仲裁。** 两个资产均加载到上下文，LLM 根据当前任务选择最适用的。`engram review` 将此情况标记为 warning，建议人工干预并对其中一个设置 `overrides:` 以使解决结果确定性化。

5. **同 pool 内部冲突 → `engram validate` 报错。** Pool 资产内部不得相互矛盾。Pool maintainer 必须在 pool 发布前解决冲突。该约束在 pool 发布时执行。

**实例演示：**

**示例 1：org 级 mandatory vs. project 级 hint（mandatory 始终获胜）**
- `~/.engram/org/acme/feedback_no_push_to_main.md` — `scope: org`，`enforcement: mandatory`
- `<project>/.memory/local/feedback_bypass_main_protection.md` — `scope: project`，`enforcement: hint`
- 结果：`engram validate` 报错。project 资产与 org 级 mandatory 规则冲突。project 资产无法覆盖 mandatory 规则。项目工程师必须移除或修改该 project 资产。

**示例 2：team 级 default vs. project 级 hint 且声明了 overrides（合法覆盖）**
- `~/.engram/team/platform/feedback_tabs_over_spaces.md` — `scope: team`，`enforcement: default`
- `<project>/.memory/local/feedback_two_space_indent.md` — `scope: project`，`enforcement: hint`，`overrides: team/feedback_tabs_over_spaces`
- 结果：校验通过。project 覆盖声明合法有效。相关性闸门加载 project 资产。LLM 对此项目使用 2 空格规则。

**示例 3：pool（subscribed_at: team）vs. 原生 project 资产**
- Pool 资产 `~/.engram/pools/kernel-work/feedback_rebase_before_merge.md` — `scope: pool`；订阅方 `pools.toml` 声明 `subscribed_at: team`
- `<project>/.memory/local/feedback_merge_commit_preferred.md` — `scope: project`，`enforcement: hint`
- 结果：pool 资产以 team 特化度参与；project 资产以 project 特化度参与。project 获胜（比 team 更具体）。LLM 看到两个资产，使用 project 的 merge commit 偏好，并可提示 pool 的 rebase 偏好作为备选。

**示例 4：两个 pool 在同一归属层级冲突（LLM 仲裁）**
- `~/.engram/pools/pool-A/feedback_prefer_tabs.md` — 用户以 `subscribed_at: user` 订阅
- `~/.engram/pools/pool-B/feedback_prefer_spaces.md` — 同一用户也以 `subscribed_at: user` 订阅，与 pool-A 的规则冲突
- 结果：两者均在 user 特化度，假设均为 `enforcement: hint`（或均为 `default`）。LLM 带两个资产仲裁；`engram review` 标记 warning。推荐解决方式：对其中一个设置 `overrides:`，或退订冲突 pool。

**不变量。** 给定相同的资产集和相同的 `pools.toml`，决策算法始终产生相同结果。解决过程中不引入随机性或会话状态。相同输入 → 相同输出。

---

### §8.5 Org、Team 和 Pool 的 Git 同步

**`~/.engram/org/<org-name>/` 和 `~/.engram/team/<team-name>/` 是 git 仓库。**

每个目录均从上游远端（由 org 或 team 维护的 GitHub / GitLab / Gitea 仓库）克隆而来。这使 org 和 team 的记忆具备以下特性：
- **版本化：** 每次变更都是带有消息、作者和时间戳的 commit。
- **可审计：** `git log` 显示谁在何时修改了哪条规则。
- **CODEOWNERS 强制：** mandatory 资产在合并前需要指定 owner 的审批。
- **离线可用：** 初始 clone 后，所有数据驻留在本地磁盘；日常使用无需网络。

**团队级记忆的典型工作流：**

```bash
# 加入一个团队（将团队记忆仓库克隆到本地）
engram team join git@github.com:acme/platform-team-engram.git

# 从上游拉取所有团队的更新
engram team sync

# 拉取指定团队的更新
engram team sync platform-team

# 将本地修改发布到上游（需要写入权限）
engram team publish

# 查看所有团队归属及待同步状态
engram team status
```

org 存在相同的子命令：`engram org join`、`engram org sync`、`engram org publish`、`engram org status`。由于用户最多属于一个 org，`engram org status` 显示 0 或 1 条记录。

**Pool 同步使用相同机制：**

```bash
# 订阅一个 pool（克隆 pool 仓库，在 pools.toml 中注册）
engram pool subscribe github:acme/design-system-pool

# 拉取所有已订阅 pool 的更新
engram pool sync

# 拉取指定 pool 的更新
engram pool sync design-system

# 将本地 pool 贡献发布到上游
engram pool publish design-system

# 查看所有 pool 订阅及同步状态
engram pool status
```

`engram pool subscribe` 将 pool 仓库克隆到 `~/.engram/pools/<pool-name>/`，并根据订阅方（项目、用户、team 或 org）将订阅条目写入对应的 `pools.toml`。

**mandatory 资产的 CODEOWNERS 强制执行：**

对于 `org/` 和 `team/` 仓库，git 平台的 CODEOWNERS 机制控制哪些人可以提交带有 `enforcement: mandatory` 的资产。尝试在未经指定 maintainer 审批的情况下合并新的 mandatory 资产，会被平台的分支保护机制拒绝。`enforcement: default` 或 `hint` 资产的变更可以由任意团队成员通过 pull request 提交，由 maintainer 审查并合并。

**离线操作。** 完成初始 `join` 或 `subscribe` 后，所有 org、team 和 pool 数据均驻留在本地磁盘。相关性闸门和 `engram validate` 完全支持离线运行。仅 `sync` 和 `publish` 操作需要网络访问。

---

### §8.6 典型内容分布

下表提供各 scope 通常存放何种内容及典型 enforcement 级别的直觉参考。

| 内容类型 | 典型 scope | 典型 enforcement |
|---|---|---|
| "禁止在代码中硬编码凭证"——公司安全策略 | `org` | `mandatory` |
| 公司统一编码规范 | `org` | `default` |
| "main 分支合并需双人审批"——团队 review 规则 | `team` | `mandatory` |
| 团队特定技术栈选型 | `team` | `default` |
| 来自专家团队的共享工作流（以 pool 方式分发） | `pool`（由 team 以 `team` 级订阅） | `default` |
| 个人终端和编辑器偏好 | `user` | `hint` |
| 个人身份与工作风格描述 | `user` | —（不是规则；`user` 子类型） |
| 主题知识库（例如 engram 设计文档，仅供参考） | `pool`（由用户或项目订阅） | —（参考，不是规则） |
| 此项目的 merge 策略 | `project` | `hint` 或 `default` |
| 此项目对 team default 的显式覆盖 | 带 `overrides:` 的 `project` | 任意级别（须 ≤ 被覆盖资产的级别） |

**最小可用 scope。** 单独工作的新用户只需 `user` 和 `project`，无需 org、team 或 pool 订阅。两轴模型会优雅降级：没有 org、没有 team、没有 pool 时，解决逻辑简化为 `project > user`。

**最大 scope。** 在大型组织中，五个标签可以同时使用。两轴模型无需特殊处理：相同的决策树（§8.4）适用于任意层级组合。

---

### §8.7 Frontmatter 契约汇总

下表按 scope 值汇总必填 frontmatter 字段。这是 §4.1 字段定义的汇总视图，以 scope 为维度组织。

| Scope 值 | 必填 frontmatter（除公共必填字段外） | `pools.toml` 中必填 |
|---|---|---|
| `org` | `org: <org-name>` | — |
| `team` | `team: <team-name>` | — |
| `user` | —（无 scope 条件额外字段） | — |
| `project` | —（无 scope 条件额外字段） | — |
| `pool`（pool 资产文件本身） | `pool: <pool-name>` | — |
| —（消费方订阅 pool 时） | — | `subscribed_at: org \| team \| user \| project` |

**公共必填字段**（所有资产，所有 scope）：`name`、`description`、`type`、`scope`、`enforcement`（`feedback` 子类型必填；其他子类型可选，默认为 `hint`）。

**`engram validate` 强制的关键不变量：**
- `scope: pool` 的资产必须有 `pool:` 字段，且与已知 pool 目录匹配。
- `scope: org` 的资产必须有 `org:` 字段，且与唯一活跃 org 目录匹配。
- `scope: team` 的资产必须有 `team:` 字段，且与 `~/.engram/team/` 下某个团队目录匹配。
- 声明了 `overrides:` 的资产必须引用一个 `enforcement: default` 的资产（不能是 `mandatory`）。
- 带有 `enforcement: mandatory` 的资产必须位于 `org`、`team` 或 `pool` scope（project 级 mandatory 在技术上允许，但会被标记为 `W-SCO-001` 警告，因为其下没有可强制执行的更低层 scope）。

---

---

## 9. Pool 传播机制

### §9.0 概述

当 pool 维护者更新共享 pool——添加新记忆、修改已有资产或废弃某项内容——时，订阅方项目需要获知这些变更并将其整合进来。Pool 传播机制正是管理这一流程的规范：谁会收到通知、更新如何到达、订阅方需要做出哪些决策。

engram v0.2 定义了三种传播模式，在 `pools.toml` 中按订阅条目声明：

- **`auto-sync`（自动同步）** — 订阅方的 symlink 始终指向 pool 的 `current` 版本。pool 维护者发布新版本后，订阅方在下一个会话启动时自动看到更新内容，无需审批步骤。这是新订阅的默认模式。

- **`notify`（通知式）** — 订阅方的 symlink 仍然跟随 pool 的 `current` 版本，但每当有新版本时，系统会向 `~/.engram/journal/propagation.jsonl` 追加一条事件。订阅方（人类或 LLM）通过 `engram review` 查看待处理通知，并显式决策：accept（接受）、reject（拒绝）或 override-locally（本地覆盖）。变更在当前会话中立即可见，但通知必须被处理。

- **`pinned`（钉版）** — 订阅方的 symlink 固定指向某个特定版本目录（`rev/rN/`），而非 pool 的 `current`。pool 更新不会自动传播，直到订阅方显式运行 `engram pool update <name> --to=rM`。适用于需要长期稳定性的场景，如发布分支或合规快照。

§9.1 定义版本目录结构。§9.2 给出完整的 `pools.toml` 模式。§9.3 规定每种模式的精确语义。§9.4 记录 `propagation.jsonl` 事件格式。§9.5 处理新版本与下游覆盖冲突时的冲突解决。§9.6 涵盖引用图完整性检查。§9.7 提供完整的端到端示例。

---

### §9.1 Pool 版本模型

`~/.engram/pools/<pool-name>/` 下的每个 pool 在 `rev/` 子目录中维护不可变的版本历史：

```
~/.engram/pools/<pool-name>/
├── MEMORY.md
├── rev/
│   ├── r1/
│   │   ├── feedback_rule_a.md
│   │   └── workflow_onboarding.md
│   ├── r2/
│   │   ├── feedback_rule_a.md   # 内容已更新
│   │   ├── feedback_rule_b.md   # r2 中新增
│   │   └── workflow_onboarding.md
│   └── current -> r2/           # 指向当前活跃版本的 symlink
├── local/
│   ├── user_*.md
│   ├── feedback_*.md
│   └── ...
├── workflows/<name>/
├── kb/<topic>/
└── .engram-pool.toml            # pool 元数据
```

`current` 是 `rev/` 目录内的相对 symlink，始终指向最新发布的版本目录。订阅方在 `<project>/.memory/pools/<pool-name>` 处的 symlink 逐级解析到这里。

**发布新版本。** pool 维护者运行：

```bash
engram pool publish <pool-name>
```

该工具原子性地执行以下步骤：

1. 创建 `rev/r(N+1)/`，内含 pool 工作资产的完整快照。
2. 将 `current` symlink 更新为指向 `r(N+1)/`。
3. 向 `~/.engram/journal/propagation.jsonl` 追加 `revision_published` 事件。
4. 若 `.engram-pool.toml` 中配置了 git 远端，则提交并推送至 pool 的 git 远端。

**不可变性不变量。** 版本目录一旦创建，其内容永不修改。修正和新增内容进入后续版本。这保证了锁定到特定版本的订阅方在不同机器上始终看到相同内容。

**`last_synced_rev`。** `pools.toml` 中每个订阅条目都有 `last_synced_rev` 字段。工具在每次成功同步操作后更新此字段。该字段仅供参考——用于 `engram pool status` 展示订阅方落后多远——从不用于冲突解决。

---

### §9.2 `pools.toml` 模式

订阅配置根据订阅方的不同存放在四个位置之一：

```
<project>/.memory/pools.toml      # 项目级订阅
~/.engram/user/pools.toml          # 用户级订阅
~/.engram/team/<name>/pools.toml   # 团队级订阅
~/.engram/org/<name>/pools.toml    # 组织级订阅
```

包含所有字段的完整模式：

```toml
# 示例：<project>/.memory/pools.toml

[subscribe.design-system]
subscribed_at = "team"          # org | team | user | project
propagation_mode = "notify"     # auto-sync | notify | pinned
pinned_revision = null          # propagation_mode = "pinned" 时必填；否则为 null
last_synced_rev = "r7"          # 工具维护；记录消费方已见过的最新版本

[subscribe.kernel-work]
subscribed_at = "user"
propagation_mode = "auto-sync"
pinned_revision = null
last_synced_rev = "r12"

[subscribe.acme-checkout-playbook]
subscribed_at = "project"
propagation_mode = "pinned"
pinned_revision = "r3"          # symlink 指向 rev/r3/ 而非 rev/current
last_synced_rev = "r3"
```

**字段语义：**

| 字段 | 类型 | 是否必填 | 含义 |
|---|---|---|---|
| `subscribed_at` | string | 是 | 冲突解决中的有效层级（§8.2）。取值为 `org`、`team`、`user`、`project` 之一。 |
| `propagation_mode` | string | 是 | `auto-sync`、`notify`、`pinned` 之一。新订阅的默认值：`auto-sync`。 |
| `pinned_revision` | string 或 null | 条件必填 | `propagation_mode = "pinned"` 时必填，须为 pool `rev/` 目录中存在的版本标识符（如 `"r3"`）。模式为 `auto-sync` 或 `notify` 时必须为 null。 |
| `last_synced_rev` | string | 否 | 仅供参考。工具在每次同步后写入，请勿手动编辑。 |

**校验。** `engram validate` 会在以下情况报错：
- `propagation_mode = "pinned"` 且 `pinned_revision = null`
- `propagation_mode != "pinned"` 且 `pinned_revision` 非 null
- `pinned_revision` 引用的版本目录在 pool 中不存在

---

### §9.3 模式语义

#### 模式一：`auto-sync`（新订阅的默认模式）

订阅方在 `<project>/.memory/pools/<pool-name>`（或用户/团队/组织订阅的对应路径）处的 symlink 始终通过 pool 的 `rev/current` symlink 解析到最新发布版本。

当 pool 维护者运行 `engram pool publish <pool-name>` 时：

1. pool 的 `rev/current` symlink 更新为 `r(N+1)/`。
2. 由于订阅方的 symlink 末端指向 `rev/current`，在下一次文件系统解析时——即每次会话启动时 Relevance Gate 加载上下文时——自动解析到 `r(N+1)/`。
3. 无需审批步骤。订阅方被动接收新内容。

**适用场景：** 低风险的共享资源——参考记忆库、稳定的工作流模板、广泛适用的知识库。对于不良更新下游风险较低、希望快速传播的资产。

**失效模式——mandatory 冲突。** 若新版本引入的资产带有 `enforcement: mandatory` 且与订阅方现有覆盖冲突，则订阅方项目下次运行 `engram validate` 时报错（错误码：`E-ENF-001`）。订阅方须：(a) 移除冲突的本地覆盖，(b) 请求 pool 维护者将 enforcement 降为 `default`，或 (c) 切换到 `pinned` 并锁定到更新前的版本：

```bash
engram pool subscribe-mode --pool=<name> --mode=pinned --at=r<N>
```

#### 模式二：`notify`（规则类 pool 推荐使用）

订阅方的 symlink 仍跟随 pool 的 `rev/current` symlink，因此 pool 维护者发布后，当前会话中立即可见更新内容。但同时，对于每个订阅方尚未确认的新版本，系统会向 `~/.engram/journal/propagation.jsonl` 追加 `subscriber_notified` 事件。

`engram review` 展示待处理的传播通知。对于每条通知，订阅方做出以下决策之一：

- **accept（接受）** — 取消通知。无结构性变更；订阅方已经在看到新内容。记录 `decision: accept` 的 `subscriber_decision` 事件。
- **reject（拒绝）** — 取消通知，并将订阅切换到 `pinned`，锁定到更新前的版本。订阅方的 symlink 被重新指向更新前的版本目录，后续 pool 更新停止流入，直到订阅方显式推进。记录 `decision: reject` 及新钉版版本的 `subscriber_decision` 事件。
- **override-locally（本地覆盖）** — 将特定冲突资产复制到订阅方的本地 scope，并在 frontmatter 中以 `overrides: pool/<asset-id>` 编辑。订阅方对其他资产继续跟踪 `current`。记录 `decision: override-locally` 及复制资产列表的 `subscriber_decision` 事件。

**通知批处理。** 每次版本升级追加一条 `subscriber_notified` 事件（而非每个变更资产各一条）。事件包含差异摘要（`added`、`modified`、`removed` 计数）。

**notify 模式下的 mandatory 冲突。** 若新版本引入的 `enforcement: mandatory` 资产与订阅方覆盖冲突，`propagation.jsonl` 中对应通知的 `"mandatory_conflict"` 字段为 `true`。`engram review` 以 `[需要操作]` 标语展示该通知。工具要求订阅方选择 reject 或 override-locally（对于 mandatory 规则，本地副本不得与规则相悖——必须是补充或扩展，而非矛盾）。不允许静默 accept 。

**适用场景：** 规则类 pool、反馈类 pool、工作流类 pool——下游订阅方可能希望在完全接受变更前进行审查的场景。不良更新会实质性干扰活跃工作的任何 pool。

#### 模式三：`pinned`（钉版）

订阅方在 `<project>/.memory/pools/<pool-name>` 处的 symlink 直接指向特定版本目录——`rev/r<N>/`——而非 `rev/current`。pool 更新不会传播到该订阅方，除非其显式请求推进。

**推进钉版订阅：**

```bash
# 查看可用版本及变更内容
engram pool diff <pool-name> --from=r3 --to=current

# 推进到指定版本
engram pool update <pool-name> --to=r5

# 推进到最新可用版本
engram pool update <pool-name> --to=current
```

`engram pool update` 执行后，`pools.toml` 中的 `pinned_revision` 字段更新为新目标，`last_synced_rev` 同步写入。

**适用场景：** 长期稳定性要求——发布分支不希望共享规则在发布期间变动、合规快照须经审计方可更新、或任何需要对每项变更保持显式控制的场景。

**主动使用 `engram pool diff`** 监控钉版期间 pool 中积累的变更：

```bash
engram pool diff design-system --from=r3 --to=current
# → 展示 r4、r5、r6、... current 中新增、修改、删除的资产
```

---

### §9.4 `propagation.jsonl` 格式

`~/.engram/journal/propagation.jsonl` 是只追加的 JSON Lines 文件。每行是一个独立的 JSON 对象，行内容永不原地修改。

**文件位置：** `~/.engram/journal/propagation.jsonl`

**事件类型**及其模式：

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"revision_published","pool":"design-system","from_rev":"r7","to_rev":"r8","changes":{"added":2,"modified":1,"removed":0},"publisher":"alice@acme.com"}
{"timestamp":"2026-04-18T10:31:15Z","event":"subscriber_notified","pool":"design-system","subscriber":"/home/alice/projects/billing-service","subscriber_scope":"team","pending_since":"r7","mandatory_conflict":false}
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"accept","reviewer":"alice@acme.com","rev":"r8"}
{"timestamp":"2026-04-18T12:00:00Z","event":"propagation_completed","pool":"design-system","subscriber":"/home/alice/projects/billing-service","from_rev":"r7","to_rev":"r8"}
{"timestamp":"2026-04-18T12:05:00Z","event":"override_declared","pool":"design-system","subscriber":"/home/alice/projects/billing-service","asset_id":"pool/feedback_accessibility_review","local_copy":"local/feedback_accessibility_review_local.md"}
```

**事件类型参考：**

| 事件 | 追加时机 | 关键字段 |
|---|---|---|
| `revision_published` | 维护者运行 `engram pool publish` | `pool`、`from_rev`、`to_rev`、`changes`、`publisher` |
| `subscriber_notified` | `notify` 模式订阅方在同步时检测到新版本 | `pool`、`subscriber`、`subscriber_scope`、`pending_since`、`mandatory_conflict` |
| `subscriber_decision` | 订阅方通过 `engram review` 操作 | `pool`、`subscriber`、`decision`（`accept`/`reject`/`override-locally`）、`reviewer`、`rev` |
| `propagation_completed` | 订阅 symlink 成功更新（任意模式） | `pool`、`subscriber`、`from_rev`、`to_rev` |
| `override_declared` | 订阅方通过 override-locally 决策将 pool 资产复制到本地 | `pool`、`subscriber`、`asset_id`、`local_copy` |

**保留策略。** 默认保留期为 2 年。超期条目由 `engram journal compact` 移入 `~/.engram/journal/archive/propagation-<year>.jsonl`。活跃文件从不原地截断；压缩操作始终是"追加到归档文件 + 截断源文件"，而非"原地修改"。

**只追加不变量。** 工具只能向 `propagation.jsonl` 追加内容。任何行都不得被删除或修改。这使该文件可通过 `git log` 轻松审计，也可安全地发送到中央日志系统而无需额外协调。

---

### §9.5 传播时的冲突解决

当新版本引入变更时，可能与下游本地内容产生冲突。§8.4 决策树适用于所有情形。以下场景描述了每种传播模式如何处理最常见的冲突模式。

**场景 A：pool 新增 `mandatory` 规则与订阅方现有覆盖冲突**

pool 维护者向 pool 中添加了一个 `enforcement: mandatory` 的 `feedback` 资产，而订阅方此前已在本地进行了覆盖。

- **`auto-sync` 模式：** 订阅方项目下次运行 `engram validate` 时报错，错误码 `E-ENF-001`。订阅方须：(a) 移除冲突的本地覆盖，(b) 请求 pool 维护者将 enforcement 降为 `default`，或 (c) 运行 `engram pool subscribe-mode --pool=<name> --mode=pinned --at=<更新前版本>` 冻结到最后已知良好版本。
- **`notify` 模式：** `subscriber_notified` 事件中 `"mandatory_conflict": true`。`engram review` 以 `[需要操作]` 标语展示通知。订阅方必须选择 reject 或 override-locally（对于 mandatory 规则，本地副本不得与规则相悖）。工具阻止静默 accept。
- **`pinned` 模式：** 直到订阅方显式推进钉版版本时，才会触发影响。当推进超过引入 mandatory 规则的版本时，冲突检查此时运行。

**场景 B：pool 修改了订阅方已用 `overrides:` 覆盖的 `default` 规则**

pool 的 `feedback_tabs_over_spaces.md`（enforcement: `default`）修改了正文内容，但订阅方的本地 `feedback_two_space_indent.md` 仍声明 `overrides: pool/feedback_tabs_over_spaces`。

- **所有模式：** 订阅方的覆盖在结构上仍然有效——`overrides:` 引用的是规则 ID，而非规则的具体文本内容。覆盖继续生效。
- **`notify` 和 `auto-sync` 模式：** `engram review` 显示提示信息："pool 规则 `feedback_tabs_over_spaces` 已在 r8 中更新；您的覆盖可能已过时。请检查本地覆盖是否仍符合您的意图。" 这是警告，不是错误。
- **`pinned` 模式：** 仅当订阅方推进超过修改该规则的版本时，警告才会出现。

**场景 C：pool 删除了订阅方资产 `references:` 所引用的规则**

某 pool 资产被新版本删除，而另一个订阅方资产通过 frontmatter 的 `references:` 字段指向它。

- **所有模式：** `engram validate` 对持有悬空 `references:` 字段的资产发出 `W-REF-001 reference_rot` 警告。订阅方资产不会被自动删除或修改。下游所有者须决定：将 `references:` 字段更新为指向替代资产、将资产标记为 deprecated，或在依赖不再适用时删除该 `references:` 字段。
- **`auto-sync` 和 `notify` 模式：** pool 更新解析后，下次 `engram validate` 运行时警告出现。
- **`pinned` 模式：** 仅当订阅方推进超过删除被引用资产的版本时，警告才会出现。

**场景 D：两个 pool 独立修改同一主题，且都订阅在同一层级**

两个 pool 都包含针对同一编码实践（如缩进）的 `feedback` 资产，且都以 `team` 层级订阅。

- **所有模式：** `engram review` 标记为警告："pool-A 的 `feedback_prefer_tabs` 与 pool-B 的 `feedback_prefer_spaces` 在 team scope 下存在潜在冲突。两个资产都将被加载；LLM 进行仲裁。" 这是 §8.4 规则 4 的实际应用。
- 推荐解决方案：在两个资产之一上设置 `overrides:`，或针对该主题取消订阅优先级较低的 pool。

---

### §9.6 引用图完整性

engram v0.2 在 `~/.engram/graph.db`（SQLite）中维护跨所有资产的引用图。引用图追踪 org、team、user、project 和 pool 资产中所有 frontmatter `references:` 字段。

**当某个 pool 资产在新版本中被删除或取代时**，引用图检查作为 `engram pool publish`（维护者侧）和 `engram pool sync`（订阅方侧）的一部分运行：

1. 查询 `graph.db`，找出所有具有 `references:` 条目且指向被删除或取代资产的下游资产（org、team、user、project 及其他 pool）。
2. 对每个此类下游资产，向 `engram review` 队列添加 `W-REF-001 reference_rot` 警告。
3. 不得自动删除或修改任何下游资产。引用图检查相对于资产是只读操作。
4. 下游资产所有者决定：将 `references:` 字段更新为指向替代资产、使用 frontmatter 中的 `deprecated: true` 标记资产为废弃，或在依赖不再适用时删除 `references:` 字段。

**为何只读。** 基于上游变更自动修改订阅方资产违反了"每个 scope 拥有自己资产"的原则。pool 更新不能深入订阅方的 `local/` 目录并修改文件，只有订阅方才能修改自己的资产。

**引用图更新频率。** `graph.db` 在每次 `engram validate` 运行、每次 `engram pool sync` 以及每次通过 `engram edit` 写入资产时更新。删除后可安全重建：`engram index rebuild --graph` 从当前资产集完整重新计算引用图。

**防止静默覆盖的核心机制。** 引用图完整性检查是防止 pool 更新静默使下游工作失效的核心机制。若没有此机制，pool 维护者重命名或删除某个资产，数十个下游资产所依赖的引用就会静默悬空，导致 LLM 行为不一致。

---

### §9.7 完整传播示例

本节通过一个使用通用组织名称的完整端到端传播场景进行说明。

**初始状态：**
- 组织 `acme`，共享 pool `design-system` 当前处于版本 `r7`
- 团队 `platform` 以 `subscribed_at: team`、`propagation_mode: notify` 订阅了 `design-system`
- 项目 `acme-billing-service` 属于团队 `platform`，通过 `~/.engram/team/platform/pools.toml` 继承 pool 订阅

**事件：** `design-system` 维护者（`alice@acme.com`）发布 `r8`，新增一个 `feedback` 资产：`feedback_accessibility_review_in_pr.md`，`enforcement: default`——"所有面向 UI 的 PR 必须在审查清单中包含无障碍审查项。"

**传播序列：**

**步骤 1 — 发布：**
```bash
# 维护者机器上
engram pool publish design-system
# → 创建 rev/r8/，包含完整快照
# → 更新 rev/current → r8/
# → 提交并推送至 git 远端
```
追加的 journal 条目：
```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"revision_published","pool":"design-system","from_rev":"r7","to_rev":"r8","changes":{"added":1,"modified":0,"removed":0},"publisher":"alice@acme.com"}
```

**步骤 2 — 订阅方检测到新版本：**
```bash
# 订阅方机器（或 CI），定期运行或在会话启动时运行
engram pool sync design-system
# → 检测到 pool 远端处于 r8；本地 last_synced_rev = r7
# → 由于模式为 notify，追加 subscriber_notified 事件
# → 不阻止 symlink 更新；current 已指向 r8/
```
追加的 journal 条目：
```jsonl
{"timestamp":"2026-04-18T10:31:15Z","event":"subscriber_notified","pool":"design-system","subscriber":"/home/alice/projects/billing-service","subscriber_scope":"team","pending_since":"r7","mandatory_conflict":false}
```

**步骤 3 — 会话启动时通知浮现：**

`acme-billing-service` 下一次 `engram` 会话启动时，会话横幅显示：
```
[notify] design-system 已从 r7 更新到 r8（新增 1 个资产）。运行 `engram review` 关闭通知。
```

**步骤 4 — 订阅方审查：**
```bash
engram review
# → 显示：design-system r8 通知
# →   新增：feedback_accessibility_review_in_pr.md（enforcement: default）
# →   无 mandatory 冲突。
# → 选项：[a]接受  [r]拒绝  [o]本地覆盖
```

**步骤 5a — 决策：accept（接受）：**
```bash
# 订阅方接受更新
engram review --pool=design-system --rev=r8 --decision=accept
```
追加的 journal 条目：
```jsonl
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"accept","reviewer":"alice@acme.com","rev":"r8"}
{"timestamp":"2026-04-18T11:45:01Z","event":"propagation_completed","pool":"design-system","subscriber":"/home/alice/projects/billing-service","from_rev":"r7","to_rev":"r8"}
```
`pools.toml` 中的 `last_synced_rev` 更新为 `r8`。新的无障碍规则在所有后续会话中生效。

**步骤 5b — 反例：decision: reject（拒绝，切换为 pinned）：**

假设 `acme-billing-service` 团队决定在下一次季度审查之前不希望任何 pool 更新自动流入，选择拒绝并钉版：

```bash
engram review --pool=design-system --rev=r8 --decision=reject
# → 内部运行：engram pool subscribe-mode --pool=design-system --mode=pinned --at=r7
# → 将 symlink 从 rev/current 重新指向 rev/r7/
# → 更新 pools.toml：propagation_mode = "pinned"，pinned_revision = "r7"
```
追加的 journal 条目：
```jsonl
{"timestamp":"2026-04-18T11:45:00Z","event":"subscriber_decision","pool":"design-system","subscriber":"/home/alice/projects/billing-service","decision":"reject","reviewer":"alice@acme.com","rev":"r8","new_mode":"pinned","pinned_at":"r7"}
```
项目保持在 `r7`。r8 的无障碍规则不生效。后续 `engram pool sync` 运行会记录版本差异但不更新 symlink。如需日后推进：
```bash
engram pool diff design-system --from=r7 --to=current
engram pool update design-system --to=r9
```

---

## 10. 跨仓收件箱消息协议

### §10.0 概述

当多个 LLM agent 并发地工作在相互关联的仓库上时——例如，`acme/service-a` 消费 `acme/service-b` 发布的客户端 SDK——在仓库 A 中工作的 agent 可能发现仓库 B 的 bug、设计缺陷或破坏性变更。此时，需要一种结构化的点对点方式让该 agent 向 B 的维护者和 agent 发送信号，并由 B 的 agent 反向汇报解决情况。

这一机制就是**跨仓收件箱（Cross-Repo Inbox）**：位于 `~/.engram/inbox/<repo-id>/` 的目录，保存发送给某仓库的结构化消息。收件箱消息的特征：

- **点对点。** 消息从某个特定发送方仓库发往某个特定接收方仓库。
- **短暂性。** 消息有生命周期（`pending → acknowledged → resolved` 或 `rejected`），最终归档而非永久留存。
- **默认由 LLM 撰写。** 发送方通常是在日常工作中发现问题的 LLM agent。人工也可以通过 CLI 发送消息。

**与 pool 传播（§9）的关键区别：**

| | Pool 传播 | 跨仓收件箱 |
|---|---|---|
| 方向 | 广播（1 个发布者 → N 个订阅者） | 点对点（A → B） |
| 内容 | 持久资产（记忆、工作流） | 临时消息（bug 报告、问题、更新通知） |
| 典型作者 | 人工 / 池维护者 | LLM agent（工作中发现） |
| 生命周期 | 永久存在（通过 supersede/archive 管理） | `pending → acknowledged → resolved → archived` |
| 存储路径 | `~/.engram/pools/<name>/` | `~/.engram/inbox/<repo-id>/` |

会话启动时，接收方 LLM 会与自身记忆上下文一同加载所有 `pending` 状态的收件箱消息："您有 2 条待处理的跨仓消息。" 这是 SPEC 格式中唯一一处一个仓库的数据进入另一个仓库上下文加载路径的地方——scope 模型中其他一切要么是本地的，要么通过 pool 订阅显式引入。

§10.1 规定目录布局。§10.2 定义消息格式。§10.3 说明 intent 语义。§10.4 规定生命周期状态机。§10.5 介绍去重与流量限制。§10.6 定义仓库标识符解析。§10.7 记录 `inter_repo.jsonl` 日志格式。§10.8 提供完整的端到端示例。§10.9 涉及隐私与安全。

---

### §10.1 目录布局

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

~/.engram/journal/inter_repo.jsonl            # 跨仓事件日志（全局）
```

`<repo-id>` 是按 §10.6 解析的稳定标识符。每个收件箱下的四个子目录对应生命周期中的四种状态（§10.4）。消息不在原位删除，而是随状态迁移在子目录之间移动。

**文件命名规则：**

```
<时间戳>-from-<发送方-id-slug>-<简短主题>.md
```

其中 `<时间戳>` 为 UTC 格式的 `YYYYMMDD-HHmmss`，`<发送方-id-slug>` 是将 `/` 替换为 `-` 后的发送方 repo-id，`<简短主题>` 是从消息 intent 和正文首行提炼的 1–4 个词的 slug。例如：`20260418-103000-from-acme-service-a-bug-users-404.md`。

**归档路径。** 已解决消息超过 180 天、已拒绝消息超过 30 天后，将自动移动到 `~/.engram/archive/inbox/<repo-id>/<state>/`。归档路径与收件箱路径镜像，并遵守同样的禁止自动删除不变量（§3.2）。

---

### §10.2 消息格式

每条收件箱消息是一个包含 YAML frontmatter 和结构化正文的单独 `.md` 文件。

**必填 frontmatter 字段：**

| 字段 | 类型 | 语义 |
|---|---|---|
| `from` | string | 发送方 repo-id（按 §10.6 解析） |
| `to` | string | 接收方 repo-id（按 §10.6 解析） |
| `intent` | enum | `bug-report` / `api-change` / `question` / `update-notify` / `task`——见 §10.3 |
| `status` | enum | `pending` / `acknowledged` / `resolved` / `rejected`——必须与文件所在子目录一致 |
| `created` | ISO 8601 | 发送方撰写消息的时间（UTC） |
| `message_id` | string | 全局唯一 ID，格式：`<发送方-repo-id>:<YYYYMMDD-HHmmss>:<4位随机数>`。用于去重和回复线程。 |

**可选 frontmatter 字段：**

| 字段 | 类型 | 语义 |
|---|---|---|
| `severity` | enum | `info` / `warning` / `critical`——默认 `info`。影响 `engram review` 中的排序。 |
| `deadline` | ISO 8601 | 发送方期望解决的截止时间。在 `engram review` 中显示倒计时。 |
| `related_memory_ids` | list[string] | 发送方记忆库中提供上下文的记忆 ID。在未来版本中接收方可通过网络可访问端点请求这些 ID（v0.2 不支持）。 |
| `related_code_refs` | list[string] | 代码位置，格式为 `path/to/file.py:L42@<git-blob-sha>`。git blob sha 锁定发送方观察到的精确版本。 |
| `dedup_key` | string | 覆盖自动去重哈希。具有相同 `dedup_key`、`to` 和 `intent` 的两条消息视为重复（§10.5）。 |
| `reply_to` | string | 本条消息所回复的上一条消息的 `message_id`。创建可通过 `engram inbox list --thread=<id>` 查看的线程。 |
| `duplicate_count` | integer | 消息被合并为重复时由 engram 自动递增（§10.5）。发送方不设置此字段，由 CLI 管理。 |
| `acknowledged_at` | ISO 8601 | 由 `engram inbox acknowledge` 在迁移至 `acknowledged` 时设置。 |
| `resolved_at` | ISO 8601 | 由 `engram inbox resolve` 在迁移至 `resolved` 时设置。 |
| `resolution_note` | string | 由 `engram inbox resolve --note="..."` 添加的自由文本备注。 |
| `rejected_at` | ISO 8601 | 由 `engram inbox reject` 设置。 |
| `rejection_reason` | string | 由 `engram inbox reject --reason="..."` 添加的拒绝原因。 |

**正文结构：**

```markdown
<一行摘要——LLM 可见的标题>

**What:** <具体观察、请求或报告>

**Why:** <为何对接收方重要——对接收方的影响>

**How to resolve (if actionable):** <具体建议或请求>
```

`bug-report`、`api-change` 和 `task` intent 均需包含上述四个正文部分。对于 `question` 和 `update-notify` intent，"How to resolve" 部分可以省略，因为不需要特定操作。

**完整示例消息文件：**

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

GET /api/users 对不存在的 ID 返回空数组而非 404

**What:** 调用 `GET /api/users?id=nonexistent-id` 时，接口返回
`200 OK` 且响应体为空数组 `[]`，而非 `404 Not Found`。
可在 `src/api/users.py:L42`（git blob `abc123def456`）处观察到此问题。

**Why:** `acme/service-a` 将空数组响应视为"无结果"并静默跳过后续处理。
当实际用户 ID 有效但临时不可用时，`service-a` 会在无任何错误日志的情况下丢失数据，
导致订单流水线出现静默数据丢失。

**How to resolve:** 当用户不存在时，请返回 `404 Not Found`，
响应体为 `{"error": "user not found", "id": "<queried-id>"}`。
空数组应仅用于零结果的集合端点，而非按 ID 查询的端点。
```

---

### §10.3 Intent 语义

五种 `intent` 值不仅仅是标签：它们承载了对接收方如何响应及在何种时间框架内响应的预期。

| Intent | 含义 | 接收方行为预期 |
|---|---|---|
| `bug-report` | 发送方在消费接收方代码或 API 时遇到了可复现的缺陷 | 调查；确认是 bug 还是预期行为；若为 bug，修复后 `resolve` 并附提交引用；若为预期行为，通过 `resolve` 说明或通过 `reject` 给出理由 |
| `api-change` | 发送方需要或建议对接收方公共接口做出变更 | 分级处理；接受则通过 `resolve` 回复计划或 PR 引用；拒绝则附设计理由 |
| `question` | 发送方需要只有接收方维护者或 agent 才了解的信息 | 通过 `reply_to` 回复消息作答；将原消息 `resolve` 并在 `resolution_note` 中附答案 |
| `update-notify` | 发送方通知接收方已发生的上游变更影响了接收方 | 确认收到；如需则采取行动；待接收方适应变更后 `resolve` |
| `task` | 发送方请求接收方执行某项有明确边界的操作 | 分级处理；接受或通过 `reject` 附明确理由；完成后 `resolve` |

**`engram review` 中的优先级排序。** 当存在多条 pending 消息时，`engram review` 按以下顺序排列：`severity`（critical → warning → info），然后 `intent`（bug-report 和 task 优先于 question 和 update-notify），然后 `deadline`（最早优先），最后 `created`（最旧优先）。此排序在此处定义，所有合规实现必须产生一致的审查队列。

**对上下文加载的影响。** 会话启动时，接收方的记忆上下文加载器将所有 `pending` 状态的收件箱消息以 `## Pending Cross-Repo Messages` 标题包含在上下文包中。只有 `pending` 消息会被自动加载到上下文中；`acknowledged`、`resolved` 和 `rejected` 消息不会自动加载（可通过 `engram inbox list` 查询）。

---

### §10.4 生命周期

**状态说明：**

- **`pending`** — 消息已发送，位于接收方的 `pending/` 子目录中。在 `engram review` 中可见，并加载到接收方会话上下文中。
- **`acknowledged`** — 接收方（LLM 或人工）已确认收到并承担处理责任。消息移动至 `acknowledged/`。发送方在下次 `engram review` 时通过 `inter_repo.jsonl` 中的 `message_acknowledged` 事件感知。
- **`resolved`** — 接收方已完成请求或隐含的操作。消息移动至 `resolved/` 并附 `resolution_note`。发送方在下次 `engram review` 时通过 `message_resolved` 事件感知。
- **`rejected`** — 接收方明确拒绝处理并给出原因。消息移动至 `rejected/`。发送方在下次 `engram review` 时通过 `message_rejected` 事件感知。

**状态迁移图：**

```
pending ──► acknowledged ──► resolved
   │              │
   └──────────────┴──────────► rejected
```

迁移是单向的：`resolved` 或 `rejected` 状态的消息不能重新打开。若同一问题再次出现，发送方应撰写新消息并将 `reply_to` 指向原始 `message_id`。

**迁移操作（CLI）：**

```bash
# 接收方确认收到
engram inbox acknowledge <message-id>

# 接收方附备注解决
engram inbox resolve <message-id> --note="已在 commit abc123 中修复；GET /api/users 现对不存在的 ID 返回 404。"

# 接收方附原因拒绝
engram inbox reject <message-id> --reason="预期行为：空数组是我们集合端点的已记录契约。"
```

每次迁移均向 `~/.engram/journal/inter_repo.jsonl` 追加一条事件（§10.7）。

**反向通知。** 发送方无需主动轮询解决情况。在下次调用 `engram review` 或 `engram status` 时，CLI 会扫描 `inter_repo.jsonl` 中发送方发出的消息的状态变化，并呈现上次会话以来的所有迁移。输出示例：

```
跨仓收件箱——上次会话以来的更新：
  ✓ 已解决  acme/service-b：GET /api/users 404 修复（消息 acme/service-a:20260418-103000:7f3a）
             备注：已在 commit def789abc 中修复。GET /api/users 现对不存在的 ID 返回 404 Not Found。
             已发布于 service-b v1.4.2。
```

**自动归档。** 已解决消息超过 180 天后，在下次 `engram review` 运行时自动移动至 `~/.engram/archive/inbox/<repo-id>/resolved/`。已拒绝消息超过 30 天后移动至 `~/.engram/archive/inbox/<repo-id>/rejected/`。自动归档向 `inter_repo.jsonl` 追加 `message_archived` 事件。自动归档过程不删除任何消息。

---

### §10.5 去重与流量限制

**去重规则。** 如果两条消息具有相同的 `to` repo-id 和 `intent`，且满足以下至少一项条件，则视为重复：

1. 相同的 `dedup_key`（由发送方显式设置时）。
2. 排序后的 `related_code_refs` 列表的 SHA-256 哈希相同（两条消息均非空时）。
3. `<from>:<正文首行>` 的 SHA-256 哈希相同（`dedup_key` 和 `related_code_refs` 均不可用时的兜底方案）。

当 `engram inbox send` 在接收方的 `pending/` 子目录中检测到重复时，**不**创建新文件，而是：

1. 将新消息正文作为新段落追加到现有文件中，附带 `<!-- duplicate received <timestamp> -->` HTML 注释。
2. 将 frontmatter 中的 `duplicate_count` 字段递增 1。
3. 向 `inter_repo.jsonl` 追加 `message_duplicated` 事件。
4. `engram inbox send` 以状态 `0` 退出，但打印：`已检测到重复——已合并到现有消息 <message-id>（当前 duplicate_count=N）。`

这种方式在防止重复消息刷屏的同时保留了所有信息。

**流量限制。** 为防止失控的 LLM agent 刷爆接收方收件箱：

- **待处理上限：** 同一发送方在同一接收方收件箱中最多可同时存在 20 条 `pending` 消息（可在 `~/.engram/config.toml` 中通过 `inbox.max_pending_per_sender` 配置；默认 20）。
- **24 小时窗口：** 同一发送方向同一接收方在任意 24 小时 UTC 窗口内最多发送 50 条消息（包括被合并的重复消息，可通过 `inbox.max_per_sender_per_day` 配置；默认 50）。

流量限制以 `(发送方, 接收方)` 为单位，非全局限制。超出限制时，`engram inbox send` 以非零状态退出并打印：

```
流量限制已达上限：acme/service-a → acme/service-b
  待处理：20/20  |  24 小时窗口：47/50
  请等待接收方处理消息，或使用 'engram inbox list --to=acme/service-b' 审查并去重。
```

无论如何，`rate_limit_hit` 事件都会追加到 `inter_repo.jsonl`。

---

### §10.6 仓库标识符解析

`<repo-id>` 按以下顺序解析：

1. **显式配置。** 若项目的 `.engram/config.toml` 包含 `repo_id = "acme/service-b"`，则直接使用该字符串。对于长期项目，强烈建议使用显式 repo-id：它能在仓库重命名、主机迁移和远端 URL 变更后保持稳定。

2. **Git 远端哈希。** 若未配置显式 `repo_id`，engram 计算 `sha256(git remote get-url origin)[:12]`（小写十六进制）。只要 git 远端 URL 不变，此值稳定。

3. **路径哈希（兜底）。** 若无 git 远端（如本地独立项目），engram 计算 `sha256(realpath(<项目根目录>))[:12]`。只要项目目录不移动，此值稳定。

**配置 repo_id。** 在项目根目录的 `.engram/config.toml` 中添加：

```toml
[project]
repo_id = "acme/service-b"    # 稳定的人类可读标识符；无空格；允许斜杠
```

**发现机制。** `engram inbox list-repos` 显示本机上所有曾发送或接收过消息的仓库，来源于 `inter_repo.jsonl`。这是日志派生视图，不是目录列表——已归档出活跃收件箱的仓库仍会出现在历史记录中。

**接收方地址簿。** CLI 在 `~/.engram/inbox/.address_book.toml` 维护本地地址簿，从 `inter_repo.jsonl` 填充，将已知的 repo-id 映射到其最后已知的配置名称。这使 `--to=` 的 tab 补全无需网络调用即可工作。

---

### §10.7 `inter_repo.jsonl` 格式

`~/.engram/journal/inter_repo.jsonl` 是用户级别的全局追加写入 JSON Lines 文件，记录本机上所有仓库的收件箱事件。

**事件模式：**

每行为一个 JSON 对象。所有事件的必填字段：

| 字段 | 类型 | 存在于 |
|---|---|---|
| `timestamp` | ISO 8601 字符串 | 所有事件 |
| `event` | string（事件类型） | 所有事件 |
| `message_id` | string | 除 `rate_limit_hit` 外的所有事件 |
| `from` | string（repo-id） | 所有事件 |
| `to` | string（repo-id） | 所有事件 |

**事件类型及其附加字段：**

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"message_sent","from":"acme/service-a","to":"acme/service-b","intent":"bug-report","severity":"warning","message_id":"acme/service-a:20260418-103000:7f3a"}
{"timestamp":"2026-04-18T14:15:00Z","event":"message_acknowledged","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","acknowledged_by":"bob@acme.com"}
{"timestamp":"2026-04-19T09:00:00Z","event":"message_resolved","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","resolution_note":"已在 PR #123 中修复","commit_sha":"abc123def456"}
{"timestamp":"2026-04-20T11:00:00Z","event":"message_rejected","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","rejection_reason":"API 契约 v2 中的预期行为。"}
{"timestamp":"2026-04-18T10:35:00Z","event":"message_duplicated","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","duplicate_count":2}
{"timestamp":"2026-04-18T10:40:00Z","event":"rate_limit_hit","from":"acme/service-a","to":"acme/service-b","limit_type":"pending_cap","current":20,"limit":20}
{"timestamp":"2026-09-20T00:00:00Z","event":"message_archived","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","archive_path":"~/.engram/archive/inbox/acme-service-b/resolved/20260418-103000-from-acme-service-a-bug-users-404.md"}
```

**完整事件类型参考：**

| 事件类型 | 触发时机 | 附加字段 |
|---|---|---|
| `message_sent` | 发送方调用 `engram inbox send` | `intent`、`severity` |
| `message_acknowledged` | 接收方调用 `engram inbox acknowledge` | `acknowledged_by` |
| `message_resolved` | 接收方调用 `engram inbox resolve` | `resolution_note`、`commit_sha`（可选） |
| `message_rejected` | 接收方调用 `engram inbox reject` | `rejection_reason` |
| `message_duplicated` | 发送方发送重复消息，合并到现有消息 | `duplicate_count`（新总数） |
| `rate_limit_hit` | 发送尝试超出流量限制 | `limit_type`（`pending_cap` 或 `daily_window`）、`current`、`limit` |
| `message_archived` | 自动归档运行并移动文件 | `archive_path` |

所有时间戳均为 UTC。文件严格追加写入；任何工具不得编辑或删除其中的行。

---

### §10.8 完整示例

**场景设置：**
- Agent A 工作在 `acme/service-a`（订单处理服务）。
- Agent B 工作在 `acme/service-b`（提供 A 调用的 `/api/users` 端点以验证客户 ID）。
- 两个仓库位于同一台开发者机器上。
- `acme/service-a` 在 `.engram/config.toml` 中配置了 `repo_id = "acme/service-a"`。
- `acme/service-b` 在 `.engram/config.toml` 中配置了 `repo_id = "acme/service-b"`。

**步骤 1 — Agent A 发现 bug。**

在运行 `acme/service-a` 的测试套件时，Agent A 观察到 `GET /api/users?id=nonexistent` 返回 `200 []` 而非 `404`。Agent A 撰写消息：

```bash
engram inbox send \
  --to=acme/service-b \
  --intent=bug-report \
  --severity=warning \
  --deadline=2026-04-25 \
  --code-ref="src/api/users.py:L42@abc123def456" \
  --message="GET /api/users 对不存在的 ID 返回空数组而非 404"
```

**步骤 2 — 消息文件创建。**

engram 写入 `~/.engram/inbox/acme-service-b/pending/20260418-103000-from-acme-service-a-bug-users-404.md`，包含 §10.2 中展示的 frontmatter 和正文。

**步骤 3 — 日志条目追加。**

```jsonl
{"timestamp":"2026-04-18T10:30:00Z","event":"message_sent","from":"acme/service-a","to":"acme/service-b","intent":"bug-report","severity":"warning","message_id":"acme/service-a:20260418-103000:7f3a"}
```

**步骤 4 — Agent B 下次会话。**

Agent B 启动新的 engram 会话时，`engram review` 显示：

```
待处理跨仓收件箱消息（1 条）：
  ⚠ WARNING  [bug-report]  来自 acme/service-a
             GET /api/users 对不存在的 ID 返回空数组而非 404
             截止时间：2026-04-25  |  代码引用：src/api/users.py:L42@abc123def456
             ID：acme/service-a:20260418-103000:7f3a
```

消息也在 `## Pending Cross-Repo Messages` 标题下注入到 Agent B 的会话上下文中。

**步骤 5 — Agent B 确认收到并调查。**

```bash
engram inbox acknowledge acme/service-a:20260418-103000:7f3a
```

文件从 `pending/` 移动到 `acknowledged/`。日志条目：

```jsonl
{"timestamp":"2026-04-18T14:15:00Z","event":"message_acknowledged","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","acknowledged_by":"bob@acme.com"}
```

**步骤 6 — Agent B 修复 bug 并解决消息。**

Agent B 在 `src/api/users.py:L42` 找到 bug，修复后提交新 commit `def789abc`，然后：

```bash
engram inbox resolve acme/service-a:20260418-103000:7f3a \
  --note="已在 commit def789abc 中修复。GET /api/users 现对不存在的 ID 返回 404 Not Found。已发布于 service-b v1.4.2。"
```

文件从 `acknowledged/` 移动到 `resolved/`。日志条目：

```jsonl
{"timestamp":"2026-04-19T09:00:00Z","event":"message_resolved","from":"acme/service-a","to":"acme/service-b","message_id":"acme/service-a:20260418-103000:7f3a","resolution_note":"已在 commit def789abc 中修复。GET /api/users 现对不存在的 ID 返回 404 Not Found。已发布于 service-b v1.4.2。","commit_sha":"def789abc"}
```

**步骤 7 — Agent A 下次会话看到解决通知。**

Agent A 下次 `engram review` 时：

```
跨仓收件箱——上次会话以来的更新：
  ✓ 已解决  acme/service-b：GET /api/users 404 修复（消息 acme/service-a:20260418-103000:7f3a）
             备注：已在 commit def789abc 中修复。GET /api/users 现对不存在的 ID 返回
             404 Not Found。已发布于 service-b v1.4.2。
```

Agent A 现在可以更新自己的代码，正确处理 `404` 响应，同时确信上游修复已到位。

---

### §10.9 隐私与安全

**收件箱是本地的。** `~/.engram/inbox/` 中的消息不会自动离开用户机器。v0.2 中没有自动同步、转发或中继机制。未来版本可能引入可选的网络同步（例如，通过团队收件箱的共享 git 远端），但这明确不在 v0.2 范围内。

**`related_code_refs` 中的路径信息。** 代码引用包含本地文件路径（如 `src/api/users.py:L42`）。对信息分类有严格要求的组织应注意，如果收件箱内容被导出或共享，这些路径可能暴露内部目录结构或模块名称。v0.2 中没有自动导出机制；这是人工注意事项，不是 engram 强制限制。

**追加写入迁移。** 消息撰写后不得编辑。状态迁移（pending → acknowledged → resolved / rejected）将文件移动到新子目录，并追加字段（`acknowledged_at`、`resolved_at`、`resolution_note` 等），但不修改原始的 `from`、`to`、`intent`、`created` 或 `message_id` 字段。这保留了发送内容和发送时间的防篡改记录。

**无自动转发。** Agent A 发给 `acme/service-b` 的消息永远不会自动路由到 `acme/service-c` 或任何其他仓库。跨仓消息要求显式寻址；没有广播模式，也没有抄送（CC）字段。任何转发都是人工的主动操作。

**`inter_repo.jsonl` 是用户全局的。** `~/.engram/journal/inter_repo.jsonl` 日志记录了本机上所有仓库的所有收件箱事件。导出或同步此文件的工具应将其与提交历史或个人生产力日志同等对待，给予相应的隐私保护。

---

---

## 11. 一致性契约

### §11.0 概述

engram 存储库随时间无限增长，这是其设计本意：质量维护通过一致性引擎实现，而非通过容量上限。然而，若缺乏主动监控，无限增长的存储库将积累各种矛盾——事实相互抵牾、规则彼此冲突、引用的资源已不存在、工作流调用的工具已变更，以及资产在未声明的情况下静默地彼此覆盖。若不加以处理，这些不一致性会逐步削弱 LLM 基于存储库进行可靠推理的能力。

一致性引擎解决上述问题，但**不自动删除、不自动修改**。它扫描存储库，将每个检测到的问题归类为七种标准冲突类型之一，并生成一条**提案**——一条结构化、已日志化的冲突记录及其建议修复方案。所有执行均留给操作者决定。

**核心原则：**

1. **检测，不修改。** 一致性引擎仅提出建议，永不修改资产内容、移动文件，或在没有操作者明确指令的情况下更改任何 frontmatter 字段。
2. **每条提案均已日志化。** 所有检测事件和所有解决决策均追加写入 `~/.engram/journal/consistency.jsonl`。审计记录完整且防篡改。
3. **七种标准冲突类型。** 系统检测到的任何不一致性均落入 §11.1 定义的七类之一。该分类体系在 v0.2 范围内是完备的；新增类型需要规范版本升级。
4. **证据驱动，非启发式。** 分类基于 §4.8 定义的置信字段、`graph.db` 中维护的引用图，以及时间有效性字段（`valid_from:`、`valid_to:`、`expires:`）。不基于纯粹的词汇匹配作出任何分类。

本章规定一致性引擎必须遵守的**契约**。**DESIGN §5.2** 规定四阶段扫描算法（静态分析、语义聚类、LLM 辅助审查、fixture 执行）、嵌入策略以及用于评估聚类的 LLM 提示词。实现本契约的工具可采用不同的检测算法，但**必须**生成符合 §11.2 中模式的提案对象，且**必须**永不自动修改资产。

---

### §11.1 七种冲突类型

以下七种类型构成 engram 存储库中一致性问题的标准分类体系。每种类型均具有固定的 `class` 标识符（用于提案对象）、默认严重程度、检测信号摘要，以及一个示例（使用通用名称）。

#### 1. `factual-conflict`（事实冲突）

**定义。** 两个或多个资产对同一主题断言了不同的事实。两者均未对另一方声明 `supersedes:`；两者均未处于 `deprecated` 或 `archived` 状态。两者均处于活跃状态，且在相同主题下均会被加载到 LLM 上下文中。

**检测信号。** 语义聚类（对嵌入向量运行 DBSCAN）识别具有高主题相似度的资产。在每个聚类内部，LLM 辅助审查识别做出矛盾事实断言的资产对或资产组。检测发生在四阶段扫描的语义聚类阶段（DESIGN §5.2）。

**默认严重程度。** `warning`

**示例。** 记忆 A（`local/project_billing_db_choice`）写道"计费服务使用 MySQL"。记忆 B（`pool/design-system/feedback_postgres_only`）写道"平台所有服务均使用 Postgres"。两者均为 `active` 状态，互不引用。

**解决选项。** `update`（修正一个资产）/ `supersede`（声明一方取代另一方）/ `merge`（合并为单一资产）/ `archive`（将一个或两个归档）/ `dismiss`（标记为误报）。

---

#### 2. `rule-conflict`（规则冲突）

**定义。** 两个 `feedback`、`agent` 或团队级别的资产对同一情景规定了相互矛盾的行动。与 `factual-conflict` 的区别在于：此类资产是规范性的（关于应做什么的规则），而非描述性的（关于事实是什么）。注意：§8.4 的决策树在加载时通过层级和 enforcement 级别解决规则冲突；`rule-conflict` 提案在决策树无法产生确定性结果，或两条 `mandatory` 规则相互矛盾时浮现以供所有者决策。

**检测信号。** 对聚类后的 `feedback` 和 `agent` 资产进行同主题 LLM 审查，检查规则正文之间的逻辑矛盾。满足以下条件时触发：（a）两个资产处于相同 enforcement 级别和相同层级位置；（b）两者均未声明指向对方的 `overrides:`；（c）LLM 审查确认规定内容相互矛盾。

**默认严重程度。** 对于 `default` 或 `hint` enforcement 级别的同范围冲突为 `warning`；对于同范围内两条 `mandatory` 资产的冲突为 `error`。

**示例。** 反馈 A（`user/feedback_rebase_before_merge`）规定"合并功能分支前始终进行 rebase"。反馈 B（`user/feedback_merge_commit_preferred`）规定"始终使用 merge commit，永不 rebase"。两者均为 `scope: user`、`enforcement: default`，均未声明 `overrides:`。

**解决选项。** 在较新的资产上添加指向较旧资产的 `supersedes:` / 在较具体的资产上添加 `overrides:` / `merge` 为一条带条件应用的规则 / `archive` 过时的规则。

---

#### 3. `reference-rot`（引用失效）

**定义。** 具有 `references:` frontmatter 字段的资产，或正文中指向外部资源的 `reference` 子类型资产，包含一个不再可解析的引用。目标可能是 URL、文件路径、git SHA 或另一个资产 ID。

**检测信号。** 在静态分析阶段进行周期性爬取（DESIGN §5.2）。对每个 `references:` 字段及 `reference` 子类型正文中的每个 URL/路径：验证 URL 可达性（HTTP 2xx）、文件路径存在性、git SHA 在声明仓库中的存在性，以及资产 ID 在 `graph.db` 中的可解析性。

**默认严重程度。** 若引用在可选的 `references:` 字段中为 `info` / 若引用在必填 frontmatter 字段中（如 `workflow_ptr` 资产中的 `workflow_ref:`）为 `warning` / 若工作流 spine 的 `memory read` 调用指向不存在的资产 ID 为 `error`。

**示例。** 一个 `reference` 子类型记忆（`local/reference_upstream_monitoring_tool`）六个月前创建，指向 `github.com/acme-internal/monitor-v2` 上的一个 GitHub 仓库。该仓库已被删除。资产仍处于 `active` 状态。

**解决选项。** `update`（以当前 URL/路径替换）/ `archive`（资源已消失；退役引用资产）/ `supersede`（已有新引用资产；将旧资产链接至新资产）。

---

#### 4. `workflow-decay`（工作流衰变）

**定义。** 工作流资产的 `spine.*` 调用某个工具、调用某个路径，或依赖某个外部服务，但该工具/路径/服务已不再按预期工作。工作流的 `fixtures/` 测试用例在执行时失败或产生意外输出。

**检测信号。** 在 fixture 执行阶段（DESIGN §5.2）运行 fixture 套件。一致性引擎在沙盒环境（`~/.engram/workspace/consistency-run-<id>/`）中执行工作流的 fixture 套件。fixture 失败触发 `workflow-decay` 提案。部分失败（部分通过、部分失败）产生 `warning`；全部失败产生 `error`。

**默认严重程度。** 全部 fixture 失败为 `error` / 部分 fixture 失败为 `warning`。

**示例。** 某容器部署工作流调用 `kubectl v1.29 rollout status`。宿主机已升级至 `kubectl v1.31`，新版本删除了 spine 使用的某个参数。验证 rollout 检查的 fixture 现以非零状态退出。

**解决选项。** `update`（修订 spine 和 fixtures 以匹配当前环境，然后重新运行自学习）/ `archive`（工作流已过时）/ `escalate`（工作流所有者需判断环境变更是临时的还是永久的）。

---

#### 5. `time-expired`（时间过期）

**定义。** 资产的 frontmatter 中包含已过期的 `valid_to:` 或 `expires:` 日期，但资产仍处于 `active` 状态，且仍被其他活跃资产或工作流引用。按资产自身声明，该资产实际上已过期。

**检测信号。** 静态分析阶段进行日期比较。对每个包含 `valid_to:` 或 `expires:` 的资产：将声明日期与今天的日期对比。若今天 > 声明日期，且资产尚未处于 `deprecated` 或 `archived` 状态，则通过 `graph.db` 检查是否有其他活跃资产引用该资产。

**默认严重程度。** 若资产未被任何活跃资产引用为 `info` / 若资产被一个或多个活跃资产或工作流引用为 `warning`。

**示例。** 项目记忆（`local/project_sprint_q1_requirements`）于 2026 年 1 月创建，设有 `valid_to: 2026-03-31`。现在是 2026 年 4 月 18 日。三个活跃的 `workflow_ptr` 资产通过 `references:` 字段引用该资产。

**解决选项。** `update`（以当前需求替换内容，延长或删除 `valid_to:`）/ `supersede`（为当前冲刺创建新资产，并添加 `supersedes: local/project_sprint_q1_requirements`）/ `archive`（冲刺已结束；不应有新的引用指向该资产）。

---

#### 6. `silent-override`（静默覆盖）

**定义。** 一个较新的资产（按 `created:` 或 `updated:` 日期）与一个较旧的资产涵盖同一主题，实际上在实践中取代了后者——但较新资产并未声明指向较旧资产的 `supersedes:`。较旧资产仍处于 `active` 状态，会与较新资产一同被加载到 LLM 上下文中，造成隐式冗余或矛盾。

**检测信号。** 语义聚类识别该资产对（均在同一聚类中，高度相似）。对比 `created:` / `updated:` 时间戳确定哪个较新。两个资产均未声明 `supersedes:` 确认静默性质。在聚类内 LLM 审查确认较新资产覆盖或矛盾于较旧资产。

**默认严重程度。** `warning`

**示例。** 2026 年 1 月，反馈资产（`user/feedback_naming_snake_case`）规定"所有变量名一律使用 snake_case"。2026 年 4 月，新反馈资产（`user/feedback_naming_kebab_case`）创建，规定"所有标识符一律使用 kebab-case"。两者均不存在 `supersedes:` 链接。

**解决选项。** 在较新资产上添加 `supersedes: user/feedback_naming_snake_case` / `merge` 为带显式适用条件的单一资产 / `archive` 较旧资产（若较新资产具有权威性）/ `dismiss`（若两者在不同上下文中均有意为之，同时为各自添加 `limitations:` 以说明适用范围）。

---

#### 7. `topic-divergence`（同题分歧）

**定义。** 多个资产涉及同一主题，但得出的结论相互矛盾，无法构成连贯一致的整体。这是 `factual-conflict` 的泛化：不是简单的"A 说 X，B 说非 X"二元矛盾，而是三个或更多视角针对同一主题各自合理但整体上无法协调一致。任何单一资产对之间不一定是直接矛盾；问题在于整个聚类未能收敛。

**检测信号。** 聚类级 LLM 审查（DESIGN §5.2）对每个语义聚类分配 `divergence_score`。包含三个或更多资产且分歧分数超过配置阈值的聚类触发 `topic-divergence` 提案。阈值可配置（默认：0-1 分制中的 0.6）。

**默认严重程度。** 若分歧可能是有意为之（如资产代表多种合法设计权衡）为 `info` / 若分歧可能是无意为之（涉及预期存在单一权威答案的主题）为 `warning`。

**示例。** 三个项目记忆涉及"集成测试的最佳组织方式"：记忆 A 写道"与源代码同目录，使用 `*_test.go` 命名"；记忆 B 写道"统一放在顶层 `tests/` 目录"；记忆 C 写道"每个包下使用 `testdata/` 目录"。三者均处于 `active` 状态，互不引用或取代。

**解决选项。** 将该聚类提升为知识库文章（§6），综合各方权衡形成单一连贯策略 / 保留各资产作为有意区分的不同视角，并为每个资产添加 `limitations:` 说明各自的适用范围 / `archive` 较弱的替代方案（若已存在共识）/ 用新的单一权威资产 `supersede` 其余。

---

### §11.2 检测输出格式

每次一致性检测均生成一条**提案对象**。提案是一致性引擎与操作者之间的通信单元。它们存储在日志中（§11.3），由 `engram consistency scan` 返回，并在 `engram review` 中显示。

**提案模式：**

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
  "summary": "计费服务数据库选型与团队级 Postgres-only 规则存在冲突",
  "evidence": {
    "semantic_cluster_id": "cluster-7",
    "confidence_scores": {
      "local/project_billing_db_choice": 0.82,
      "pool/design-system/feedback_postgres_only": 0.95
    },
    "contradiction_text": "项目记忆写道 'MySQL'；团队反馈写道 'Postgres-only mandatory'"
  },
  "suggested_resolutions": [
    {
      "action": "update",
      "target": "local/project_billing_db_choice",
      "rationale": "团队规则为强制级；项目必须遵从"
    },
    {
      "action": "supersede",
      "target": "local/project_billing_db_choice",
      "with": "pool/design-system/feedback_postgres_only"
    },
    {
      "action": "dismiss",
      "rationale": "误报；提案范围过宽"
    }
  ],
  "status": "open"
}
```

**字段语义：**

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `proposal_id` | 字符串 | 必须 | 格式：`cp-<YYYYMMDDHHmmssSSS>-<6位十六进制>`。全局唯一。 |
| `detected_at` | ISO 8601 UTC | 必须 | 提案创建时间戳。 |
| `class` | 枚举字符串 | 必须 | §11.1 中七种类型标识符之一。 |
| `severity` | 枚举字符串 | 必须 | `info` / `warning` / `error`。参见 §11.1 各类型默认值。 |
| `involved_assets` | 字符串[] | 必须 | 资产 ID 列表（相对于存储根目录）。至少包含一个资产。 |
| `summary` | 字符串 | 必须 | 描述冲突的单句人类可读描述。 |
| `evidence` | 对象 | 必须 | 检测证据。必填子字段因类型而异（见下表）。 |
| `suggested_resolutions` | 对象[] | 必须 | 至少包含一条解决建议。 |
| `status` | 枚举字符串 | 必须 | 初始值始终为 `open`。 |

**各冲突类型的 `evidence` 必填子字段：**

| 冲突类型 | 必填证据字段 |
|---|---|
| `factual-conflict` | `semantic_cluster_id`、`confidence_scores`、`contradiction_text` |
| `rule-conflict` | `semantic_cluster_id`、`confidence_scores`、`contradiction_text` |
| `reference-rot` | `broken_reference`（失效的 URL/路径/ID）、`check_type`（`url`/`path`/`sha`/`asset-id`）、`last_checked_at` |
| `workflow-decay` | `fixture_run_id`、`failed_fixtures`（列表）、`exit_codes` |
| `time-expired` | `declared_expiry`（`valid_to:` 或 `expires:` 的值）、`active_referrers`（仍引用该资产的资产 ID 列表） |
| `silent-override` | `semantic_cluster_id`、`older_asset`、`newer_asset`、`date_delta_days` |
| `topic-divergence` | `semantic_cluster_id`、`divergence_score`、`asset_count` |

**`suggested_resolutions[].action` 枚举：**

| 动作 | 语义 |
|---|---|
| `update` | 编辑指定资产的内容。操作者提供新文本；LLM 可起草。 |
| `supersede` | 在较新资产上添加指向较旧资产的 `supersedes:` frontmatter。较旧资产转为 `deprecated`。 |
| `merge` | 将两个或多个资产合并为一个新资产；原资产转为 `deprecated`。 |
| `archive` | 将指定资产移动到 `archive/`（适用保留策略；最短保留期下限为 6 个月）。 |
| `dismiss` | 将提案标记为误报。相同证据对在 90 天内不再触发新提案。 |
| `escalate` | 将决策权移交给范围所有者；从 LLM 关注队列中移除该提案。 |

**状态迁移：**

```
open → in_review → resolved
                 → dismissed
                 → expired（若提案超过 90 天未解决）
```

处于 `expired` 状态的提案移至归档日志区段；操作者在 `engram review` 中收到最终提醒。

---

### §11.3 `consistency.jsonl` 日志格式

所有一致性引擎事件以追加写入方式记录在 `~/.engram/journal/consistency.jsonl` 中。这是所有提案、审查和解决操作的审计记录。

**文件位置：** `~/.engram/journal/consistency.jsonl`

**格式：** 每行一个 JSON 对象，每行是一条事件记录。

**事件记录：**

```jsonl
{"timestamp":"2026-04-18T09:32:15Z","event":"proposal_created","proposal_id":"cp-20260418093215-a1b2c3","class":"factual-conflict","severity":"warning","involved":["local/project_billing_db_choice","pool/design-system/feedback_postgres_only"]}
{"timestamp":"2026-04-18T14:10:00Z","event":"proposal_reviewed","proposal_id":"cp-20260418093215-a1b2c3","reviewer":"alice@acme.com","decision":"update","resolution_asset":"local/project_billing_db_choice"}
{"timestamp":"2026-04-18T14:10:30Z","event":"proposal_resolved","proposal_id":"cp-20260418093215-a1b2c3","applied_action":"update","resolved_by":"alice@acme.com"}
```

**事件类型：**

| 事件 | 写入时机 |
|---|---|
| `proposal_created` | 一致性引擎创建新提案时 |
| `proposal_reviewed` | 操作者（人类或 LLM）从 `suggested_resolutions` 中选择动作时 |
| `proposal_resolved` | 所选动作已执行，提案转为 `resolved` 状态时 |
| `proposal_dismissed` | 操作者将提案标记为误报（`action: dismiss`）时 |
| `proposal_expired` | 提案在 90 天内未解决，状态设为 `expired` 时 |

**各事件必填字段：**

| 事件 | 必填字段 |
|---|---|
| `proposal_created` | `timestamp`、`event`、`proposal_id`、`class`、`severity`、`involved` |
| `proposal_reviewed` | `timestamp`、`event`、`proposal_id`、`reviewer`、`decision` |
| `proposal_resolved` | `timestamp`、`event`、`proposal_id`、`applied_action`、`resolved_by` |
| `proposal_dismissed` | `timestamp`、`event`、`proposal_id`、`dismissed_by`、`reason` |
| `proposal_expired` | `timestamp`、`event`、`proposal_id`、`age_days` |

**追加写入不变量。** `consistency.jsonl` 中的行永不修改或删除。已解决和已忽略的提案在活跃日志中无限期保留其完整历史。压缩操作——将旧的已解决/已忽略条目移至 `~/.engram/archive/journal/consistency-<YYYY>.jsonl`——在两年后执行。压缩采用先复制后截断的方式；原始条目在活跃日志缩短之前已存在于归档中。

**重复检测。** 若一致性引擎检测到与现有 `open` 或 `in_review` 提案相同的证据对（相同的 `involved_assets` + 相同的 `class`），不会创建重复提案，而是在日志中追加 `proposal_re_detected` 事件，并将现有提案的 `detected_at` 更新为新时间戳。若匹配的提案处于 `dismissed` 状态且距忽略时间不足 90 天，则不创建新提案。90 天后忽略过期，写入新的 `proposal_created` 事件。

---

### §11.4 置信度与证据

一致性引擎的分类以证据为驱动。本节说明 §4.8 中的置信字段如何参与检测决策，以及置信度值如何在系统使用过程中得到更新。

**置信分公式**（§4.8 中的规范定义；此处在 §11 上下文中重申）：

```
confidence_score = (validated_count - 2 × contradicted_count - staleness_penalty)
                   / max(1, total_events)

其中：
  total_events     = validated_count + contradicted_count
  staleness_penalty = 0.0  若 last_validated 在今天 90 天以内
                   | 0.3  若 last_validated 在今天 365 天以内
                   | 0.7  若 last_validated 超过 365 天之前
```

**置信分如何参与一致性引擎决策：**

- 高置信度资产（`score > 0.7`）参与 `factual-conflict` 时会提升提案严重程度：LLM 已多次确认高置信度资产，使得该矛盾更具可操作性。
- 低置信度资产（`score < 0`）参与 `factual-conflict` 或 `rule-conflict` 时会将提案严重程度降至 `info`：该资产本身可能已不可靠；冲突可能无关紧要。
- 提案对象（§11.2）中的 `evidence.confidence_scores` 字段报告检测时所有 `involved_assets` 的置信分。

**置信度何时更新：**

LLM 调用在上下文中使用资产 X 时，根据结果可能触发置信度更新：

- **正面结果**（任务成功完成；用户确认）：`validated_count++`，`last_validated = now`，`usage_count++`
- **负面结果**（现实与资产矛盾；用户明确纠正）：`contradicted_count++`，`usage_count++`
- **中性**（资产已加载但结果未被跟踪）：仅 `usage_count++`

**谁来报告结果：**

- **LLM 代理**通过 `engram memory validate-use <id> --outcome=success|failure` 命令（从工作流 spine 的运行后钩子或适配器的完成钩子中调用）。
- **人类**通过 `engram review`（对近期会话中使用的记忆进行点赞/点踩）。
- **一致性引擎本身**通过结果启发：若某资产参与的提案被忽略为误报，这是一个弱正面信号（资产内容有效；提案有误）。引擎可将 `validated_count` 增加 1，并在证据中记录注释。这是引擎唯一允许触碰资产 frontmatter 的场景——且仅限 `confidence` 子字段，永不涉及正文或其他任何 frontmatter 字段。

**由陈旧度触发的提案：**

`confidence_score < 0` 且 `last_validated` 超过 365 天的资产可自动触发提案生成：
- 若资产设有 `valid_to:` 且日期已过：提出 `time-expired` 提案。
- 若语义聚类中存在同主题的较新资产：提出 `topic-divergence` 提案。

**安全不变量：永不因低置信度自动归档。** 负的置信分会将资产浮现在 `engram review` 中供人工决策。引擎创建提案后即停止，不移动文件、不修改 frontmatter 中的 `state:` 字段、也不从未来的 LLM 上下文中压制该资产。

---

### §11.5 修复工作流

本节描述从检测到解决的提案完整生命周期，从操作者视角呈现。

**第一步——检测（后台）。**

一致性引擎以后台进程形式运行其四阶段扫描（调度和阶段序列参见 DESIGN §5.2）。检测到冲突时，创建提案对象（§11.2）并以 `proposal_created` 事件写入 `consistency.jsonl`。任何资产均不被触碰。

**第二步——浮现（`engram review`）。**

`engram review` 命令从 `consistency.jsonl` 汇总所有未结提案，按严重程度排序显示（`error` 最先，然后 `warning`，最后 `info`），同严重程度内按 `detected_at` 排序（最旧的最先）。摘要行和 `involved_assets` 列表使操作者能快速了解每个问题。

**第三步——审查。**

操作者选择要检查的提案。`engram consistency report <proposal-id>` 显示包含证据详情的完整提案对象。

**第四步——解决。**

操作者发出解决命令：

```bash
# 修正一个资产以与另一个保持一致
engram consistency resolve <proposal-id> --action=update \
  --asset=local/project_billing_db_choice

# 声明较新资产取代较旧资产
engram consistency resolve <proposal-id> --action=supersede \
  --older=local/project_billing_db_choice \
  --newer=pool/design-system/feedback_postgres_only

# 将两个资产合并为新的单一资产
engram consistency resolve <proposal-id> --action=merge \
  --assets=user/feedback_naming_snake_case,user/feedback_naming_kebab_case \
  --into=user/feedback_naming_convention

# 归档过时或已废弃的资产
engram consistency resolve <proposal-id> --action=archive \
  --asset=local/project_sprint_q1_requirements \
  --reason="Q1 冲刺已结束；需求已由 Q2 规划文档取代"

# 标记为误报
engram consistency resolve <proposal-id> --action=dismiss \
  --reason="资产适用于不同上下文；冲突不成立"

# 上报给范围所有者
engram consistency resolve <proposal-id> --action=escalate
```

**第五步——执行。**

所选动作被执行：相关资产被修改（`update`、`supersede`、`merge`），移入 `archive/`（`archive`），或提案被标记为 `dismissed` / `escalated`。`proposal_reviewed` 事件和 `proposal_resolved`（或 `proposal_dismissed`）事件追加写入 `consistency.jsonl`。

**第六步——审计记录。**

提案的完整历史——检测时的证据、操作者决策和解决结果——永久记录在 `consistency.jsonl` 中。解决后的查询（`engram consistency report <proposal-id>`）仍返回完整记录。

**自动过期规则（不依赖自动修改的积压管理）：**

保持 `open` 状态超过 90 天的提案自动转为 `expired`。操作者在 `engram review` 中收到最终提醒。`proposal_expired` 事件写入 `consistency.jsonl`。过期提案不再出现在默认的 `engram review` 视图中，但可通过 `engram review --include-expired` 访问。

**重复检测行为。** 若同一冲突在提案 `expired` 之后或在 `dismiss` 90 天过期后再次被检测到，一致性引擎创建新的 `proposal_created` 事件（新的 `proposal_id`）。新提案的 `evidence` 字段中以 `prior_proposal_id` 引用此前过期/忽略的提案。

---

### §11.6 非目标与安全不变量

本节明确列出一致性引擎不执行的操作。这些是不可谈判的不变量。违反其中任何一条的工具均不符合本规范。

**一致性引擎不执行以下操作：**

- **永不自动删除。** 归档操作仅在操作者在解决命令中明确指定 `--action=archive` 时发生。引擎本身不具备自主归档能力。
- **永不自动编辑资产内容。** 解决命令中的 `update` 动作由操作者（或在操作者指令下行事的 LLM）提供新内容。引擎本身不向任何资产文件写入新的正文文本。
- **永不自动应用提案。** 任何提案从 `open` 到 `resolved` 的状态迁移都需要操作者的明确解决命令。后台处理不会消费自身生成的提案。
- **永不在会话关键路径上运行。** 一致性扫描以后台进程方式调度。引擎不在相关性闸门评估、LLM 上下文打包，或任何 LLM 正在等待响应的路径上内联运行。
- **不以零误报为目标。** 引擎倾向于浮现更多提案（更高召回率），而非压制不确定的检测（更高精确率）。遗漏真实冲突比产生嘈杂的误报提案更有害，后者操作者可以忽略。

**安全不变量：**

- 在没有操作者明确指令的情况下，一致性引擎**永不修改**资产的物理文件。这适用于正文内容、frontmatter 字段、文件名和目录位置。
- 唯一例外是 frontmatter 中的 `confidence` 子字段（§11.4）：当某资产的提案被忽略为误报时，引擎可将 `validated_count` 增加 1。此例外严格受限：引擎不得修改任何其他 frontmatter 字段。
- 引擎在每次运行使用**沙盒工作空间**（`~/.engram/workspace/consistency-run-<id>/`，参见 DESIGN §3.6）。用于 `workflow-decay` 检测的 fixture 执行发生在此沙盒中，永不在活跃工作流目录中执行。
- 针对 `enforcement: mandatory` 资产的提案被路由给**范围维护者**（在范围的 CODEOWNERS 或等效文件中声明的身份），而非由订阅者消费。订阅者无法针对其不拥有的强制级资产解决提案。
- 归档保留下限：通过一致性解决命令移动到 `archive/` 的任何资产，在允许物理删除前必须保留至少 **6 个月**。这与整个系统中所有归档操作适用的保留下限相同。

---

### §11.7 集成点

一致性引擎与 engram 系统以下部分存在交互。本表为交叉参考指南；每行列出集成点及对应的规范章节。

| 集成点 | 引擎使用/生成的内容 | 规范章节 |
|---|---|---|
| 资产置信字段 | frontmatter 中的 `validated_count`、`contradicted_count`、`last_validated`、`usage_count` 参与证据评分 | §4.8 |
| 引用图（`graph.db`）| 引擎查询引用图以检测 `reference-rot`，并在提出 `archive` 前检查入引用计数 | §3.3、§4.1 |
| 入引用保护 | 有入引用的资产不得被提案为删除（归档）；§3.3 的 MUST 4 同样适用于一致性提案 | §3.3 |
| Scope 模型 enforcement | 资产的 `enforcement:` 级别影响提案的严重程度分配（mandatory 冲突升级为 `error`） | §8.3 |
| 时间有效性字段 | `valid_from:` / `valid_to:` / `expires:` 触发 `time-expired` 提案 | §4.1、§4.8 |
| Pool 传播 | 跨 pool 资产集合被纳入语义聚类；pool 与订阅者之间的分歧可浮现为 `factual-conflict` 或 `topic-divergence` | §9.5 |
| 收件箱 | 对于 `update-notify` 意图的消息，引擎可通过收件箱机制浮现相关的 `silent-override` 或 `topic-divergence` 提案 | §10.3 |
| 自学习引擎（工作流） | 自学习引擎无法自动修复的 fixture 失败被上报为 `workflow-decay` 提案 | §5 / DESIGN §5.2 |
| 校验层 | `engram validate` 对强制级覆盖违规报错（§8）；一致性引擎捕获 validate 不会标记为硬错误的静默不一致性 | §12 |
| 一致性日志 | 所有提案和解决操作追加到 `consistency.jsonl`；该日志是所有引擎活动的唯一事实来源 | §11.3 |
| Web UI（`engram review`）| 未结提案在总览面板和一致性视图中浮现；解决动作触发 §11.5 中描述的解决命令 | DESIGN §7 |

---

### §11.8 前瞻性说明

以下能力有意推迟实现，此处记录以避免实现者在试错中重新发现范围边界。

**推迟至 DESIGN §5.2（算法，非契约）：**

- **四阶段扫描算法。** 静态分析 → 语义聚类 → LLM 辅助审查 → fixture 执行的序列，包括精确的 DBSCAN 参数、聚类阈值、LLM 提示词模板及 fixture 执行框架，在 DESIGN §5.2 中规定。本章规定的契约（提案必须是什么样的，引擎必须绝对不做什么）是固定的；实现该契约的算法则不然。
- **严重程度排序与噪声调优。** 生产部署可能希望将 `info` 级提案压制在可配置阈值以下，或对 `error` 级提案进行告警加权。这些属于运营配置关注点，归属 DESIGN §5.2。

**推迟至未来规范版本：**

- **机器学习驱动的严重程度排序。** 基于历史操作者行为自动提升或降级提案严重程度（例如："此类提案总是被忽略 → 降级为 info"）需要一个尚未规定的反馈循环。未来工作。
- **跨仓冲突检测。** 当两个不同仓库的代理在各自收件箱中有相互矛盾的提案时（Agent A 提出更新资产 X；Agent B 提出删除资产 X），需要一个协调协议。这超出了 v0.2 单仓库一致性模型的范围。未来工作。
- **批量解决工作流。** 大型存储库可能一次性生成数百条 `time-expired` 提案。批量解决命令（`engram consistency resolve-all --class=time-expired --action=archive --older-than=180d`）推迟至未来 UX 迭代；§11.5 中的解决协议仅处理单提案情形。

---

---

## 12. 校验规则与错误码注册表

### §12.0 概述

§12 是 `engram validate` 的机器可读契约。它列出了任何符合 engram 规范的工具**必须**执行的所有结构与模式校验规则，并为每条规则分配一个稳定的、可被引用的错误码。这些码出现在 CLI 输出、JSON 报告、CI 日志以及本文档的交叉引用中。

**范围。** §12 覆盖结构与模式的正确性——文件存在性、frontmatter 语法、必填字段、类型约束、引用完整性及生命周期状态——所有这些均可在读写时无需 LLM 辅助进行机械检查。各自有效但相互语义冲突的资产，由 §11（一致性契约）处理。

**错误码方案。** 每个码的格式为 `{严重程度}-{分类}-{编号}`：

- **严重程度** — `E`（错误，退出码 2）/ `W`（警告，退出码 1）/ `I`（信息，退出码 0 并附注）
- **分类** — 三字母范围缩写（完整表格见 §12.14）
- **编号** — 三位数字，在各分类内零填充

**分类总览：**

| # | 分类 | 前缀 | 覆盖内容 |
|---|---|---|---|
| 1 | 结构（Structural） | STR | 文件/目录存在性与布局 |
| 2 | Frontmatter | FM | 必填/可选字段、类型、格式 |
| 3 | 记忆子类型（Memory subtypes） | MEM | 各子类型内容规则 |
| 4 | 工作流（Workflow） | WF | Spine、fixtures、metrics、修订规则 |
| 5 | 知识库（Knowledge Base） | KB | 章节与编译摘要规则 |
| 6 | MEMORY.md 索引（IDX） | IDX | 索引格式与覆盖率 |
| 7 | Scope | SCO | Scope 层次一致性 |
| 8 | Enforcement | ENF | mandatory/default/hint 覆盖规则 |
| 9 | 引用（References） | REF | 引用图完整性 |
| 10 | Pool | POOL | Pool 传播与订阅规则 |
| 11 | 收件箱（Inbox） | INBOX | 收件箱消息格式与生命周期 |
| 12 | 一致性（Consistency） | CONS | 一致性提案完整性 |

**CLI 集成：**

```
engram validate                        # 运行全部校验器；退出 0 / 1 / 2
engram validate --category=STR,FM      # 按分类运行
engram validate --json                 # 机器可读输出（§12.13）
```

---

### §12.1 结构（STR-*）

结构规则在任何内容解析开始前，检查必要的目录和文件是否存在于预期路径。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-STR-001` | 错误 | 项目根目录下存在 `.memory/` 目录 | §3.2 |
| `E-STR-002` | 错误 | `.memory/MEMORY.md` 存在 | §7 |
| `E-STR-003` | 错误 | `.memory/local/` 目录存在（用于项目级资产） | §3.2 |
| `W-STR-001` | 警告 | `.memory/` 存在但不含任何资产 | §3 |
| `W-STR-002` | 警告 | `.memory/` 顶层出现意外条目——不属于：`MEMORY.md`、`local/`、`pools/`、`workflows/`、`kb/`、`index/`、`pools.toml` | §3.2 |
| `E-STR-004` | 错误 | 用户全局 `~/.engram/version` 文件缺失（工具进行规范版本检查时需要该文件） | §13 |
| `W-STR-003` | 警告 | `~/.engram/version` 存在但其主版本号与已安装工具的主版本号不匹配 | §13 |

**说明。** `E-STR-001` 至 `E-STR-003` 是所有后续校验器的先决条件。若其中任一失败，其他分类的校验器可能产生虚假结果，应在结构错误修复之前跳过。

---

### §12.2 Frontmatter（FM-*）

Frontmatter 规则适用于所有资产文件（记忆、工作流文档、知识库章节、收件箱消息）。未通过 `E-FM-001` 或 `E-FM-002` 的文件无法进一步校验，其余 FM 检查对该文件均跳过。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-FM-001` | 错误 | 资产文件不含 YAML frontmatter 块（缺少开头的 `---`） | §4.1 |
| `E-FM-002` | 错误 | YAML frontmatter 格式错误（解析出错） | §4.1 |
| `E-FM-003` | 错误 | 必填字段 `name` 缺失 | §4.1 |
| `E-FM-004` | 错误 | 必填字段 `description` 缺失 | §4.1 |
| `E-FM-005` | 错误 | 必填字段 `type` 缺失 | §4.1 |
| `E-FM-006` | 错误 | `type` 值不属于 6 个有效子类型之一：`user`、`feedback`、`project`、`reference`、`workflow_ptr`、`agent` | §4.1 |
| `E-FM-007` | 错误 | 必填字段 `scope` 缺失（v0.2+） | §4.1 |
| `E-FM-008` | 错误 | `scope` 值不属于 5 个有效 scope 标签之一：`user`、`project`、`team`、`org`、`pool` | §4.1 |
| `E-FM-009` | 错误 | `scope: pool` 资产缺少必填 `pool:` 字段 | §8.2 |
| `E-FM-010` | 错误 | `scope: pool` 资产在消费方 `pools.toml` 中缺少对应的 `subscribed_at:` 条目 | §8.2 |
| `E-FM-011` | 错误 | `scope: org` 资产缺少必填 `org:` 字段 | §8.1 |
| `E-FM-012` | 错误 | `scope: team` 资产缺少必填 `team:` 字段 | §8.1 |
| `W-FM-001` | 警告 | 可选字段使用不当（例如，在不支持到期的子类型上使用 `expires:`） | §4.1 |
| `W-FM-002` | 警告 | `description` 值超过 150 个字符（MEMORY.md 钩子显示在 150 字符处截断） | §7.2 |
| `W-FM-003` | 警告 | ISO 8601 日期字段（`created`、`updated`、`expires`、`valid_from`、`valid_to`）格式错误 | §4.1 |

---

### §12.3 记忆子类型（MEM-*）

MEM 规则在 FM 规则通过后应用。每条规则针对特定子类型；校验器在应用这些规则前**必须**检查子类型身份。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-MEM-001` | 错误 | `feedback` 子类型缺少必填 `enforcement:` 字段 | §4.3 |
| `E-MEM-002` | 错误 | `enforcement:` 值不属于 `mandatory`、`default`、`hint` 之一 | §8.3 |
| `E-MEM-003` | 错误 | `feedback` 正文缺少 `**Why:**` 和/或 `**How to apply:**` 章节 | §4.3 |
| `E-MEM-004` | 错误 | `project` 正文缺少 `**Why:**` 和/或 `**How to apply:**` 章节 | §4.4 |
| `E-MEM-005` | 错误 | `workflow_ptr` 子类型缺少必填 `workflow_ref:` 字段 | §4.6 |
| `E-MEM-006` | 错误 | `workflow_ptr` 的 `workflow_ref:` 指向不存在的工作流路径 | §4.6 |
| `E-MEM-007` | 错误 | `agent` 子类型缺少必填 `source:` 字段 | §4.7 |
| `W-MEM-001` | 警告 | `project` 记忆正文包含相对日期表达式（例如"下周四"、"上周"） | §4.4 |
| `W-MEM-002` | 警告 | `agent` 记忆缺少可选 `confidence:` 字段（推荐用于证据评分） | §4.7、§4.8 |

---

### §12.4 工作流（WF-*）

WF 规则应用于 `.memory/workflows/` 下的每个工作流目录。未通过 `E-WF-001` 至 `E-WF-003` 的工作流目录结构不完整；下游校验器应跳过该目录。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-WF-001` | 错误 | 工作流目录缺少必填 `workflow.md` | §5.1 |
| `E-WF-002` | 错误 | 工作流目录缺少必填 `spine.*` 文件 | §5.1 |
| `E-WF-003` | 错误 | 工作流目录缺少必填 `fixtures/` 目录 | §5.1 |
| `E-WF-004` | 错误 | `fixtures/` 目录不含任何 fixture 文件（至少需要 1 个） | §5.4 |
| `E-WF-005` | 错误 | 工作流目录缺少 `metrics.yaml` | §5.5 |
| `E-WF-006` | 错误 | `workflow.md` frontmatter 中的 `spine_lang` 值不是受支持的语言标识符 | §5.2 |
| `E-WF-007` | 错误 | `rev/current` 符号链接存在但悬空（指向不存在的修订版本） | §5.6 |
| `W-WF-001` | 警告 | `fixtures/` 目录中无成功用例 fixture（推荐至少一个） | §5.4 |
| `W-WF-002` | 警告 | `fixtures/` 目录中无失败用例 fixture（推荐至少一个） | §5.4 |
| `W-WF-003` | 警告 | `spine.*` 文件声明的副作用未在 `workflow.md` frontmatter 的 `side_effects:` 字段中列出 | §5.3 |
| `W-WF-004` | 警告 | `metrics.yaml` 中未定义 `metric_primary` | §5.5 |

---

### §12.5 知识库（KB-*）

KB 规则应用于 `.memory/kb/` 下的每个主题目录。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-KB-001` | 错误 | 知识库主题目录缺少必填 `README.md` | §6.1 |
| `E-KB-002` | 错误 | 知识库主题目录不含任何章节文件（至少需要 1 个） | §6.1 |
| `E-KB-003` | 错误 | `README.md` frontmatter 的 `chapters:` 列表中引用了不存在的文件 | §6.2 |
| `W-KB-001` | 警告 | `_compiled.md` 缺失——建议在活跃使用前先进行编译 | §6.5 |
| `W-KB-002` | 警告 | `_compile_state.toml` 哈希与当前章节内容不匹配——`_compiled.md` 已过期 | §6.5 |
| `W-KB-003` | 警告 | 主题目录中存在章节文件但未出现在 `chapters:` 列表中（孤儿章节） | §6.2 |

---

### §12.6 MEMORY.md 索引（IDX-*）

IDX 规则校验层级式着陆索引(§7)。§12 是这些错误码的规范定义,所有先前章节引用时一律使用此处定义的 3 位数形式。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-IDX-001` | 错误 | `MEMORY.md` 包含相对路径无法解析到实际文件的链接（悬空链接） | §7.2 |
| `E-IDX-002` | 错误 | `local/` 下的资产文件既未在 `MEMORY.md` 也未在任何 `index/<topic>.md` 中建立索引 | §7.2 |
| `E-IDX-003` | 错误 | `MEMORY.md` 中 `## Topics` 章节标题出现超过一次（结构性重复） | §7.2 |
| `W-IDX-001` | 警告 | `MEMORY.md` L1 条目数超过第 95 百分位阈值（索引密度信号——见 §16 词汇表） | §7、§16 |
| `W-IDX-002` | 警告 | `MEMORY.md` 中引用了 `index/<topic>.md` 文件，但该文件不存在 | §7.3 |
| `W-IDX-003` | 警告 | `MEMORY.md` 中某资产既有内联条目，又出现在某个主题子索引中（重复索引） | §7.2 |

---

### §12.7 Scope（SCO-*）

SCO 规则验证资产声明的 scope 与其文件系统位置以及所声明的 scope 目录是否一致。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-SCO-001` | 错误 | 资产声明 `scope: org` 但 `org:` 字段值与 `~/.engram/org/<name>/` 下的已有目录不对应 | §8.1 |
| `E-SCO-002` | 错误 | 资产声明 `scope: team` 但 `team:` 字段值与已有团队目录不对应 | §8.1 |
| `E-SCO-003` | 错误 | 资产声明 `scope: pool` 但 `~/.engram/pools/` 下不存在该 pool 目录 | §8.2 |
| `W-SCO-001` | 警告 | `scope: project` 资产带有 `enforcement: mandatory`——项目级 mandatory 不常见；推荐使用 team 或更高 scope | §8.7 |
| `W-SCO-002` | 警告 | 资产声明的 `scope` 与其文件系统位置不匹配（例如 `scope: user` 但文件位于 `.memory/local/`） | §3.2 |

**说明。** `W-SCO-001` 是 §8.7 中之前引用的码的规范定义。

---

### §12.8 Enforcement（ENF-*）

ENF 规则检查覆盖链的有效性。`E-ENF-001` 是 §8.3 和 §9.6 中之前引用的码的规范定义。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-ENF-001` | 错误 | 低层 scope 资产与带有 `enforcement: mandatory` 的高层 scope 资产冲突（mandatory enforcement 不可被覆盖） | §8.3、§8.4 |
| `E-ENF-002` | 错误 | 资产声明 `overrides: <id>` 但目标资产不存在 | §8.3 |
| `W-ENF-001` | 警告 | 资产覆盖了一个 `default`-enforcement 资产，但未声明 `overrides:` 字段 | §8.3 |
| `W-ENF-002` | 警告 | `overrides:` 目标的 scope 层级不高于声明资产（同层或更低层的覆盖存在疑点） | §8.3 |
| `W-ENF-003` | 警告 | `overrides:` 链存在循环（A 覆盖 B，B 覆盖 A） | §8.3 |

---

### §12.9 引用（REF-*）

REF 规则校验引用图。`W-REF-001` 是 §9.6 中之前引用的码的规范定义。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-REF-001` | 错误 | `references:` 条目指向不存在的资产（悬空引用） | §3.3 MUST 4 |
| `E-REF-002` | 错误 | 一个有入引用条目的资产正被删除；必须先弃用（移至 `archive/`）才能删除 | §3.3 MUST 4 |
| `E-REF-003` | 错误 | `supersedes:` 字段指向不存在的目标 | §4.1 |
| `W-REF-001` | 警告 | 引用腐化：`references:` 目标已被移至 `archive/` | §9.6 |
| `W-REF-002` | 警告 | 检测到 `supersedes:` 循环链 | §4.1 |
| `W-REF-003` | 警告 | 资产正文中的 `[[wiki-link]]` 指向不存在的资产 | §3.3 MUST 1 |

---

### §12.10 Pool（POOL-*）

POOL 规则应用于订阅方项目和 pool 目录。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-POOL-001` | 错误 | `pools.toml` 声明 `propagation_mode: pinned` 但 `pinned_revision:` 为空或缺失 | §9.2 |
| `E-POOL-002` | 错误 | `pools.toml` 引用的 pool 名称在 `~/.engram/pools/` 下不存在对应目录 | §9.2 |
| `E-POOL-003` | 错误 | Pool 的 `rev/current` 符号链接悬空（指向不存在的修订版本） | §9.1 |
| `W-POOL-001` | 警告 | 订阅的 pool 有新修订版本待审查，且 `propagation_mode` 为 `notify` | §9.3 |
| `W-POOL-002` | 警告 | Pool 目录缺少 `.engram-pool.toml` 清单文件 | §9.1 |
| `W-POOL-003` | 警告 | `pools.toml` 中声明的 `subscribed_at` scope 层级与 pool 声明的发布者 scope 不匹配（可能存在层次误用） | §9.2 |

---

### §12.11 收件箱（INBOX-*）

INBOX 规则应用于 `~/.engram/inbox/<repo-id>/` 下的消息文件。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-INBOX-001` | 错误 | 收件箱消息文件缺少一个或多个必填字段：`from:`、`to:`、`intent:`、`status:` | §10.2 |
| `E-INBOX-002` | 错误 | `intent` 值不属于 5 个有效意图之一：`bug-report`、`api-change`、`question`、`update-notify`、`task` | §10.3 |
| `E-INBOX-003` | 错误 | `status` 值不属于 4 个有效状态之一：`pending`、`acknowledged`、`resolved`、`expired` | §10.4 |
| `E-INBOX-004` | 错误 | 收件箱消息文件位于错误的状态目录中（例如 `status: pending` 但文件在 `resolved/` 下） | §10.4 |
| `W-INBOX-001` | 警告 | 待处理消息超过 30 天无确认 | §10.4 |
| `W-INBOX-002` | 警告 | 发送方已超过投递日志中记录的速率限制 | §10.5 |
| `W-INBOX-003` | 警告 | `reply_to:` 字段引用了不存在的消息 ID | §10.2 |

---

### §12.12 一致性（CONS-*）

CONS 规则应用于 `consistency.jsonl` 日志及其提案。这些规则由 `engram validate` 检查；更深层的语义冲突检测是一致性引擎的职责（§11）。

| 码 | 严重程度 | 规则 | 章节 |
|---|---|---|---|
| `E-CONS-001` | 错误 | `consistency.jsonl` 中的某提案引用了不再存在的资产路径 | §11.3 |
| `W-CONS-001` | 警告 | 某未结提案已挂起超过 90 天且未完成解决（即将到期） | §11.5 |
| `W-CONS-002` | 警告 | 某提案的 `involved_assets` 列表包含已移至 `archive/` 的资产 | §11.2 |
| `I-CONS-001` | 信息 | 提案创建速率超过每天 10 条——高频可能表明存在值得排查的根本原因 | §11.5 |

---

### §12.13 CLI 输出格式

**JSON 模式（`engram validate --json`）：**

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

**文本模式（`engram validate`）：**

```
.memory/local/feedback_example.md:
  E-FM-003 (error) required field `name` missing
    → SPEC §4.1

.memory/MEMORY.md:
  W-IDX-001 (warning) MEMORY.md L1 entry count exceeds 95th-percentile threshold
    → SPEC §7

2 errors, 5 warnings — exit 2
```

**退出码：**

| 退出码 | 含义 |
|---|---|
| `0` | 通过——无错误，无警告（信息级提示仍可能打印） |
| `1` | 存在警告——无错误 |
| `2` | 存在一个或多个错误 |

---

### §12.14 分类汇总

完整码空间分配表。每个分类拥有 `001–099` 范围；`100–999` 的编号保留供未来扩展。

| 分类 | 前缀 | 范围 | 主要章节 |
|---|---|---|---|
| 结构（Structural） | STR | 001–099 | §3 |
| Frontmatter | FM | 001–099 | §4.1 |
| 记忆子类型（Memory subtypes） | MEM | 001–099 | §4.2–§4.7 |
| 工作流（Workflow） | WF | 001–099 | §5 |
| 知识库（Knowledge Base） | KB | 001–099 | §6 |
| MEMORY.md 索引（IDX） | IDX | 001–099 | §7 |
| Scope | SCO | 001–099 | §8 |
| Enforcement | ENF | 001–099 | §8.3、§8.4 |
| 引用（References） | REF | 001–099 | §3.3、§9.6 |
| Pool | POOL | 001–099 | §9 |
| 收件箱（Inbox） | INBOX | 001–099 | §10 |
| 一致性（Consistency） | CONS | 001–099 | §11 |

**分配新码的规则。** 添加校验规则时，在对应分类内取下一个未使用的编号。已弃用的码不得复用；弃用码在本表及变更日志中以 `（已弃用）` 注释标注。

---

## 13. 版本控制与迁移契约

### §13.0 概述

engram 采用 `MAJOR.MINOR` 规范版本（无 PATCH），并对破坏性变更有明确规则。v0.2 是第一个广泛采用的版本，它以具体、有据可查的方式对 v0.1 引入了破坏性变更。§13 确保任何用户都不会丢失数据：迁移契约规定了每个变更字段、自动迁移步骤、缺失必填字段时应用的默认值，以及 6 个月只读兼容窗口——在此期间，v0.1 存储库在用户按自己节奏完成迁移的同时仍可正常使用。

§13 的读者分为两类：

- **正在迁移 v0.1 存储库的用户** — 参见 §13.3（破坏性变更表）和 §13.4（迁移命令契约）。
- **实现 `engram migrate` 的工具作者** — 阅读 §13 全文，重点关注 §13.4 中的幂等性和回滚要求。

`~/.engram/version` 版本文件（§13.2）是存储库基于哪个规范版本写入的权威记录。每个 `engram` CLI 命令在启动时读取该文件，并应用 §13.2 中的规则。

---

### §13.1 语义化版本控制

**engram 规范版本**采用 `MAJOR.MINOR` 格式（如 `0.1`、`0.2`、`1.0`）。由于这是磁盘格式的规范而非库 API，不使用 PATCH 级别——文档澄清和示例添加不会触发任何版本号变更。

**破坏性变更**触发 MAJOR 升级：

- 删除或重命名必填 frontmatter 字段
- 改变现有枚举值的含义（如重命名 scope 标签或 enforcement 级别）
- 重组规范目录布局（如将 `.memory/local/` 移至不同路径）
- 重命名 Memory 子类型、Workflow 生命周期状态或错误码前缀

**附加性变更**触发 MINOR 升级：

- 添加新的可选 frontmatter 字段
- 添加新的 scope 标签、Memory 子类型、错误码、intent 值或事件类型（现有值不受影响）
- 添加新的 CLI 子命令
- 添加新的 pool 传播模式

**非变更**（不触发版本升级）：

- 修正错别字或澄清措辞
- 添加或改进示例
- 添加新的附录章节

**实现版本。** 工具自身的发布版本（如 `engram-cli 0.2.1`）独立遵循语义化版本。`0.2.1` 实现必须符合 `0.2` 规范。补丁位保留用于不改变规范契约的错误修复。

---

### §13.2 `~/.engram/version` 文件

`~/.engram/version` 是一个纯文本文件，包含单行内容：存储库写入时所基于的规范版本。

```
0.2
```

无尾随空格，无需尾随换行，无其他字段。工具必须原子性地写入该文件（先写入临时文件，再重命名）。

**写入规则。** `engram init` 创建 `~/.engram/version`，内容为工具内嵌的规范版本。`engram migrate` 在成功完成后更新该文件。

**读取规则。** 每个 `engram` CLI 命令在启动时读取 `~/.engram/version` 并应用以下逻辑：

| 条件 | 行为 |
|---|---|
| 文件缺失 | 假设为 `0.1`（兼容规则）。每会话发出一次 `W-STR-004`。 |
| 版本与工具内嵌规范匹配 | 正常进行。 |
| 版本早于工具规范 | 发出信息级提示，指向迁移说明。只读操作继续；写入需要迁移（§13.5）。 |
| 版本新于工具规范 | 发出 `W-STR-005`。工具可能无法理解更新的构造；用户应升级工具。 |

**此处分配的警告码：**

| 码 | 严重程度 | 条件 |
|---|---|---|
| `W-STR-004` | 警告 | `~/.engram/version` 文件缺失；假设为 v0.1——运行 `engram migrate --to=0.2` |
| `W-STR-005` | 警告 | `~/.engram/version` 声明的版本新于本工具支持的版本——请升级工具 |

---

### §13.3 v0.1 → v0.2 破坏性变更

下表列举了 v0.2 引入的每一项破坏性变更。"迁移默认值"列说明了当字段缺失时 `engram migrate` 注入的值；"无需操作"表示该变更不需要数据转换。

| # | 变更内容 | v0.1 | v0.2 | 迁移默认值 |
|---|---|---|---|---|
| 1 | Memory 文件位置 | `.memory/*.md`（平铺） | `.memory/local/*.md` | 将所有 `*.md` 移至 `local/*.md` |
| 2 | 共享 pool 路径 | `~/.engram/shared/<name>/` | `~/.engram/pools/<name>/` | 迁移时执行 `mv` |
| 3 | `scope` frontmatter 字段 | 缺失（隐含 local） | 必填 | `scope: project` |
| 4 | feedback 的 `enforcement` | 缺失 | 必填 | `enforcement: default` |
| 5 | `MEMORY.md` 200 行上限 | 强制执行 | 已移除——质量由一致性引擎维护 | 无需操作 |
| 6 | Memory 子类型 | 4 个（`user`、`feedback`、`project`、`reference`） | 6 个（新增 `workflow_ptr`、`agent`） | 现有 4 个不变 |
| 7 | Workflow 作为一等资产 | 不存在 | 必要结构（§5） | 无 v0.1 工作流需迁移 |
| 8 | Knowledge Base 作为一等资产 | 不存在 | 必要结构（§6） | 无 v0.1 知识库需迁移 |
| 9 | `confidence` 字段 | 不存在 | `agent` 类型必填；其他推荐 | 为 `agent` 文件添加空对象 `{}` |
| 10 | Scope 标签 | 不存在 | 五个标签：`org`、`team`、`user`、`project`、`pool` | 设置 `project`；其余为空 |
| 11 | 用户全局目录 | `~/.engram/global/` | `~/.engram/user/` | 迁移时重命名 |
| 12 | 团队与组织 scope | 不存在 | 通过 `team/` 和 `org/` 目录支持 | 初始为空；按需启用 |

第 7、8、12 项无需数据迁移操作——它们引入了 v0.1 中不存在的新资产类型和 scope 级别。第 1–6、9–11 项需要具体的文件系统和 frontmatter 转换，均由 `engram migrate` 处理。

---

### §13.4 `engram migrate --from=v0.1` 契约

**命令格式：**

```
engram migrate --from=v0.1 [--dry-run] [--target=<path>] [--json] [--rollback]
```

**前置条件（任何写入前检查）：**

1. 目标目录包含 `.memory/`（检测到 v0.1 格式）。
2. 工具版本支持 v0.2 规范。
3. v0.1 存储库中无 `E-*` 校验错误（警告可接受）。如有疑问，先运行 `engram validate`。

若任一前置条件不满足，migrate 以代码 1 退出并给出人类可读的说明。不修改任何文件。

**试运行模式（`--dry-run`）：**

将完整迁移报告打印到标准输出。不对文件系统做任何修改。报告列出每个受影响资产的以下信息：

- 当前路径 → 新路径
- 新增的 frontmatter 字段
- 注入的默认值
- 需要用户决策的任何歧义

`--json` 以 JSON 对象格式输出相同报告。若迁移预计成功，退出码为 0；若检测到问题，退出码为 1。

**实际迁移步骤（按序执行）：**

1. 读取 `~/.engram/version`（缺失则暗示 `0.1`）。确认来源为 v0.1。
2. **安全备份。** 将当前 `.memory/` 目录完整复制为 `.memory.pre-v0.2.backup/`。若该复制操作无法完成，则中止整个迁移。
3. 创建 v0.2 目标结构：`.memory/local/`、`.memory/pools/`、`.memory/workflows/`、`.memory/kb/`。
4. 对每个 `.memory/*.md`（v0.1 平铺文件）：
   a. 移动至 `.memory/local/<文件名>`。
   b. 解析 frontmatter。若 `scope` 字段缺失，添加 `scope: project`。
   c. 若 `type: feedback` 且缺少 `enforcement`，添加 `enforcement: default`。
   d. 若 `type: agent` 且缺少 `confidence`，添加 `confidence: {}`。
   e. 保留所有未知 frontmatter 字段（前向兼容规则，§4.1）。
5. 若 `~/.engram/shared/` 存在，移动至 `~/.engram/pools/`。更新所有 `subscribed_at` 引用。
6. 若 `~/.engram/global/` 存在，重命名为 `~/.engram/user/`。
7. 使用 v0.2 层级格式重新生成 `MEMORY.md`（§7）。`<!-- engram:preserve-begin -->` 和 `<!-- engram:preserve-end -->` 标记之间的用户内容原样保留。
8. 将 `~/.engram/version` 写入内容 `0.2`。
9. 向 `~/.engram/journal/migration.jsonl` 追加结构化记录：

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

**幂等性。** 若调用 migrate 时 `~/.engram/version` 已包含 `0.2`，命令打印 `存储库已在 v0.2——无需操作` 并以 0 退出。不重新执行任何迁移步骤。

**回滚。** 若 `.memory.pre-v0.2.backup/` 目录存在，`engram migrate --rollback` 从中恢复：

1. 删除当前 `.memory/`。
2. 将 `.memory.pre-v0.2.backup/` 重命名为 `.memory/`。
3. 将 `~/.engram/version` 写入 `0.1`（若之前不存在则删除该文件）。

回滚是一次性的应急手段。回滚后备份目录即被消耗；重新迁移前请再次运行试运行。

**此处分配的错误码：**

| 码 | 严重程度 | 条件 |
|---|---|---|
| `E-STR-005` | 错误 | 尝试向 v0.1 存储库写入；请先迁移 |
| `E-STR-006` | 错误 | v0.1 兼容性已过期（超过 6 个月）；需要迁移 |

---

### §13.5 6 个月兼容窗口

在 v0.2 发布日期（记录在工具内嵌元数据的 `release_date` 字段中）起的 6 个月内，v0.1 格式存储库继续以**只读模式**工作：

**每次只读操作发出的警告：**

| 码 | 严重程度 | 条件 |
|---|---|---|
| `W-STR-003` | 警告 | `~/.engram/version` 主版本不匹配：存储库为 v0.1，工具目标为 v0.2 |
| `W-STR-006` | 警告 | 兼容模式已激活：v0.1 存储库可读，但写入已被阻止——运行 `engram migrate --from=v0.1` |

**兼容窗口内可正常工作的只读操作：**

- `engram memory read`、`engram memory search` — 带警告继续
- `engram review` — 带警告继续
- `engram validate` — 继续执行；将 v0.1 特有问题报告为警告而非错误

**被阻止的写入操作：**

- `engram memory add`、`engram memory update`、`engram memory delete` — 以 `E-STR-005` 退出 1
- 在现有 v0.1 存储库中执行 `engram init` — 被阻止；用户必须先迁移

**过期后的行为。** 兼容窗口到期后，工具拒绝对 v0.1 存储库的所有操作（读和写）：

```
E-STR-006 v0.1 兼容性已到期——运行 `engram migrate --from=v0.1` 进行升级
```

`engram migrate` 本身无时间限制。用户可以在任何时间迁移 v0.1 存储库，不受兼容窗口影响。

**选择提前退出。** 希望立即获得过期后行为的用户（如强制团队完成迁移）可设置：

```
engram config set compat.v0.1=expired
```

这将立即对所有 v0.1 存储库激活 `E-STR-006`，无论发布日期如何。

---

### §13.6 从其他系统迁移

除 v0.1 外，`engram migrate --from=<source>` 还支持以下来源。每种来源将外部数据映射为 v0.2 格式，并在无法自动推断时（scope、enforcement 默认值）提示用户做出决策。

| 来源标志 | 外部系统 | 映射摘要 |
|---|---|---|
| `--from=claude-code` | Claude Code 记忆系统 | 读取 `~/.claude/projects/<slug>/memory/*.md`；映射为 v0.2 Memory 格式；提示 scope 和 enforcement 默认值 |
| `--from=chatgpt` | ChatGPT Memories 导出（JSON） | 解析 ChatGPT JSON 导出；创建 `type: user` 的 `user_*.md` Memory 条目 |
| `--from=mem0` | mem0 数据库导出 | 读取 mem0 导出；通过启发式方法映射为 `user`、`project` 或 `reference` 子类型；对歧义条目提示用户 |
| `--from=obsidian` | Obsidian 日记笔记 | 交互式：用户选择哪些笔记成为 Memory 条目；Obsidian 标签映射为 `tags:` |
| `--from=letta` | Letta / MemGPT 归档记忆 | `core_memory` 块 → `user` 子类型；`archival` 块 → `reference` 子类型 |
| `--from=mempalace` | MemPalace 存储 | Drawers → `reference` 记忆；Wings → `tags:`；Closets 仅用于元数据 |
| `--from=markdown --dir=<path>` | 通用 Markdown 目录 | 扫描 `<path>`；将每个 `.md` 视为 Memory 条目；使用目录结构推断 `tags:` |

每种来源的详细字段映射规则记录在 `docs/migrate/<source>.md` 中（不属于本规范）。此处保证的契约为：

1. 不删除或修改任何输入文件；所有写入均进入 engram 存储库。
2. 与现有存储库条目冲突时，migrate 提示而非覆盖。
3. 试运行（`--dry-run`）始终可用且始终安全。
4. 迁移日志记录（§13.4，步骤 9）写入时 `from_version` 设置为来源名称。

---

### §13.7 未来迁移兼容性

管理所有未来规范版本迁移的设计原则：

1. **记录每个破坏性变更。** 每次 MAJOR 升级的发版说明必须以 §13.3 风格枚举每一项变更。
2. **至少支持两个主版本之前的自动迁移。** 在 v1.0 发布时，`engram migrate --from=v0.1` 和 `engram migrate --from=v0.2` 必须同时受支持。
3. **6 个月可读但有警告模式。** 每次主版本迁移均附带 §13.5 中定义的相同兼容窗口。
4. **绝不销毁用户数据。** 每次实际迁移在任何写入之前创建 `.pre-v{N}.backup/` 快照。回滚路径必须始终存在。
5. **幂等性是必要条件。** 对已迁移的存储库运行两次 migrate 必须是空操作。
6. **附加性默认值。** 引入新必填字段时，其迁移默认值必须是最不令人意外的值——即如果该字段在 v0.1 中就存在，v0.1 作者会选择的值。

版本文件格式（`~/.engram/version`）本身在所有未来版本中保持稳定——单行规范版本字符串。若此契约将来必须变更，则构成 MAJOR 升级。

---

## 14. 附录

### §14.0 概述

本章包含三个参考附录，作为 §0 至 §13 规范性说明的补充：

- **附录 A** 提供了面向单个开发者真实项目的完整可运行最小可行 engram 存储库示例。每种资产类型均有体现，且该存储库可通过 `engram validate` 的清洁验证。
- **附录 B** 引用了塑造 v0.2 设计的所有外部项目、论文和理念，按其最主要影响的章节组织。
- **附录C** 复现了从早期访问设计讨论中提炼的十个常见问题，并给出了交叉引用相关规范章节的简洁解答。

这些附录为参考资料，非规范性要求。§14 中的任何内容不改变 §0–§13 中定义的验证规则或磁盘格式契约。

---

### §14.A — 附录 A：最小可行 engram 存储库

面向在 `acme-checkout-service` 项目上独立工作、订阅了一个团队池的单一开发者的完整 `.memory/` 目录示例。每种资产类型均存在。该存储库可通过 `engram validate` 的清洁验证。

**场景：** 独立开发者，`acme-checkout-service` 项目，已订阅共享的 `design-system` 池。

#### 文件树

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

#### 文件内容

**`.memory/MEMORY.md`**

```markdown
---
engram_version: "0.2"
generated_at: "2026-04-18T09:00:00Z"
scope: project
---

# 记忆索引 — acme-checkout-service

> 本项目所有 engram 资产的落地索引。
> 首先加载此文件；跟随引用加载各个资产。

## 用户身份

- [开发者档案](local/user_developer_profile.md) — 角色、技能、偏好技术栈

## 反馈（规则与偏好）

- [推送前需确认](local/feedback_push_requires_confirmation.md) — `enforcement: hint` — `git push` 前务必确认

## 项目状态

- [当前 Sprint](local/project_current_sprint.md) — Sprint 7，到期 2026-04-30

## 参考资料

- [内部 API 文档](local/reference_internal_api_docs.md) — acme 内部服务目录 URL

## 工作流指针

- [发布检查清单](local/workflow_ptr_release_checklist.md) → `workflows/release-checklist/`

## Agent 学习内容

- [提交信息风格](local/agent_commit_message_style.md) — 规范式提交，从历史中推断

## 池

- [design-system](pools/design-system/) — 团队池，`subscribed_at: user`，`auto-sync`

## 知识库

- [acme-checkout 架构](kb/acme-checkout-architecture/) — 服务拓扑、数据流、ADR 索引
```

---

**`.memory/pools.toml`**

```toml
[pools.design-system]
path = "~/.engram/pools/design-system/current/"
subscribed_at = "user"
mode = "auto-sync"
subscribed_on = "2026-03-01"
description = "共享设计系统令牌与组件规范"
```

---

**`.memory/local/user_developer_profile.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: user
scope: user
title: "开发者档案"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-18T09:00:00Z"
tags: [identity, skills]
---

# 开发者档案

**角色：** 全栈工程师，主攻后端（Go、TypeScript）。
**当前团队：** 结账平台组。
**偏好工作流：** TDD、小型 PR、规范式提交。
**日常工具：** Claude Code、neovim、tmux、gh CLI。
**时区：** UTC+8。
```

---

**`.memory/local/feedback_push_requires_confirmation.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: feedback
scope: user
title: "推送前需明确确认"
created_at: "2026-03-15T11:00:00Z"
updated_at: "2026-04-10T08:30:00Z"
enforcement: hint
tags: [git, safety]
confidence_score: 0.95
validated_count: 12
contradicted_count: 0
---

# 推送前需明确确认

**规则：** 在未与开发者确认前，绝不执行 `git push`（或任何向远程发送提交的变体操作）。

**原因：** 向 `acme-checkout-service` 的 `main` 分支推送会触发预发布部署。在热修复窗口期间意外推送可能阻塞其他团队。

**应用方式：** 在任何 `git push` 之前，输出即将推送的提交摘要，并询问"确认推送？"，等待明确的"是"后再继续。

**例外：** `git push --dry-run` 始终安全，无需确认。
```

---

**`.memory/local/project_current_sprint.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: project
scope: project
title: "当前 Sprint — Sprint 7"
created_at: "2026-04-14T09:00:00Z"
updated_at: "2026-04-14T09:00:00Z"
expires: "2026-04-30T23:59:59Z"
tags: [sprint, planning]
---

# Sprint 7（2026-04-14 至 2026-04-30）

**目标：** 交付 cart-service v2 集成，关闭 P0 延迟回归问题（issue #412）。

**当前工单：**
- CHECKOUT-881 — 集成 cart-service v2 API
- CHECKOUT-412 — P0：将结账延迟 p99 从 420 ms 降至 < 200 ms
- CHECKOUT-903 — cart-service 迁移后更新内部 API 文档

**本 Sprint 范围外：** 支付提供商重试逻辑（延至 Sprint 8）。
```

---

**`.memory/local/reference_internal_api_docs.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: reference
scope: project
title: "内部 API 文档"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-01T14:00:00Z"
tags: [api, reference, internal]
url: "https://internal.acme.example/service-catalog/checkout"
---

# 内部 API 文档

**URL：** https://internal.acme.example/service-catalog/checkout

**访问：** 需 VPN + 企业 SSO。通过 `acme-cli login` 进行基于令牌的身份验证。

**背景：** `acme-checkout-service` 消费的所有上游服务契约的权威来源。包括 cart-service、payment-service 和 identity-service 的 API Schema。每次服务发布时更新；在假设 schema 稳定性之前请检查变更日志。
```

---

**`.memory/local/workflow_ptr_release_checklist.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: workflow_ptr
scope: project
title: "发布检查清单工作流指针"
created_at: "2026-03-20T09:00:00Z"
updated_at: "2026-04-01T09:00:00Z"
workflow_ref: "workflows/release-checklist/"
tags: [release, workflow]
---

# 发布检查清单

指向位于 `workflows/release-checklist/` 的 `release-checklist` 工作流资产。

**何时调用：** 在 `acme-checkout-service` 上打任何发布标签之前。
通过 `engram workflow run release-checklist` 运行，或打开 `workflow.md` 手动执行步骤。
```

---

**`.memory/local/agent_commit_message_style.md`**

```markdown
---
engram_version: "0.2"
type: memory
subtype: agent
scope: project
title: "提交信息风格"
created_at: "2026-04-05T16:00:00Z"
updated_at: "2026-04-18T09:00:00Z"
source: agent-learned
confidence_score: 0.88
validated_count: 34
contradicted_count: 2
tags: [git, commits, style]
---

# 提交信息风格

**格式：** 规范式提交（`type(scope): subject`）。

**本仓库使用的类型：** `feat`、`fix`、`chore`、`refactor`、`test`、`docs`、`perf`。

**主题行规则：**
- 冒号后小写。
- 祈使语气（"add X"，而非 "added X"）。
- 不加尾随句号。
- 最多 72 个字符。

**正文（如有）：** 72 字符换行。主题行后留空行。描述*为何*，而非*做了什么*。

**使用的尾注：** `Fixes: #<issue>`、`Co-authored-by:`。

*从本仓库近期历史的 34 次提交中推断。*
```

---

**`.memory/workflows/release-checklist/workflow.md`**

```markdown
---
engram_version: "0.2"
type: workflow
title: "发布检查清单"
version: "1.0.0"
created_at: "2026-03-20T09:00:00Z"
updated_at: "2026-04-10T11:00:00Z"
spine: "spine.sh"
tags: [release, checklist]
---

# 发布检查清单

## 用途

验证 `acme-checkout-service` 是否已准备好打标签和部署。捕捉最常见的发布前问题：缺失迁移、过期的 API 文档、红色 CI 以及缺少变更日志条目。

## 何时使用

在打任何发布标签（`git tag vX.Y.Z`）之前运行此工作流。可安全多次运行；每次运行均为幂等操作。

## 预期结果

成功时：所有检查通过，发布标签已应用，metrics.yaml 已更新。
失败时：工作流在第一个失败检查处退出，并输出修复建议。
```

---

**`.memory/workflows/release-checklist/spine.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== 发布检查清单：acme-checkout-service ==="

echo "[1/5] 检查 CI 状态..."
gh run list --limit 1 --json conclusion -q '.[0].conclusion' | grep -q "success"

echo "[2/5] 检查未提交变更..."
git diff --quiet && git diff --staged --quiet

echo "[3/5] 验证 CHANGELOG.md 已更新..."
grep -q "## \[Unreleased\]" CHANGELOG.md

echo "[4/5] 运行单元测试..."
go test ./... -count=1 -timeout 60s

echo "[5/5] 确认迁移文件存在..."
ls db/migrations/*.sql 2>/dev/null | wc -l | grep -qv "^0$"

echo "=== 所有检查通过。可以发布。 ==="
```

---

**`.memory/workflows/release-checklist/fixtures/success-case.yaml`**

```yaml
# success-case.yaml — 发布检查清单的顺利路径夹具
fixture: success-case
description: "所有发布前条件满足"
preconditions:
  ci_status: success
  uncommitted_changes: false
  changelog_updated: true
  tests_pass: true
  migrations_present: true
expected_outcome:
  exit_code: 0
  final_message: "所有检查通过。可以发布。"
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
# failure-case.yaml — CI 红色失败夹具
fixture: failure-case
description: "CI 为红色；工作流须在步骤 1 退出"
preconditions:
  ci_status: failure
expected_outcome:
  exit_code: 1
  failed_at_step: 1
  hint: "在打发布标签前修复失败的 CI 运行。"
```

---

**`.memory/workflows/release-checklist/metrics.yaml`**

```yaml
# metrics.yaml — release-checklist 工作流的结果追踪
workflow: release-checklist
last_run: "2026-04-17T14:22:00Z"
total_runs: 8
successful_runs: 7
failed_runs: 1
last_failure_step: 3
last_failure_reason: "CHANGELOG.md 未更新"
average_duration_seconds: 42
mastery_score: 0.875
```

---

**`.memory/kb/acme-checkout-architecture/README.md`**

```markdown
---
engram_version: "0.2"
type: kb
title: "acme-checkout 架构"
created_at: "2026-03-01T10:00:00Z"
updated_at: "2026-04-15T12:00:00Z"
compiled_at: "2026-04-15T12:30:00Z"
tags: [architecture, checkout, acme]
---

# acme-checkout 架构

**摘要：** `acme-checkout-service` 的服务拓扑、数据流及关键设计决策。涵盖与 cart-service、payment-service 和 identity-service 的集成点。

## 章节

1. [概述](01-overview.md) — 服务边界、主要流程、部署拓扑
```

---

**`.memory/kb/acme-checkout-architecture/_compiled.md`**

```markdown
<!-- 由 engram compile 自动生成 — 请勿手动编辑。
     来源：kb/acme-checkout-architecture/
     编译时间：2026-04-15T12:30:00Z
     编译器：engram/0.2 -->

# acme-checkout 架构 — 编译摘要

## 概述

`acme-checkout-service` 是结账交易生命周期的唯一所有者。它编排 cart-service（商品验证 + 定价）、payment-service（收款捕获）和 identity-service（买家身份验证）。该服务以单一 Go 二进制文件形式部署在内部 gRPC 网关之后。

**关键数据流：**
1. 买家发起结账 → identity-service 验证会话令牌。
2. 从 cart-service v2 API 获取购物车内容（Sprint 7 中从 v1 迁移）。
3. 通过 payment-service 捕获付款；幂等键 = `order_id`。
4. 确认事件发布到 `checkout.completed` Kafka 主题。

*本摘要由此 KB 中的章节文件综合而成。有关源 ADR 和图表，请参阅各章节文件。*
```

---

**`.engram/version`**

```
0.2
```

---

**`CLAUDE.md`**（适配器）

```markdown
# engram 适配器 — acme-checkout-service

本项目使用 engram v0.2 记忆系统。

**记忆存储：** `.memory/MEMORY.md`

开始新会话时：
1. 读取 `.memory/MEMORY.md` 加载完整资产索引。
2. 加载与当前任务相关的资产（跟随 MEMORY.md 中的引用）。
3. 无一例外地遵守 `enforcement: mandatory` 规则；
   除非有特定理由，否则应用 `enforcement: default` 规则；
   将 `enforcement: hint` 规则视为建议。

验证方式：`engram validate`（需要 engram CLI ≥ 0.2）。
```

---

**该存储库验证清洁。运行 `engram validate` 以确认零错误。**

---

### §14.B — 附录 B：设计依据

塑造 engram v0.2 设计的所有外部项目、论文和理念，按各来源最主要影响的章节组织。

| 来源 | 类型 | 对 engram v0.2 的影响 | 章节 |
|---|---|---|---|
| Karpathy，"LLM Wiki as Personal Knowledge Base"（gist） | 方法论 | 知识库类：人工编写章节、LLM 编译摘要；写侧综合规范 | §6 |
| Karpathy，`autoresearch` | 开源系统 | 工作流自动学习 8 规范评估循环；`evolution.tsv` 仅追加历史；阶段门；简洁性标准 | §5，DESIGN §5.3 |
| MemPalace（`milla-jovovich/mempalace`） | 开源系统 | 混合检索（BM25 + 向量融合 + 时间增强 + 两阶段重排序）；4 层唤醒栈；`_compile_state.toml` 模式；后端抽象；PreCompact + Stop 钩子模式；BENCHMARKS.md 规范 | §7，§9，DESIGN §5.1 |
| Darwin.skill（`alchaincyf/darwin-skill`） | 开源系统 | 自动学习棘轮机制（git 原生提交 + 还原）；双重评估（静态 60 + 性能 40）；独立评估 agent；阶段门检查点 | §5，DESIGN §5.3 |
| Nuwa.skill（`alchaincyf/nuwa-skill`） | 开源系统 | 诚实限制声明（`limitations:` 前言字段） | §4.1 |
| "Experience-as-Code"（Agent Factory 2026-03 arXiv） | 论文 | 工作流 = 文档 + 可执行脊柱，而非纯散文；可执行脊柱作为一等公民 | §5 |
| evo-memory（DeepMind 2025） | 论文 | 搜索 → 综合 → 演化生命周期；ReMem 行动-思考-精炼循环；证据驱动的置信度评分 | §4.8，§11，DESIGN §5.2/5.3 |
| MemoryBank（arXiv 2305.10250） | 论文 | Ebbinghaus 遗忘曲线启发 `staleness_penalty` 公式；调整为置信度驱动的保留而非纯时间衰减 | §4.8，§11 |
| MemGPT / Letta | 论文 + 系统 | 记忆作为结构化分页上下文；启发了分层 MEMORY.md 设计，但 engram 保持文件原生，无分页抽象 | §7 |
| Claude Code 记忆系统 | 前艺术 | 直接前身；engram v0.1 是 Claude Code 技能；v0.2 泛化为 LLM 无关格式 | §13（迁移），§3 |
| `skills.sh` 生态系统（`npx skills add <owner>/<repo>`） | 惯例 | 剧本安装 URL 方案：`engram playbook install github:<owner>/<repo>` | §4（引用），§9，DESIGN §4 |

**致谢**

engram v0.2 直接借鉴了他人率先验证的理念。上述作品的作者应获得这些洞见的主要荣誉；任何改编中的错误均由我们负责。engram 是经过充分验证的理念的组合，旨在使持久化 LLM 记忆真正可移植且能自我维护。

---

### §14.C — 附录 C：常见问题

从早期访问设计讨论中提炼的十个问题。

1. **Q：为何使用 Markdown 文件而非向量数据库或专用记忆服务？**

   A：可移植性胜过巧妙性。Markdown 适用于任何编辑器、git、grep 和 Obsidian。嵌入是缓存（见 DESIGN §5.1）；真实来源是用户拥有的文本文件。如果 engram 明天消失，Markdown 存储库无需任何专用工具仍可完全使用。

2. **Q：为何设置 6 种记忆子类型而不是仅一种"记忆"类型？**

   A：各子类型的认识论状态不同。用户身份、人工编写的规则、LLM 学习的启发式方法、持续决策、外部指针和工作流指针都需要不同的生命周期、默认置信度值和审查节奏。单一的"记忆"类型会消除这些区别。§4.2–§4.7 详细介绍了每种子类型。

3. **Q：为何范围有两个轴（层级 + 订阅）？**

   A：如 v0.1 所做的那样将它们折叠为单一线性维度，会在知识需要跨团队流动而不隐含成员资格时造成尴尬的选择。层级模拟"你属于谁"；订阅模拟"你选择加入什么"。它们是正交的，将其视为正交可简化每条冲突解决规则。§8 详细介绍了双轴模型。

4. **Q：engram 会自动删除旧记忆吗？**

   A：不会。删除始终需要显式的操作者操作。一致性引擎提议；它从不变更资产。资产在物理删除前通过 `archive/` 路径经历六个月的保留底线。§11.6 列举了一致性引擎的非目标。

5. **Q：记忆存储库的最大大小是多少？**

   A：没有上限。质量由一致性引擎（§11）和自适应信号（见 docs/glossary.md 中的 `staleness_penalty`、`confidence_score`）维护，而非大小限制。资产类型因功能不同，而非长度不同。

6. **Q：engram 如何处理上下文窗口较小的 LLM（例如 8K token 的模型）？**

   A：相关性门（DESIGN §5.1）选择适合上下文预算的资产子集。MEMORY.md 设计为保持在 900 token 以内。小上下文模型获得相同质量的信号，只是切片更小。无需特殊配置。

7. **Q：engram 可以完全离线工作吗？**

   A：是的，完全可以。所有资产均为本地文件。池同步仅在推送或拉取时需要网络访问。CLI 没有强制性网络依赖；`engram validate`、`engram review` 以及所有本地读写操作均无需网络连接即可工作。

8. **Q：engram 与 MemPalace、mem0 和 Letta 相比如何？**

   A：MemPalace 存储逐字会话记录；engram 存储经过筛选的结构化资产。mem0 是托管服务；engram 是本地优先且 LLM 无关的。Letta 将记忆视为分页虚拟内存；engram 将其视为用户拥有的版本化文件系统。§14.B 从技术和影响层面进行了比较。

9. **Q：我可以导入现有的 Claude Code / ChatGPT / mem0 记忆吗？**

   A：可以。`engram migrate --from=<source>` 支持 Claude Code、ChatGPT 导出、mem0、Obsidian、Letta、MemPalace 和通用 Markdown 目录。迁移期间不删除或修改任何输入文件。§13.6 记录了每种来源的字段级映射。

10. **Q：engram 已准备好用于生产环境吗？**

    A：v0.2 是草稿规范；参考实现正在积极开发中。SPEC 稳定到足以基于其构建——在 v1.0 之前预计不会有破坏性变更。生产就绪度跟踪里程碑 M4（见 TASKS.md）。

---

**SPEC v0.2 草稿完成。** §0 至 §14 章节涵盖了 engram 记忆系统的完整磁盘格式契约、验证规则和迁移路径。配套文档：

- [`DESIGN.md`](DESIGN.md) — 5 层实现架构（数据 / 控制 / 智能 / 访问 / 观测）
- [`METHODOLOGY.md`](METHODOLOGY.md) — LLM 应如何编写、演化和退役资产
- [`TASKS.md`](TASKS.md) — 里程碑和实现任务板
- [`docs/glossary.md`](docs/glossary.md) — 权威术语定义

如需更新和修正，请参阅 [`docs/HISTORY.md`](docs/HISTORY.md)（将于首次发布时创建）。
