# Auto Session Continuation — engram 自动续接 spec

**Status**: Frozen 2026-04-26 (after user explicit accept).
**Owner**: T-200 ~ T-212.
**Authority**: 这份 doc 是设计权威,任何冲突回到这里查;实现落地时同步 SPEC §3.x / §5 / §14 章节,DESIGN §22 章节。

---

## 0. 一句话目标

让任何 LLM(开源 / 闭源 / 本地)在跨会话、跨工具的协作中,**不需要用户手动输入,自动获得"上次干到哪、为什么这么干、下一步该干啥"** —— 而且这件事:

- 不绑任何 SDK
- 不锁任何模型
- 离线可降级运行
- 全程可被 git diff 审计
- 永远不偷偷改用户的"沉淀记忆"(Memory)

这是 engram 跟 claude-mem 的代差:claude-mem 把会话续接做成了"Claude 专属功能",engram 把它做成 **"开源 LLM 的公共基础设施"**。

---

## 1. 问题域

### 1.1 现状(2026-04-26)

工程师跨多次会话调一个 bug 时:

- 第 1 次:Claude / Codex / Cursor / Gemini 各看到的是空上下文
- 第 2 次:重新解释 5 分钟"上次到哪了"
- 第 3 次:换一个工具,前两次的努力全废
- 第 N 次:工程师自己都忘了之前试过什么

claude-mem 用"SDK 监听 + 后台 worker"解决了 Claude Code 这一个客户端的问题,但:

1. 摘要器锁死 Claude Agent SDK
2. 二进制 SQLite + Chroma,git 看不到
3. 单一 Observation 资产类型,没有"事件 → 知识 → 流程"的三层认知模型
4. 跨工具靠 hook 多写几遍,但**摘要永远只在 Claude 跑得起**

### 1.2 engram 要解决的

让 **任何 LLM 在任何工具里** 跑完一次会话后,下次起手能自动看到:

- 上次这个任务做了什么(Episodic)
- 这个项目的稳定事实(Semantic,从多次 episode 蒸馏出来)
- 这类问题的标准解法(Procedural,从重复模式识别出来)

并且这三层每一层都可以**离线、本地、开源 LLM** 跑。

---

## 2. 总体设计:三层认知模型 + 4-tier compactor

### 2.1 三层认知

借用 Tulving (1972) 的人类记忆分层,对应 engram 的 4 类资产:

```
┌───────────────────────────────────────────────────────────────────┐
│ Episodic — "这次会话发生了什么"                                  │
│   ↓ 资产: Session(新增,本 spec 定义)                            │
│   ↓ TTL: 7~30 天滚动                                              │
│   ↓ 进 prompt: Stage 0(task_hash 命中时整段进)                  │
├───────────────────────────────────────────────────────────────────┤
│ Semantic — "这个项目/模块的稳定事实"                              │
│   ↓ 资产: Memory(已有)                                          │
│   ↓ TTL: 永久                                                     │
│   ↓ 进 prompt: Stage 1~7(scope filter + BM25 + rerank)          │
├───────────────────────────────────────────────────────────────────┤
│ Procedural — "这类问题的标准解法"                                │
│   ↓ 资产: Workflow(已有)                                        │
│   ↓ TTL: 永久                                                     │
│   ↓ 进 prompt: mandatory bypass / spine.* 可执行                 │
├───────────────────────────────────────────────────────────────────┤
│ Long-form Knowledge — 长文 + LLM 编译 digest                      │
│   ↓ 资产: KB(已有)                                              │
│   ↓ TTL: 永久                                                     │
│   ↓ 进 prompt: 只 digest                                          │
└───────────────────────────────────────────────────────────────────┘
```

**关键不变量**:Episodic 全自动写,Semantic / Procedural 必须显式 consent(SPEC §1.2 原则 4)。"自动续接"承诺**不破坏可审计性**。

### 2.2 4-tier compactor

