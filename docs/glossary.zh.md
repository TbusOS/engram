[English](glossary.md) · [中文](glossary.zh.md)

# engram 术语表(v0.2)

> **术语稳定锚点。** v0.2 每份文档(`SPEC.md`、`DESIGN.md`、`TASKS.md`、`README.md`、`METHODOLOGY.md`、`CONTRIBUTING.md`,以及每个 adapter / tutorial 文件)都**必须**使用本表里的中文术语。英文版见 [`glossary.md`](glossary.md)。不要在文档中途临时发明新译法。如果需要新术语,先在这里加一行,然后再用。

为什么重要:engram 有三类读者(LLM、人、其他工具作者)。术语漂移会让 LLM 失命中、让人看不懂、让工具作者写错接口。这张表足够小,全体项目参与者能记住;足够大,覆盖所有 v0.2 设计决策。

**最后更新:** 2026-04-18(v0.2 重写立项)

---

## 1. 架构分层

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| Layer 1 — Data | 第 1 层 数据层 | 磁盘格式;永远不直接和 LLM 对话 |
| Layer 2 — Control | 第 2 层 控制层 | `engram` CLI 家族;LLM 可选 |
| Layer 3 — Intelligence | 第 3 层 智能层 | 相关性 / 一致性 / 自学习 / 演化 / 传信 / 智慧指标;均可选、均走 append-only journal |
| Layer 4 — Access | 第 4 层 接入层 | 适配器 / MCP / prompt pack / SDK —— LLM 与 store 的通道 |
| Layer 5 — Observation | 第 5 层 观察层 | 面向人的 `engram-web` UI |

## 2. 资产类别

按**函数**区分(资产是什么),不按尺寸。三类都**不设硬上限** —— 系统用自适应信号(§16)代替固定阈值。

| English | 中文 | 函数 | 必备结构 |
|---------|------|------|---------|
| Memory | 记忆 | 一个**原子断言** —— 能独立被 supersede 的事实 / 规则 / 偏好 / 指针 | 一个 `.md` + frontmatter + body |
| Workflow | 工作流 | 一个**可执行过程** —— 有 spine 能跑 | `workflow.md` + `spine.*` + `fixtures/` + `metrics.yaml` + `rev/` |
| Knowledge Base (KB) | 知识库 | 一块**领域参考** —— 人会专门来读的多章节文档 | `README.md` + 章节 + `assets/` + `_compiled.md`(LLM 编译的摘要) |
| Playbook | 剧本 | 可安装的打包单位:一个或多个 Workflow + KB 文章 + 种子 Memory,通过 `engram playbook publish` 发布、`engram playbook install github:<owner>/<repo>` 安装 |

## 3. Memory 子类型(SPEC §4)

共 6 种。子类型表达的是**认识论状态**(谁写的 / 怎么知道它为真),和 `scope` 正交。

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| `user` | 用户型 | 关于人的事实 —— v0.1 保留 |
| `feedback` | 反馈型 | LLM 必须遵守的规则,**人写的** —— v0.1 保留,v0.2 新增必填 `enforcement` |
| `project` | 项目型 | 在做的工作事实,只用绝对日期 —— v0.1 保留 |
| `reference` | 引用型 | 指向外部系统的指针 —— v0.1 保留 |
| `workflow_ptr` | 工作流指针 | 指向 `workflows/<name>/` 的轻量条目;LLM 在 MEMORY.md 看到这个,不是整篇 workflow 文档 |
| `agent` | 代理元指令 | LLM 自己学到的启发式。和 `feedback` 区别:**来源是 LLM 自己,不是人** —— 默认置信度更低,consistency 引擎审查更严 |

> **注:** v0.2 早期草稿曾有第七种子类型 `team`。后来被取消,因为"团队硬约定"完全可以用 `feedback` + `scope: team` + `enforcement: mandatory` 表达。子类型与 scope 保持正交。

