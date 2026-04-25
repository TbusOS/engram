# SPEC-AMEND v0.2.1 — Usage Evidence Model & Confidence Derived Cache

**Status**: 草案 (draft) — 待 v0.2.1 SPEC-AMEND PR 一并合
**Affects**: SPEC §4.8(`confidence` 字段)/ §11.4(Confidence and Evidence)
**Owners**: T-170 / T-171 / T-172 / T-185 一同实现
**Last updated**: 2026-04-25

## 1. 问题(为什么动 SPEC)

issue #9 揭示了当前 `confidence` 模型的根本缺口:

- `validated_count` / `contradicted_count` 是直接整数计数 → 谁都能写,**LLM 自报任务成功 → 计数 +1** 是合法路径,但任务成功 ≠ 该 asset 贡献。
- 资产被频繁加载会推高 `usage_count`,但加载 ≠ 内容正确。
- 单任务加载多 asset 时,成功 / 失败如何归因到具体 asset 没有定义。
- Consistency Engine dismiss false positive 后更新 confidence 缺审计记录。

长期错误规则会因 LLM 自报循环 + 频繁加载得到高 confidence,这是 **"记忆系统帮自己说谎"** 的反模式。mem0 / Letta 都踩过坑。

## 2. 改 SPEC §4.8(frontmatter `confidence` 字段)

### 2.1 现有 schema(v0.2)

```yaml
confidence:
  validated_count: 3
  contradicted_count: 0
  last_validated: 2026-04-20
  usage_count: 12
```

### 2.2 v0.2.1 schema(派生缓存,不可手写)

```yaml
confidence:
  # 派生字段,任何工具都不能直接编辑这个块。
  # 数据源是 ~/.engram/journal/usage.jsonl(append-only)。
  # 跑 `engram graph rebuild --recompute-confidence` 全量重算。
  validated_score: 4.2       # sum(positive trust_weights)
  contradicted_score: 0.8    # sum(|negative trust_weights|)
  exposure_count: 47         # 全部事件(含 loaded_only)
  last_validated: 2026-04-25
  evidence_version: 1        # 派生算法版本,改算法时全量重算
```

**关键约束**:

1. 任何工具(LLM / adapter / human / Consistency Engine)**不能直接修改 frontmatter 的 confidence 块**。只能通过往 `usage.jsonl` append 事件 + 后台 / 按需 recompute。
2. `validated_count` / `contradicted_count` 整数字段**废弃**;迁移时按 trust_weight=0.5 / 计数把整数转为浮点 score(SPEC §13 additive default 规则)。
3. 缓存哈希不匹配 / 缺 `evidence_version` / `last_validated` 早于 `~/.engram/journal/usage.jsonl` 末行时间戳时,Relevance Gate 走中性默认(不奖不罚)+ 触发后台重算。

## 3. 新章节 SPEC §11.4 — Usage Event Bus

### 3.1 文件位置

```
~/.engram/journal/usage.jsonl   # append-only, JSONL, fcntl.flock 跨进程并发安全
```

跟其他 journal 一样,SPEC §3.4 / §5.1 的 contract 适用:工具 MUST NOT 截断 / 改写;graph.db 可从 journal 完全重建。

### 3.2 事件 schema(每行一个 JSON object)

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `asset_uri` | string | yes | canonical URI(T-180 后)或 scope-local id(M5 兼容) |
| `task_hash` | string | yes | 任务关联 key(T-173 自动派生:explicit > env > git > 时间窗) |
| `event_type` | enum | yes | `loaded` / `validated` / `contradicted` |
| `actor_type` | enum | yes | `human` / `llm` / `workflow` / `consistency_engine` |
| `evidence_kind` | enum | yes | 见 §3.3 8 类 |
| `trust_weight` | float | yes | 默认从 evidence_kind 表查;允许显式覆盖 |
| `co_assets` | string[] | optional | 同 task_hash 下同时加载的其他 asset_uri 列表 |
| `timestamp` | ISO-8601 string | yes | 事件发生时间 |
| `session_id` | string | optional | 会话标识(adapter / agent 自己定) |
| `model_id` | string | optional | LLM 模型标识 |

### 3.3 8 类 evidence_kind 与默认 trust_weight

| evidence_kind | 默认 weight | 谁会发 | 含义 |
|---|---|---|---|
| `explicit_user_confirmation` | **+1.0** | human | 用户明确说 "这条 asset 在这次任务里是对的" |
| `explicit_user_correction` | **-1.0** | human | 用户对该 asset 引导出来的行为做了修正 |
| `workflow_fixture_pass` | **+0.6** | workflow | 该 asset 关联的 workflow fixture 通过 |
| `workflow_fixture_fail` | **-0.6** | workflow | fixture 失败 |
| `false_positive_dismissed` | **+0.4** | consistency_engine | 用户 dismiss 该 asset 的 Consistency 报告 = 隐式确认它仍正确 |
| `task_success_heuristic` | **+0.2** | llm | LLM 自报任务成功;弱信号(因为 LLM 自报不可靠) |
| `task_failure_heuristic` | **-0.2** | llm | LLM 自报任务失败 |
| `loaded_only` | **0.0** | llm | 仅加载;只增 `exposure_count`,不影响 correctness |