```
事件流(每个 tool_use / user_prompt / outcome)
       │
       ▼
┌───────────────────────────────────────────────────────────────┐
│ Tier 0 — Mechanical(永远跑,无 LLM,毫秒级)                  │
│   提取: tool name / file paths / errors / 时间戳 / token       │
│   输出: <session>.timeline.jsonl                              │
│   失败模式: 不会失败                                          │
└───────────────────────────────────────────────────────────────┘
       │
       ▼  会话结束 / 用户 idle 5 min / 队列 ≥ 100 条
┌───────────────────────────────────────────────────────────────┐
│ Tier 1 — Local Episodic Compactor(开源小模型)                │
│   推荐: Qwen2.5-7B / Llama-3.1-8B / Phi-4 通过 ollama         │
│   任务: 工具流 → narrative(150~300 token)                    │
│   输出: .memory/sessions/<date>/<id>.md                       │
│   失败模式: 用户 ollama 没起 → 降级 mechanical-only narrative │
└───────────────────────────────────────────────────────────────┘
       │
       ▼  daemon idle 5 min + 累计 ≥ 5 个 unprocessed session
┌───────────────────────────────────────────────────────────────┐
│ Tier 2 — Semantic Distiller(开源中等模型)                    │
│   推荐: Qwen2.5-32B / Llama-3.3-70B / DeepSeek-V3             │
│   任务: 跨 N 个 session 蒸馏 "稳定事实" → 候选 Memory          │
│   输出: .memory/distilled/<topic>.proposed.md                 │
│   consent: engram distill review 才进 .memory/local/          │
└───────────────────────────────────────────────────────────────┘
       │
       ▼  weekly cron / 用户跑 engram propose run
┌───────────────────────────────────────────────────────────────┐
│ Tier 3 — Procedural Recognizer(顶配 / 用户 default 模型)     │
│   任务: "这类问题出现 ≥ 3 次 + 解法稳定" → 候选 Workflow       │
│   输出: .memory/workflows/<name>/proposal.md                  │
│   consent: engram propose review 才激活                       │
└───────────────────────────────────────────────────────────────┘
```

**Tier 0 是 ground truth**:Tier 1/2/3 的 LLM 输出 **必须引用 Tier 0 的事实**(file path / tool name / 时间戳),不允许凭空捏造。这是 RAG-over-own-trace 模式 —— 减少 LLM 幻觉的工程手段。

**每层独立可换模型**,通过 `~/.engram/config.toml`:

```toml
[observer.compactor.tier1]
provider = "ollama"
endpoint = "http://localhost:11434/v1"
model    = "qwen2.5:7b"
timeout_seconds = 30

[observer.compactor.tier2]
provider = "openai-compatible"
endpoint = "http://localhost:11434/v1"
model    = "qwen2.5:32b"
timeout_seconds = 120

[observer.compactor.tier3]
provider = "openai-compatible"
endpoint = "https://api.deepseek.com/v1"
model    = "deepseek-chat"
api_key  = "$DEEPSEEK_API_KEY"
timeout_seconds = 300
```

**没配 LLM 时的行为**:Tier 1 自动降级到 mechanical-only summary(Tier 0 的 jsonl 直接渲染成可读 markdown narrative,没有自然语言压缩,但有完整事实链)。Tier 2/3 直接跳过,等用户配上 LLM 再跑。**engram 永远可用**。

---

## 3. 数据形态(SPEC §3.x 扩展)

### 3.1 目录布局