## 4. Scope 模型(SPEC §8)

两个正交轴,共五个标签。

### 4a. 归属轴(hierarchy,由 membership 决定,自动继承)

4 级,从普遍到具体。冲突解决:同 `enforcement` 级别下,越具体越赢(`project > user > team > org`)。

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| `org` | 组织级 | `~/.engram/org/<name>/`;git 同步;公司 / 组织硬约束。用户属于 0 或 1 个 org。权威最高 |
| `team` | 团队级 | `~/.engram/team/<name>/`;git 同步;团队 / 部门约定。用户可属于多个 team |
| `user` | 用户级 | `~/.engram/user/`;本人跨项目基线;不共享 |
| `project` | 项目级 | `<project>/.memory/local/`;仅当前项目;最具体 |

### 4b. 订阅轴(pool,正交)

pool 内容按订阅方声明的 `subscribed_at` 附身到对应归属层级参与冲突解决,**不是固定"一个层级"**。

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| `pool` | 池(订阅) | `~/.engram/pools/<name>/`;按主题共享,订阅者显式加入。每个订阅方在 pools.toml 里声明 `subscribed_at: org \| team \| user \| project`,决定此 pool 对该订阅方的有效归属层级 |

### 4c. 订阅解析

| `subscribed_at` | 含义 |
|-----------------|------|
| `org` | pool 对组织内所有项目表现为 org 级内容 |
| `team` | pool 对该团队所有项目表现为 team 级内容 |
| `user` | pool 对该用户所有项目表现为 user 级内容 |
| `project` | pool 仅对该项目表现为 project 级内容 |

## 5. Enforcement 级别

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| mandatory | 强制级 | 不可被下级 scope 覆盖;`engram validate` 报错 |
| default | 默认级 | 可覆盖,但覆盖方必须声明 `overrides: <id>` |
| hint | 建议级 | 可自由覆盖,无需说明 |

## 6. 智能层组件(DESIGN §5)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| Relevance Gate | 相关性闸门 | 从候选资产里排序 + 过滤进上下文预算。智能层唯一会改变 LLM 可见状态的组件 |
| Consistency Engine | 一致性引擎 | 四层扫描检测七类冲突。只建议,永不自动 mutate |
| Autolearn Engine | 自学习引擎 | Workflow 级演化循环;纪律来自 Karpathy 的 `autoresearch` |
| Evolve Engine | 演化引擎 | Memory 级演化(ReMem action-think-refine);月度节奏;只生成 proposal |
| Inter-Repo Messenger | 跨仓传信器 | 仓库之间点对点 inbox;和 pool 传播互补 |
| Wisdom Metrics | 智慧指标 | 四组定量曲线,证明系统在变聪明 |

## 7. 一致性冲突七类(SPEC §11)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| factual-conflict | 事实冲突 | 两条资产对同一事实陈述不一致 |
| rule-conflict | 规则冲突 | 两条 `feedback`/`team` 要求相反动作 |
| reference-rot | 引用失效 | `reference` 指向的资源已不存在 |
| workflow-decay | 工作流衰变 | workflow spine 调用的工具 / 路径不在了 |
| time-expired | 时间过期 | `expires:` 日期已过但资产仍被引用 |
| silent-override | 静默覆盖 | 新资产事实上替代了旧的,但未声明 `supersedes:` |
| topic-divergence | 同题分歧 | 同主题的多条资产结论不一致 |

## 8. 记忆生命周期状态

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| draft | 草稿 | 已写但未经校验 / 未入索引 |
| active | 活跃 | 当前正在影响 LLM 行为 |
| stable | 稳定 | 已反复验证;短期不会变 |
| deprecated | 待退 | 标记为将移除;仍可读,review 中会高亮 |
| archived | 已归档 | 移到 `~/.engram/archive/`;可取回但不再加载 |
| tombstoned | 已删除 | journal 中仅保留 ID;归档期满后物理文件被删 |

