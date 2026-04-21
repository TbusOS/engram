[English](README.md) · [中文](README.zh.md)

# engram

> **engram**(记忆痕迹)—— 神经科学术语,指大脑中留下的物理记忆印记。
> 在这个项目里:一个本地、可移植、不绑定任何 LLM 的记忆系统 —— **而且越用越聪明**。

**状态:** v0.2 重写设计进行中,详见 [实施计划](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md)。v0.1 归档在 [`docs/archive/v0.1/`](docs/archive/v0.1/)。

---

## engram 是什么

当下大多数 LLM 工具都想"拥有"你的记忆。Claude Code 有自己的 memory。ChatGPT 有 "Memories"。mem0、Letta、MemGPT 把你的数据拉进它们的存储。换模型,上下文丢了。换工具,一切从头教起。

**engram 是反过来的设计。** 记忆以纯 markdown 文件形式存在你自己的磁盘上,格式开放,任何 LLM 不用插件都能读。工具来来去去,记忆留下来。而且,**你用得越久,它越聪明** —— 因为 engram 不只是存数据,它主动维护记忆的质量。

## 目标:最好的开源永久记忆系统

engram 要同时做好五件事,这五件事目前没有任何单个系统(claude-mem / basic-memory / Karpathy LLM Wiki / mem0 / MemGPT / Letta / ChatGPT Memories)全做到:

1. **LLM 优先、工具无关** —— 任何模型,本地或云端,读 `.memory/` 方式一样
2. **人可观察** —— 一等公民 Web UI 可视化整个知识图谱、演化历史、以及任一 LLM 在给定任务下实际会加载什么
3. **团队 / 组织 / 主题共享,但不污染** —— 2 轴 scope(4 级归属层次 + 正交主题订阅)+ 显式 `enforcement`(mandatory / default / hint);共享更新能传播给订阅者,但噪声永远不跨边界
4. **三类资产,不只是 Memory** —— 短 Memory 给 LLM 启动,中等 Workflow(文档 + 可执行 spine + fixtures)给流程性知识,长 Knowledge Base(人写、LLM 编译摘要)给领域参考
5. **可量化地变聪明** —— 四组"智慧"曲线(workflow 熟练度 / 任务复现效率 / 记忆精炼率 / 上下文效率)证明系统在学习,而非只是记录

**不设任何容量上限。** 质量由**一致性引擎**维护 —— 它主动检测七类不一致(事实 / 规则 / 引用失效 / 工作流衰变 / 时间过期 / 静默覆盖 / 同题分歧)并**给出建议**(永不自动执行)让你决定是否更新、合并、标记 supersede 或归档。