```
.memory/
  sessions/                              ← NEW Episodic 主体
    2026-04-26/
      sess_abc123.md                     ← Tier 1 输出(narrative)
      sess_abc123.timeline.jsonl         ← Tier 0 mechanical 事实流
  distilled/                             ← NEW Tier 2 候选 Memory
    auth-flow.proposed.md
  local/                                 ← Memory 已有(consent 后从 distilled 进来)
  workflows/                             ← Workflow 已有
    debug-grpc-timeout/
      proposal.md                        ← NEW Tier 3 候选(consent 后 spine.*)
  kb/                                    ← KB 已有

~/.engram/
  observe-queue/                         ← NEW 入队区
    sess_abc123.jsonl                    ← 实时 append,事件流
  raw/sessions/                          ← NEW 原始事件备份(可选,30 天 TTL)
    sess_abc123.full.jsonl
  observer.pid                           ← daemon 单例 lockfile
  observer.sock                          ← daemon IPC(可选,UDS 通知)
  archive/raw/<YYYY-MM>/                 ← TTL 到期归档
```

### 3.2 Session frontmatter schema(SPEC §3.x 新增)

```yaml
---
type: session
session_id: sess_abc123
client: claude-code | codex | cursor | gemini-cli | opencode | manual | raw-api
started_at: 2026-04-26T14:23:01Z
ended_at: 2026-04-26T15:47:18Z
duration_seconds: 5057
task_hash: a3f9b2c1...                 # T-172 derive_task_hash 输出
tool_calls: 47                          # Tier 0 计数
files_touched:                          # Tier 0 提取 + 去重
  - src/foo.ts
  - tests/foo.test.ts
files_modified:
  - src/foo.ts
outcome: completed | abandoned | error | unknown
error_summary: null                     # outcome=error 时 mechanical 抓首条 error
prev_session: sess_xyz789               # 同 task_hash 的上一个(双向链)
next_session: null                      # daemon 在写下一个 session 时回填
distilled_into: []                      # Tier 2 把这个 session 蒸馏进了哪些 distilled/*
scope: project                          # 默认 project,user/team 走 consent
enforcement: hint                       # session 永远是 hint,不参与 mandatory
confidence:
  validated_score: 0
  contradicted_score: 0
  exposure_count: 0
  last_validated: 2026-04-26
  evidence_version: 1
---
# Narrative

(Tier 1 输出:150~300 token 的可读叙事;mechanical-only 模式下是 Tier 0 jsonl 渲染)

## Investigated
- ...

## Learned
- ...

## Completed
- ...

## Next steps
- ...
```

### 3.3 timeline.jsonl(Tier 0 输出格式,line-delimited JSON)

每条事件是一行 JSON:

```json
{"t":"2026-04-26T14:23:01.123Z","kind":"tool_use","tool":"Read","args_hash":"sha256-...","files":["src/foo.ts"],"tokens_in":120,"tokens_out":340}
{"t":"2026-04-26T14:23:05.456Z","kind":"tool_use","tool":"Edit","files":["src/foo.ts"],"diff_lines_added":12,"diff_lines_removed":3}
{"t":"2026-04-26T14:23:12.789Z","kind":"user_prompt","prompt_hash":"sha256-...","prompt_chars":234}
{"t":"2026-04-26T14:25:08.012Z","kind":"error","tool":"Bash","exit_code":1,"stderr_hash":"sha256-...","stderr_first_line":"ImportError: ..."}
{"t":"2026-04-26T15:47:18.000Z","kind":"session_end","outcome":"completed"}
```

**约束**:
- 每条 ≤ 4 KB(超出截断,挂 `truncated:true` 标记)
- prompt 正文 / stderr 正文 **不入 timeline**(只入 `~/.engram/raw/sessions/<id>.full.jsonl`,且只在用户 opt-in `[observer.raw_retention] enabled = true` 时保留)
- 默认 raw 保留 30 天,过期归档到 `~/.engram/archive/raw/<YYYY-MM>/`

---

## 4. 协议:engram observe(SPEC §14 新增)

### 4.1 通用观察协议

任何客户端只要能 fork 一个进程就能接入。协议从 stdin 读 JSON,从 stdout 写 ack。

```bash
echo '{"event":"tool_use","tool":"Read","args":{"file_path":"src/foo.ts"},"result_chars":340}' \
  | engram observe --session=sess_abc123 --client=claude-code
```