## 9. 置信度 & 证据相关

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| validated_count | 验证次数 | LLM 据此行动且现实印证为对的次数 |
| contradicted_count | 证伪次数 | 被现实证伪的次数 |
| last_validated | 最近验证 | 最后一次正向结果的 ISO 8601 时间戳 |
| usage_count | 调用次数 | 被加载进某个 LLM 上下文的次数 |
| confidence_score | 置信分 | `(validated - 2*contradicted - staleness_penalty) / max(1, total_events)` |
| staleness_penalty | 陈旧惩罚 | 未再验证时:0(<90 天)/ 0.3(90–365 天)/ 0.7(>365 天) |
| outcome event | 结果事件 | journal 里一行,记录成功 / 失败 / 矛盾 |
| evidence-driven | 证据驱动 | 决策来自记录的结果,不凭感觉 |

## 10. 传播与 inbox 相关(SPEC §9、§10)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| propagation | 传播 | pool 层更新向订阅者的扩散 |
| auto-sync | 自动同步 | 订阅者的 symlink 自动跟 pool 的 `current` 版本 |
| notify | 通知式 | 订阅者收到 journal 条目,自选 accept / reject / override |
| pinned | 钉版 | 订阅者锁定到某个 revision;不自动升级 |
| subscriber | 订阅者 | 消费某个 pool 的项目 |
| pool maintainer | 池维护者 | 对某 pool 有写权(常由 Git CODEOWNERS 落实) |
| inbox | 收件箱 | `~/.engram/inbox/<repo-id>/`;跨仓点对点消息 |
| intent | 意图 | inbox 消息类别:`bug-report` / `api-change` / `question` / `update-notify` / `task` |
| acknowledged | 已确认 | 接收方 LLM 读到消息并接手 |
| resolved | 已解决 | 接收方已处理;发送方下次启动会收到反向通知 |

## 11. 接入路径(DESIGN §6)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| adapter | 适配器 | 每个工具一份的 prompt 模板:`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`.cursor/rules`、`system_prompt.txt` |
| MCP server | MCP 服务 | `engram mcp serve`;无状态;暴露类型化工具 |
| prompt pack | 提示包 | `engram context pack` 输出的单文件上下文,面向本地 / 小模型 / 离线 |
| SDK | SDK | Python `engram` 和 TypeScript `@engram/sdk`,面向自写 agent |
| context budget | 上下文预算 | Relevance Gate 必须塞进的 token 上限 |

## 12. Web UI 页面(DESIGN §7)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| Dashboard | 总览面板 | 顶层漏斗:计数、智慧指标 sparkline、注意项 |
| Graph | 知识图谱 | D3 力导向图:资产 + 引用 + 订阅关系 |
| Memory Detail | 记忆详情 | frontmatter + body 编辑;入 / 出引用;git blame 时间线 |
| Workflow Detail | 工作流详情 | 文档 + spine 并排;历史 metric chart;自学习控制 |
| KB Article | 知识文章 | 源文 + `_compiled.md` 并排 |
| Pool Manager | 池管理 | 池 × 订阅者对照表;传播界面 |
| Project Overview | 项目总览 | 本机所有 engram 项目;智慧指标对比 |
| Context Preview | 上下文预览 | 模拟任意任务 + 任意模型,看 LLM 到底会加载什么 |
| Autolearn Console | 自学习控制台 | 实时 `evolution.tsv` tail;start/pause;历史记录 |
| Inbox | 收件箱 | 跨仓消息视图;send / read / resolve 界面 |