权重对比关系是 **人 > workflow fixture > LLM 自报 > 仅加载**,这是 SPEC 级硬规则,任何实现不得倒置。

### 3.4 co_assets 平摊算法(防 1-of-N 自我膨胀)

任务成功一次,加载了 N 个 asset 时,**禁止给每个 asset 都 +0.2**。规则:

```
adjusted_weight(asset_i) = trust_weight / max(1, len(co_assets) + 1)
```

或等价的对称形式:每个事件已经显式列出了**除自己以外**的 co_assets,recompute 时直接 `weight / max(1, len(co_assets))`。

`explicit_user_confirmation` 类例外:必须在 prompt 模板里要求用户确认时引用具体 asset_uri,只有被点名的 asset 收到 +1.0,co_assets 列表为空。

### 3.5 attribute 算法(派生 confidence cache)

```python
validated_score = sum(adjusted_weight for ev if adjusted_weight > 0)
contradicted_score = sum(-adjusted_weight for ev if adjusted_weight < 0)
exposure_count = total event count (含 loaded_only)
last_validated = max(ev.timestamp.date() for ev with weight > 0)
```

### 3.6 evidence_version 升级流程

改 SPEC §11.4 默认 trust_weight 表 → `EVIDENCE_VERSION` +1 → 所有 cache 行的 `evidence_version` 字段过期 → Relevance Gate 走中性默认 → `engram graph rebuild --recompute-confidence` 触发批量重算。

不允许在不升 `EVIDENCE_VERSION` 的情况下偷偷改默认值。

## 4. confidence 对 Relevance Gate 的影响

DESIGN §5.1 Stage 6 ranking 公式追加 `confidence_multiplier`:

```
multiplier = clip(0.5, 1.5, 1.0 + (validated_score - contradicted_score) / max(exposure_count, 1))
```

- 上下界 [0.5, 1.5] 防止单条 asset 因 confidence 完全屏蔽 / 完全压倒其他信号
- mandatory bypass(Stage 1)**不受** confidence 影响 —— mandatory 是规则,不是知识
- exposure_count = 0 时 multiplier = 1.0(中性)

## 5. 兼容 + 迁移(`engram migrate --from=v0.2 --to=v0.2.1`,T-186)

| 老字段 | 新行为 |
|---|---|
| `validated_count: N` | 写 `validated_score: N * 0.5` 到新 schema(假设老计数对应 mid-trust 信号) |
| `contradicted_count: N` | 同上,`contradicted_score: N * 0.5` |
| `last_validated: D` | 直接保留 |
| `usage_count: N` | 改为 `exposure_count: N` |
| 缺整个 confidence 块 | 写零态块(SPEC §13 additive default) |

迁移完成后跑 `engram graph rebuild --recompute-confidence`(可选)用真实 usage.jsonl 历史(老 store 一般为空)覆盖估算值。

## 6. 现有实现状态(T-170 / T-171 / T-173 done,2026-04-25)

- ✅ `engram/usage/types.py` — UsageEvent + 4 enum
- ✅ `engram/usage/trust_weights.py` — DEFAULT_TRUST_WEIGHTS 表 + EVIDENCE_VERSION
- ✅ `engram/usage/appender.py` / `reader.py` / `recompute.py`
- ✅ `engram/usage/task_hash.py` — 4 级降级 task_hash 派生
- ✅ `context.py` 接入:每个 included asset emit `loaded_only` event,co_assets 真实填
- ✅ `consistency/resolve.py` 接入:DISMISS 动作 emit `false_positive_dismissed`
- ⏳ `validate.py` 接入待 T-184(mandatory directive)落地后,scope_conflict 触发时 emit `contradicted` 事件(留给 v0.2.1 PR)
- ⏳ frontmatter `confidence` derived cache schema 落 SPEC.md 待 T-185
- ⏳ DESIGN §5.1 Stage 6 confidence_multiplier 落 DESIGN.md 待 T-185

## 7. 不动的事

- 不引入 vector DB / Postgres / 任何专用持久化引擎
- 不在 LLM 推理路径里实时拦截 / 改写 confidence
- 不让 `usage.jsonl` 跨机器自动同步(本地优先;rsync / git 仍是 SPEC §2.3 的兜底方案)