stdout:
```json
{"ok":true,"queued_at":"2026-04-26T14:23:01.124Z","queue_depth":42}
```

### 4.2 性能合约

`engram observe` 的承诺:

| 条件 | p50 | p99 |
|---|---|---|
| 队列深度 < 1000 条 | < 5 ms | < 10 ms |
| 队列深度 1000~10000 条 | < 10 ms | < 50 ms |
| 队列满(10000+) | 拒绝写入,返回 `{"ok":false,"reason":"queue_full"}`,不阻塞 hook | < 5 ms |

实现要点:
- 直接 append 到 `~/.engram/observe-queue/<session-id>.jsonl`,fcntl.flock 短暂持锁
- **不**调任何 LLM,**不**触发 daemon,**不**做语义处理
- 用 `os.O_APPEND` + `os.write`(POSIX 单 write < 4KB 原子),避免重新打开 / fsync

### 4.3 客户端接入

5 个 adapter 各自带一个 hook 脚本(`adapters/<client>/hooks/`):

```bash
# adapters/claude-code/hooks/post_tool_use.sh
#!/bin/sh
# Claude Code 通过环境变量传入 session id 和 tool 信息
exec engram observe --session="$CLAUDE_SESSION_ID" --client=claude-code
```

```bash
# adapters/codex/hooks/post_tool_use.sh
#!/bin/sh
exec engram observe --session="$CODEX_SESSION_ID" --client=codex
```

无 hook 的客户端(用户直接调本地 ollama):

```bash
# 用户的 prompt wrapper
ollama run qwen2.5 < prompt | tee >(engram observe --client=raw-api --session="$SESSION")
```

`engram observer install --target=<client>` 命令安装时自动写 hook 脚本路径(类似 T-163 的 mcp install)。

---

## 5. Daemon 设计(DESIGN §22 新增)

### 5.1 单例 + 自愈

```
~/.engram/observer.pid  ← lockfile,fcntl.flock + PID
```

启动流程:
1. 尝试 `fcntl.flock(LOCK_EX | LOCK_NB)` 获取 pid 文件
2. 拿不到 → 检查 PID 是否还活着
   - 还活着 → 退出,return 0(已经在跑了)
   - 死了 → steal lock,清理孤儿队列(继承前任未处理的 session)
3. 启动 watcher
4. SIGTERM / SIGINT → 优雅关停(处理完队列再退)

### 5.2 处理循环

```python
while running:
    sessions = scan_observe_queue()  # 找有新事件的 session
    
    for sess in sessions:
        # Tier 0 一直跑(每条事件一进来就处理)
        run_tier0(sess)
        
        if sess.is_ended() or sess.last_event_age > IDLE_THRESHOLD:
            # session 结束 / idle 5 min → Tier 1
            run_tier1(sess)
    
    if total_idle > 5 * 60:
        # daemon idle 5 min + 累计未蒸馏 session ≥ 5 → Tier 2
        run_tier2_if_threshold()
    
    sleep(POLL_INTERVAL)  # 默认 2 秒
```

### 5.3 调度参数(`config.toml`)

```toml
[observer]
enabled = true
poll_interval_seconds = 2
session_idle_threshold_seconds = 300       # 5 min
tier2_min_unprocessed_sessions = 5
tier2_min_idle_seconds = 300
tier3_schedule = "weekly"                   # weekly | daily | manual
raw_retention_days = 30
queue_max_events_per_session = 10000
```

### 5.4 Cross-session task linkage(prev/next 双向链)

写入 session.md 时:

1. 计算 task_hash(T-173)
2. 在 sessions/ 下找最近一个**同 task_hash + ended_at < self.started_at** 的 session
3. 写入 `prev_session: sess_xxx` 到自身 frontmatter
4. 回写那个 session 的 `next_session` 字段(原子重写,fcntl.flock)