## 五层架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Layer 5  观察层          engram-web:总览 / 图谱 / 上下文预览 /            │
│           (FastAPI+Svelte) 收件箱 / 自学习控制台 / ...                      │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 4  接入层          适配器 | MCP Server | Prompt Pack |              │
│           (面向 LLM)       Python SDK | TypeScript SDK                     │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 3  智能层          相关性闸门 · 一致性引擎 · 自学习 · 演化           │
│           (可选、可关)     · 跨仓传信器 · 智慧指标                          │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 2  控制层          engram CLI:memory / workflow / kb / pool /       │
│           (LLM 可选)       team / org / inbox / consistency / context /    │
│                           mcp / web / playbook / migrate                   │
├──────────────────────────────────────────────────────────────────────────┤
│  Layer 1  数据层          .memory/ 目录 + ~/.engram/                        │
│           (纯 markdown)    符合 SPEC,任何 LLM 都能读                        │
└──────────────────────────────────────────────────────────────────────────┘
```

每一层都可独立替换。删掉 Layer 5,CLI 还能用。关掉 Layer 3 智能层,系统仍然正确(只是不自演化)。完全卸载 CLI,markdown 仍然可被人、LLM、Obsidian 和任何懂 markdown 的工具读取。

## 三类资产

按**函数**区分(资产是什么),**不按尺寸**。不设任何硬上限。系统用自适应信号代替固定阈值。

| 类别 | 是什么 | 必备结构 | LLM 上下文角色 |
|------|--------|---------|---------------|
| **Memory** | **原子断言** —— 能独立被 supersede 的事实 / 规则 / 偏好 / 指针 | 一个 `.md` + frontmatter + body | 经 Relevance Gate 进系统 prompt |
| **Workflow** | **可执行过程** —— 有 spine 能跑 | `workflow.md` + `spine.*` + `fixtures/` + `metrics.yaml` + `rev/` | 任务匹配时加载;autolearn 自演化 |
| **Knowledge Base** | **领域参考** —— 人会专门来读的多章节文档 | `README.md` + 章节 + `assets/` + `_compiled.md`(LLM 编译摘要) | 按需检索;`_compiled.md` 优先进 budget |

**无尺寸硬上限。** 三个自适应信号代替固定阈值:

- **动态预算分配** —— Relevance Gate 按实际 utilization 调整类型预算
- **百分位长度信号** —— 长度在本类型前 5% 的资产在 `engram review` 里出现"建议 review"提示 —— 不是警告、不是硬阻塞
- **拆分 / 升级 / 降级建议** —— Evolve Engine 建议拆分密集 memory、升级 memory 簇为 KB 文章、降级未用 workflow 为 memory、升级含过程 memory 为 workflow —— **全是建议,永不自动执行**

新项目不用从零开始 —— 订阅需要的 pool,立刻继承已验证的工作流和引用资料:

```bash
engram init --org=acme --team=bsp --subscribe=kernel-work,android-bsp
```

## Scope:两个正交轴,不是一条线

真实团队共享知识的方式不止一种。engram 把它们分成两个独立的轴:

### 归属轴(membership —— 你隶属,就继承)

```
org      ~/.engram/org/<name>/       公司 / 组织硬约束(权威最高)
team     ~/.engram/team/<name>/      团队 / 部门约定
user     ~/.engram/user/             本人跨项目基线
project  <project>/.memory/local/    仅当前项目(最具体)
```

你属于 0 或 1 个 org、0 或 N 个 team,你始终是你,工作在 N 个项目里。上游层级全部自动继承。同 `enforcement` 级别下,越具体越赢。

### 订阅轴(pool —— 你选择加入)

```
pool     ~/.engram/pools/<name>/     主题式共享,显式订阅
```

Pool **正交**于归属层次。pool 在某个归属层级上被订阅 —— 在 `pools.toml` 里声明 `subscribed_at: org | team | user | project`。pool 内容就以该层级的权威参与冲突解决。

例子:
- 你的 **org** 订阅 `pool: compliance-checklists` → 公司所有项目把它当 org 级 mandatory 看
- **平台团队** 订阅 `pool: design-system` → 该团队所有项目当 team 级继承
- **你本人** 订阅 `pool: my-dotfiles-notes` → 只有你的项目看到
- 单个 **项目** 订阅 `pool: acme-checkout-service-playbooks` → 仅该项目使用

### Enforcement 级别

每条规则声明自己有多硬:

- `mandatory` —— 下级不可覆盖;`engram validate` 报错
- `default` —— 可覆盖,但覆盖方必须声明 `overrides: <id>`
- `hint` —— 自由覆盖

### 冲突解决(一棵决策树)

1. `mandatory` 赢过 `default` 赢过 `hint`
2. 同 enforcement 下,**越具体越赢**:`project > user > team > org`
3. Pool 内容按 `subscribed_at` 层级参与比较
4. 仍然同级:LLM 带两条都进上下文仲裁,`engram review` 标 warning

## 跨仓库协作

你的 agent 经常并发操作多个关联仓库 —— 比如 A 仓用 B 仓的 SDK。当 A 的 agent 发现 B 的 bug 或难用 API 时,可以直接给 B 的 inbox 发一条结构化消息:

```bash
engram inbox send --to=repo-b \
  --intent=api-change \
  --message="你的 read_config() 在文件缺失时默默返回 {},应该抛异常。" \
  --code-ref="libb/config.py:L42@abc123"