## 13. CLI 命令族(DESIGN §4)

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| `engram init` | 初始化 | 建 `.memory/`,注入种子、适配器、订阅 |
| `engram memory` | 记忆 | Memory 资产 CRUD:`add` / `list` / `read` / `update` / `archive` / `search` |
| `engram workflow` | 工作流 | `add` / `run` / `revise` / `promote` / `rollback` / `autolearn` |
| `engram kb` | 知识库 | `new-article` / `compile` / `list` / `read` |
| `engram pool` | 池 | `create` / `list` / `subscribe` / `unsubscribe` / `publish` / `propagate` |
| `engram team` | 团队 | `join` / `sync` / `publish` / `status` |
| `engram inbox` | 收件箱 | `list` / `send` / `read` / `acknowledge` / `resolve` / `reject` |
| `engram consistency` | 一致性 | `scan` / `report` / `resolve <id>` |
| `engram context` | 上下文 | `pack` / `preview` |
| `engram mcp` | MCP | `serve [--transport=stdio|sse]` |
| `engram web` | Web | `serve` / `open` |
| `engram playbook` | 剧本 | `pack` / `install` / `uninstall` / `publish` |
| `engram migrate` | 迁移 | `--from=v0.1 \| claude-code \| chatgpt \| mem0 \| obsidian \| letta` |
| `engram review` | 健康审查 | 聚合 consistency / propagation / inbox 问题 |
| `engram validate` | 校验 | 结构 + 语义校验,CI 友好 exit code |
| `engram snapshot` | 快照 | tarball + 校验和,创建 / 恢复 |
| `engram export` | 导出 | 导出 markdown / prompt / JSON 给外部工具 |
| `engram wisdom report` | 智慧报告 | 打印四组指标曲线 |

## 14. 核心哲学口号

| English | 中文 | 说明 / 译法原因 |
|---------|------|----------------|
| no auto-delete | 永不自动删 | 删除走 `archive/`,保留期 ≥ 6 个月 |
| no capacity cap | 无容量上限 | 磁盘便宜;质量靠一致性引擎维护,不靠裁剪 |
| LLM-first | LLM 优先 | 主读者是任何 LLM;人的体验是第二优先(但不是事后补) |
| data over tool | 数据高于工具 | markdown store 比 engram 本身活得长 |
| portability > cleverness | 可移植 > 花哨 | 乏味的 markdown 在十年尺度上赢过专有格式 |
| quality over quantity | 质量优于数量 | 一百条精炼记忆胜过一千条噪声 |
| evidence-driven evolution | 证据驱动演化 | 置信度而非直觉决定何时让一条记忆退役 |

## 15. 设计先验(引用缩写)

下列名字在设计讨论中反复出现;文档里使用短形式,第一次提及时给 canonical 链接。

| 短名 | 全称 | Canonical 位置 |
|------|------|----------------|
| autoresearch | Karpathy 的 `autoresearch` 项目(八条纪律的 agent 循环) | `/Users/sky/linux-kernel/github/autoresearch/program.md` |
| evo-memory | DeepMind 2025 Search-Synthesize-Evolve 论文 | `/Users/sky/linux-kernel/ai-doc/memory-systems/evo-memory.md` |
| agent-factory | Agent Factory 2026-03 —— 经验作为代码 | `/Users/sky/linux-kernel/ai-doc/self-improving-agents/agent-factory.md` |
| MemoryBank | 艾宾浩斯遗忘曲线 LLM 记忆论文 | `/Users/sky/linux-kernel/ai-doc/memory-systems/memorybank.md` |
| MemGPT / Letta | 把记忆当作 OS 虚拟内存 | `/Users/sky/linux-kernel/ai-doc/memory-systems/memgpt.md` |
| Karpathy LLM Wiki | LLM 编译的个人知识库方法论 | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f |

---

## 16. 自适应信号(替代固定尺寸阈值)

engram **不设**任何资产的硬行数上限。系统用三种自适应信号把"值得 review 的候选"浮现给所有者,**只建议,永不阻塞 / 警告 / 拒绝**。