**Stage 0 注入策略**:同 task_hash 的最近 ≤ 3 个 session(按时间倒序)整段进 prompt;超出 3 个走 Tier 2 蒸馏后再用。

---

## 6. Relevance Gate Stage 0(DESIGN §5.1 扩展)

```
Stage 0 (NEW): Recent session continuation
  输入: task_hash(若有)
  动作: 找同 task_hash 最近 ≤ 3 个 sessions(按时间倒序)
  budget: 默认 25% of total context(可配)
  输出: 整段 narrative + frontmatter 摘要,优先级最高(在 Stage 1 mandatory 之前)

Stage 1 (existing): mandatory bypass
Stage 2 (existing): scope filter
...
```

**为什么 Stage 0 在 mandatory 之前**:任务连续性是用户当下最关心的事,比一般规则更紧迫。但 Stage 0 永远不能挤掉 mandatory —— 用 25% budget 上限保护 mandatory + 普通检索的余地。

---

## 7. Confidence-driven decay(DESIGN §22.4)

### 7.1 衰减公式

每个 session 的 effective_ttl 不是固定 30 天,而是按 confidence 调整:

```
base_ttl = 30 days
exposure_bonus = min(exposure_count * 3 days, +60 days)
contradicted_penalty = contradicted_score * 5 days
abandoned_penalty = (outcome == "abandoned") ? 14 days : 0

effective_ttl = max(7 days, base_ttl + exposure_bonus - contradicted_penalty - abandoned_penalty)
```

### 7.2 流转

- `effective_ttl` 到期 → 移到 `~/.engram/archive/sessions/<YYYY-MM>/`(不删,SPEC §1.2 6 个月最低)
- 高频引用(exposure ≥ 5) → daemon 自动放进 Tier 2 蒸馏候选队列
- 跟新 session 矛盾 → Consistency Engine Phase 4(staleness)标记,不自动删,只降权

### 7.3 wisdom curve 接入

`engram wisdom report` 加 2 条新曲线:

- **C7 — Continuation hit rate**:Stage 0 命中率(进 prompt 的 session 被用户/LLM "继续做" 的比例)
- **C8 — Distillation yield**:Tier 2 产出的 distilled 候选被 promote 成 Memory 的比例

---

## 8. Consent 通路:Session → Memory / Workflow

### 8.1 distill review

```bash
engram distill review
# 列出 .memory/distilled/*.proposed.md
# 每条带:摘要 / 来源 sessions / 建议 scope / 与现有 Memory 的潜在冲突

engram distill promote <topic> [--scope=user] [--enforcement=default]
# 把 distilled/<topic>.proposed.md 移到 local/<topic>.md(consent 信号)
# 同步写 distilled_into 反向链到来源 sessions
# append usage event: distilled_promoted

engram distill reject <topic> [--reason=...]
# 移到 archive/distilled/<YYYY-MM>/,journal 记原因
```

LLM 自己也可以跑这个命令(consent 不要求人按,只要求显式动作)—— 这跟 T-49 apply_resolution 的 `consent=True` 是同一个语义。

### 8.2 propose review(Workflow)

```bash
engram propose review              # 列 workflows/*/proposal.md
engram propose promote <name>      # 激活 Workflow,proposal.md → README.md + spine.*
engram propose reject  <name>      # 归档
```

---

## 9. 与现有任务/已有模块的关系

| 现有 | 关系 |
|---|---|
| **T-170 usage bus** | observer 复用 usage bus 写 session 事件(`session_started` / `session_ended` / `session_promoted`) |
| **T-172 task_hash** | observer 直接复用,不重复实现 |
| **T-180 canonical URI(partial)** | session 用 `engram://session/<id>` URI;T-180 收尾时一起冻结 |
| **T-181 reachability(blocking M4 P0)** | session 不进默认 reachability,作为单独通道(SPEC §11 的 INV-I1 不覆盖 sessions/) |
| **T-46 Consistency Engine** | Phase 4 staleness 扫 sessions/ 时识别"过时 session" |
| **T-49 apply_resolution** | Session promote / archive 走相同 dry-run + consent 模式 |
| **T-188 wisdom report** | 加 C7 / C8 两条新曲线,P1 |
| **T-190~T-194 Evolve Engine** | Tier 3 procedural recognizer 是 Evolve 的入口之一 |