```

下次 B 的 LLM 启动 session 时,它会看到这条 pending 消息,连同自己的 memory 一起进上下文。B 改完之后,A 下次启动会收到反向通知。所有消息都 journal、按 `code-ref` 去重、按 rate-limit 节流,防止刷屏。

## 为什么用 markdown(不用向量数据库)

- **任何 LLM 都能读** —— 不需要 SDK、parser、embedding 管线就能开始
- **任何人都能编辑** —— Obsidian、Logseq、vim、VS Code 即开即用
- **git 友好** —— diff 可读,团队靠 `git push` 共享
- **即使 engram 本身停更也没事** —— 你剩下的仍然是一堆能读能改的 markdown 笔记

engram 内部**使用** embedding(本地 `bge-reranker-v2-m3`)为 Relevance Gate 加速,但 embedding 是**缓存**,不是事实源。markdown 永远是 canonical。

## 差异化一览

| | engram v0.2 | claude-mem | basic-memory | Karpathy Wiki | mem0 | MemGPT / Letta | ChatGPT Mem |
|---|---|---|---|---|---|---|---|
| 纯 markdown 存储 | ✅ | SQLite | ✅ | ✅ | 托管 | 内部 | 托管 |
| 工具无关 | ✅ | 仅 Claude | 大部分 | 大部分 | 大部分 | SDK 耦合 | 仅 ChatGPT |
| 归属层次 + pool scope | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 显式 `enforcement` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 7 类一致性检测 | ✅ | 部分 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 可执行 workflow | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 知识库类 (KB) | ✅ | ❌ | 部分 | ✅ | ❌ | ❌ | ❌ |
| 一等公民 Web UI | ✅ | ❌ | ❌ | ❌ | 部分 | 部分 | ✅ |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 跨仓收件箱 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 量化的自改进 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 开源 | ✅ | ✅ | ✅ | ✅ | 部分 | ✅ | ❌ |

## 核心原则

5 条,不打折:

1. **记忆是你的数据资产,不是某个产品的功能**。它属于你。
2. **可移植性 > 花哨功能**。乏味的 markdown 在十年尺度上赢。
3. **质量高于容量**。不限你存多少,但严格守住每一条的水平。一致性引擎保证 store 即使膨胀也不乱。
4. **永不自动删**。删除走 `archive/`,保留期 ≥ 6 个月。出错可恢复。
5. **证据驱动的演化**。记忆的置信度来自记录的结果,不是感觉。系统用**数据**证明某条记忆不好,才让它退役。

## Quick start(v0.2 —— CLI 在 M2–M4 建设中)

```bash
# 安装(计划中 —— 目前 v0.2 设计阶段)
pip install engram-cli

# 任意项目目录 —— 小团队,最小配置
engram init --subscribe=kernel-work --adapter=claude-code,codex

# 大组织 —— 完整层次
engram init --org=acme --team=platform \
  --subscribe=compliance-checklists,kernel-work,design-system \
  --adapter=claude-code,codex,gemini

# 生成:
#   .memory/MEMORY.md                        —— landing 索引(LLM 第一个读)
#   .memory/local/                           —— 项目级资产
#   .memory/pools/<name>/ → ~/.engram/...    —— 订阅的 pool symlink
#   .memory/workflows/<name>/                —— 项目私有工作流
#   .memory/kb/<topic>/                      —— 项目私有知识库
#   .memory/pools.toml                       —— 订阅配置(subscribed_at)
#   CLAUDE.md, AGENTS.md, GEMINI.md          —— 适配器 prompt 模板