| English | 中文 | 触发 / 行为 |
|---------|------|------------|
| Dynamic budget allocation | 动态预算分配 | Relevance Gate 按 Wisdom Metrics 观察到的 utilization rate 动态调整类型预算,常用类型拿更多 context budget |
| Percentile length signal | 百分位长度信号 | 某资产长度 ≥本类型/scope 的 95 百分位时,`engram review` 列为"建议 review"。阈值随**项目自身分布**变,不是全局数字。M4 feature |
| Split / promote / demote proposal | 拆分 / 升级 / 降级建议 | Evolve Engine 提议:*split*(一条 memory 含 2+ 不相交语义簇)、*promote to KB*(3+ memory 共现率 >60%)、*demote workflow→memory*(spine 90 天无执行)、*promote memory→workflow*(memory 含过程步骤且被多次同类用)。**只 proposal,永不自动执行**。M5 feature |

## 17. 检索算法术语(MemPalace 式 hybrid)

| English | 中文 | 含义 |
|---------|------|------|
| Hybrid retrieval | 混合检索 | BM25 + 向量融合评分。`fused_dist = dist * (1.0 - 0.30 * overlap)` |
| Temporal date boost | 时间邻近加权 | query 含 "N weeks ago" 等时,目标日附近的 session 最多 40% 距离缩减 |
| Two-pass retrieval | 两段检索 | assistant-reference 查询("you said X"),第一段只在 user 回合索引查,第二段在 top 候选上加 assistant 内容再查 |
| BM25 fusion | BM25 融合 | 关键词重叠按 Okapi-BM25 评分,在候选集内计算 |
| Stop word list | 停用词表 | 32 个常用词的黑名单,query 提取关键词前剥离 |

## 18. Autolearn 术语(Darwin 式)

| English | 中文 | 含义 |
|---------|------|------|
| Ratchet | 棘轮 | 每轮 autolearn = 一个 git commit;metric 降 → 自动 revert;metric 升 → keep。分数单调上升 |
| Dual evaluation | 双维度评分 | 100 分 rubric:静态 60(SPEC 合规 + fixtures + 可解析 + 无 secret)+ 动态 40(fixtures 通过 + metric delta > 0) |
| Independent evaluator | 独立评估 | 改 spine 的 subagent 和打分的 subagent 必须不同 context,防自评偏见 |
| Phase gate | 阶段闸门 | 连续 K=5 轮后强制 pause,diff summary 写 `engram review`,等人 confirm 再继续 |

## 19. 时间有效期字段

| English | 中文 | 含义 |
|---------|------|------|
| `valid_from` | 起效日 | ISO 8601 日期。事实从此日起成立。frontmatter 可选字段 |
| `valid_to` | 失效日 | ISO 8601 日期。事实到此日终止。frontmatter 可选字段 |
| `expires` | 过期日 | 单点"此后可能过期"标记。和 valid_from/to 互补 —— expires 提示 review;valid_to 表示事实本身有历史边界 |
| Time-filtered query | 时间过滤查询 | graph.db 操作"X 日时以下哪些事实为真?"—— 返回有效期覆盖 X 的资产 |

## 20. 性能预算

| 名字 | 中文 | 目标 |
|------|------|------|
| Hook latency | 钩子延迟 | 每个 Claude Code hook(`engram_stop.sh`、`engram_precompact.sh`)<500ms 完成 |
| Startup context injection | 启动上下文注入 | MEMORY.md + Level 1 核心 <100ms 加载完 |
| `engram review` | 健康审查 | ~1000 条资产的 store 上 <2s |
| LongMemEval Relevance Gate | 检索基准(防御性) | ≥95% R@5 作为 baseline(**不是**对外 headline 指标) |

---

## 新增或重命名术语流程

1. 发一个只改 `docs/glossary.md` + `docs/glossary.zh.md` 的 PR
2. 如果是重命名:`grep -rn "<老术语>" *.md docs/` 并在同一个 PR 里全部更新
3. PR 描述必须说明老名字为何不对(或新术语填补了什么空白)
4. 术语只有在英文行和中文行都填好、"说明"列写清楚理由后才算定稿