---

## 10. 任务分解(T-200 ~ T-212)

| ID | 任务 | 依赖 | 优先级 |
|---|---|---|---|
| T-200 | observer 协议 + `engram observe` CLI(< 10 ms 入队) | T-15 journal | **P0** |
| T-201 | observer daemon 骨架(单例 + watcher + graceful shutdown) | T-200 | **P0** |
| T-202 | Tier 0 mechanical compactor | T-200, T-201 | **P0** |
| T-203 | Session 资产类型 + SPEC §3.x 章节 + frontmatter | T-12, T-202 | **P0** |
| T-204 | Tier 1 LLM compactor + ollama / openai-compatible provider + mechanical 降级 | T-202, T-203 | P1 |
| T-205 | 5 adapter hook 脚本 + `engram observer install --target=<client>` | T-200 | P1 |
| T-206 | Relevance Gate Stage 0(task_hash 命中 session 注入) | T-40, T-203 | P1 |
| T-207 | Cross-session task linkage(prev/next 双向链) | T-203, T-173 | P1 |
| T-208 | Tier 2 semantic distiller → distilled/<topic>.proposed.md | T-204 | P2 |
| T-209 | `engram distill review/promote/reject` consent 通路 | T-208 | P2 |
| T-210 | Tier 3 procedural recognizer → workflows/proposal.md | T-208 | P2 |
| T-211 | Confidence-driven decay + Consistency Engine 跨 session 矛盾扫描 | T-46, T-203 | P2 |
| T-212 | E2E 跨 5 session 跑同一个 bug,验证"第 5 次起手 LLM 看见前 4 次" | T-200~T-211 | **P0**(交付 gate) |

P0 是本周交付目标(T-200 ~ T-203 + T-212 框架),P1 / P2 在后续 2~4 周完成。

---

## 11. 不变量(MUST)