# 任何 LLM 用起来 —— store 是 canonical
claude                   # 读 CLAUDE.md → 读 .memory/
codex                    # 读 AGENTS.md → 读 .memory/
engram mcp serve         # 给 Claude Desktop / Zed / 任何 MCP 客户端
engram context pack --task="修 checkout flow smoke test" --budget=4k | ollama run qwen:7b

# 观察与维护
engram web serve         # 打开 http://127.0.0.1:8787 看 dashboard
engram consistency scan  # 扫冲突,给出 resolve 建议
engram review            # 聚合健康检查
engram wisdom report     # 看四组自改进曲线
```

**命令细节?** SPEC.md / DESIGN.md v0.2 正在写,进度看 [plan](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md)。

## 从其他系统迁移

```bash
engram migrate --from=v0.1        # engram v0.1
engram migrate --from=claude-code # ~/.claude/projects/.../memory/
engram migrate --from=chatgpt     # ChatGPT Memory 导出 JSON
engram migrate --from=mem0        # mem0 db 导出
engram migrate --from=obsidian    # Obsidian 日记或指定文件夹
engram migrate --from=letta       # Letta / MemGPT 存档
```

## 仓库结构

```
engram/
├── README.md / README.zh.md               # 当前文件
├── SPEC.md / SPEC.zh.md                   # v0.2 数据格式规范(进行中)
├── DESIGN.md / DESIGN.zh.md               # v0.2 五层架构实现设计(进行中)
├── METHODOLOGY.md / METHODOLOGY.zh.md     # LLM 如何写 memory(进行中)
├── TASKS.md / TASKS.zh.md                 # 活任务板(进行中)
├── CONTRIBUTING.md / CONTRIBUTING.zh.md
├── docs/
│   ├── glossary.md / glossary.zh.md       # 双语术语锚点
│   ├── archive/v0.1/                      # 早期 3 层架构(冻结)
│   └── superpowers/plans/                 # 执行计划
├── cli/                                   # Python CLI(M2–M4)
├── web/                                   # FastAPI + Svelte Web UI(M7)
├── sdk-ts/                                # TypeScript SDK
├── adapters/                              # 工具特定的 prompt 模板
├── seeds/                                 # init 种子
├── playbooks/                             # 可安装的工作流包
└── tests/
```

## 灵感来源

engram 站在多个项目和论文的肩膀上。每一条都塑造了一个具体部分:

- [**Karpathy —— LLM Wiki 作为个人知识库**](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) —— 写入侧综合、持续累积(Knowledge Base 类)
- [**autoresearch**](https://github.com/karpathy/autoresearch)(Karpathy) —— 八条纪律的 agent 优化循环(Autolearn 引擎)
- **Agent Factory**(2026-03 arXiv) —— *经验应存为可执行代码而非文本*(Workflow 类 + spine)
- **evo-memory**(DeepMind 2025) —— Search → Synthesize → Evolve 生命周期,ReMem action-think-refine(Evolve 引擎)
- [**MemoryBank**](https://arxiv.org/abs/2305.10250) —— 艾宾浩斯曲线启发,改造为基于置信度的保留而非基于时间的衰减
- [**MemGPT / Letta**](https://github.com/cpacker/MemGPT) —— 把记忆当 OS 虚拟内存(启发 Layer 1 分层思路)
- **Claude Code 自带的记忆系统** —— 本项目直接泛化的前身

## 社区

- **讨论区** —— 设计评审 / 问答 / 使用场景分享:https://github.com/TbusOS/engram/discussions
- **Issues** —— bug 报告 / 功能请求:https://github.com/TbusOS/engram/issues
- **介绍站** —— https://TbusOS.github.io/engram/
- **Web UI 预览** —— https://TbusOS.github.io/engram/design/
- **贡献方式**:见 [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **v0.2 实施计划**:[`docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md`](docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md)

## License

MIT。