1. **observer 永不阻塞会话**:`engram observe` p99 < 50 ms,失败时 hook 静默降级
2. **Tier 0 永远跑**:无 LLM / 无网络 / daemon 死亡都不影响事件入队
3. **Session 不自动晋升 Memory**:必须经 `engram distill promote` 显式动作
4. **distilled / proposal 文件不进 Relevance Gate 检索**:不污染搜索结果
5. **客户端 SDK 不 import**:engram 不 import claude-agent-sdk / openai-agents 等任何客户端 SDK
6. **离线降级路径**:无 LLM 配置时,Tier 1 输出仍然产出有效 narrative(mechanical-only)
7. **git diff 可读**:session.md / distilled/*.md / proposal.md 全是 markdown,人和 git 都能直接看

违反任何一条都属于 SPEC 级别 bug,不是设计选择。

---

## 12. 评测指标(T-212 验收)

跑分场景:同一个 bug 跨 5 次会话,客户端各异(claude-code / codex / cursor / 一次离线 ollama / claude-code 收尾)。

通过条件:

1. 每次会话起手,LLM **不需用户提示** 就能引用上一次的具体决策
2. 第 5 次起手时,前 4 个 session 的 narrative 摘要(≤ 800 token)出现在 prompt 里
3. 所有 session 在离线 ollama 上也能产出 narrative(mechanical 降级)
4. 5 个 session 没有产出任何 Memory 变更(自动写入承诺)
5. 用户跑 `engram distill review` 看到 ≥ 1 个 distilled 候选(Tier 2 自动跑了)
6. 用户跑 `engram distill promote` 后,新 session 的 prompt 里出现 promoted Memory 的影响

---

## 13. 时间线

| 阶段 | 时间 | 交付 |
|---|---|---|
| **本次会话** | 2026-04-26 | spec frozen + T-200~T-203 落地 + HTML 同步 |
| Week 1 | 2026-04-27 ~ 2026-05-03 | T-204(Tier 1)+ T-205(adapter hooks)+ T-206(Stage 0)+ T-207(linkage) |
| Week 2 | 2026-05-04 ~ 2026-05-10 | T-208(Tier 2)+ T-209(distill review/promote)+ T-211(decay) |
| Week 3 | 2026-05-11 ~ 2026-05-17 | T-210(Tier 3 procedural)+ T-212(E2E 验收) |

**P0 = M4 收尾 + Auto-Continuation MVP**;P1/P2 进 M5。

---

## 14. 与 claude-mem 的差异(对照表,可借鉴 vs 边界)

| 维度 | claude-mem | engram(本 spec) | 立场 |
|---|---|---|---|
| 自动观察 | hook + worker(自动) | hook + daemon(自动) | **借鉴** |
| 内容压缩 | Claude SDK 锁死 | 4-tier,可换任何 LLM | **超越** |
| 存储 | SQLite + Chroma | markdown + sidecar 索引 | **超越** |
| 资产类型 | Observation 单一 | Episodic / Semantic / Procedural / KB 四类 | **超越** |
| 跨工具 | 多客户端 hook | 通用 stdin 协议 + 5 adapter hooks | **打平 / 略超** |
| 跨项目 | 手工标 `merged_into_project` | 2 轴 scope + pool 订阅 | **超越** |
| 一致性 | content_hash dedup | content_hash + Phase 4 staleness + 跨 session 矛盾 | **超越** |
| 进 prompt | 三层渐进披露(search → timeline → full) | Stage 0 + 7-stage Relevance Gate | **借鉴 + 扩展** |
| Wisdom curve | discovery_tokens(ROI 单一) | C1~C8(8 条曲线) | **超越** |
| 离线降级 | 不能(摘要必须 Claude) | 全量(mechanical-only 兜底) | **超越** |

**借鉴**:hook + 后台 worker、content_hash dedup、worker_pid 自愈、progressive disclosure。
**边界**(不学):SDK 锁死、SQLite 主存、单一资产类型、per-project only。

---

## 附录 A — 与已冻结决定的兼容性

- SPEC §1.2 原则 4(不偷偷改用户文件):**守住**(distilled / proposal 不算 mutate Memory)
- SPEC §3.1 三类资产:**扩展为四类**(Session 加入,要 SPEC bump 到 v0.2.1)
- SPEC §4.1 frontmatter MUST be preserved:**继承**
- SPEC §13.7 additive default:Session frontmatter 缺失字段按零态块填充
- DESIGN §5.1 7-stage Relevance Gate:**插入 Stage 0**(在 Stage 1 之前)

## 附录 B — 测试矩阵(粗草)

| 层 | 单测 | E2E |
|---|---|---|
| T-200 observe queue | 入队原子性 / fcntl 并发 / 队列满拒绝 / 性能 < 10 ms | 5 客户端 hook 各跑一次 |
| T-201 daemon | 单例 / 自愈 / SIGTERM 优雅 / 孤儿队列接管 | 24h 稳定性 |
| T-202 Tier 0 | 各 tool / file / error 提取 / 无 LLM 也跑 | mechanical-only 完整 narrative |
| T-203 Session | frontmatter round-trip / validate 零错 / archive 流 | git diff 可读 |
| T-204 Tier 1 | ollama / openai-compatible / 降级 | 离线产出 |
| T-206 Stage 0 | task_hash 命中 / budget 25% / 不挤 mandatory | 真实 prompt 注入 |
| T-212 跨 session | 5 客户端任务链 / Tier 2 自动产出 / consent 通路 | 黑盒验收 |

测试覆盖率目标:核心模块 90%+,observer 整体 80%+。

---

**End of spec**.
