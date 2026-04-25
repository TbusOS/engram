[English](TASKS.md) · [中文](TASKS.zh.md)

# engram 任务板

**版本目标**：v0.2.0（首次公开发布）及后续版本
**状态**：进行中 — 通过 GitHub Issue 认领任务并自行分配
**最后更新**：2026-04-25
**规范版本**：https://github.com/TbusOS/engram/blob/main/TASKS.md

---

## 1. 理念与使用说明

本文件是**活文档** — 随任务认领、完成、拆分而持续更新，通过 PR 维护。不要把它当成静态规范。如果某任务显示为进行中却没有对应 PR，该任务实际上并未推进。

**状态值**：`todo` / `doing` / `review` / `done` / `abandoned`

**归属**：Owner 列填写 GitHub 用户名；留空 = 可认领。

**依赖**：写明前置 T-ID。依赖项未到 `done` 前不得开始该任务。

**认领**：开一个标题为 `Claim T-XX` 的 Issue，自行分配，然后在实现 PR 里将本文件中的 Owner 和状态改为 `doing`。每个任务只有一个 Owner。

**拆分**：预估工作量超过 3 天的任务，在开始前必须拆分。子任务 ID 形如 T-11a、T-11b，与父任务行并列放置。父任务行保留，Notes 列指向子任务。

**讨论层级**：
- 方向性讨论（里程碑顺序、P2 升级为 P1）→ GitHub Discussions
- 任务级澄清（需求模糊、被阻塞）→ 该 T-ID 对应的 Issue
- 代码审查 → PR 本身

**完成标准**：单测通过 + 集成测试通过（视情况而定）+ 功能出现在 `--help` 输出中，或按照 DESIGN.md 文档可通过 MCP 工具访问。只有合并后才能将状态改为 `done`。

**Abandoned（已放弃）**：如果某任务不再推进，将状态改为 `abandoned` 并在 Notes 中说明原因。保留该行，不要删除。

---

## 2. 里程碑概览

| 里程碑 | 目标 | 退出的硬门槛 |
|--------|------|-------------|
| **M1** — SPEC + DESIGN 冻结 | v0.2 SPEC 和 DESIGN 经过外部审核并冻结 | 5 位以上外部读者 + 所有审核 Issue 已解决 |
| **M2** — CLI 核心 | `engram init / status / version / validate / review / memory (CRUD)` 端到端可用 | 空项目 → init → 添加 10 条记忆 → validate 全绿 |
| **M3** — 范围 + 池 + 迁移 | 全部 4 个层级范围 + 池订阅 + `migrate --from=v0.1` 端到端可用 | 真实 v0.1 存储无数据丢失地完成迁移 |
| **M4** — 智能层 Phase 1-2 + 适配器 + MCP | 相关性闸门 + 一致性引擎 Phase 1-2 + 跨仓传信器 + Claude Code / Codex / Gemini CLI / Cursor / raw-api 适配器 + MCP 服务（读工具） | engram-cli 可通过 pip 安装；全部 P0 CLI 命令通过 E2E |
| **M4.5** — 基准测试基础设施 | `benchmarks/BENCHMARKS.md` + consistency_test + scope_isolation_test + docs/HISTORY.md | 结果可从已提交脚本中复现 |
| **M4.6** — 越用越好用 12 周主线（v0.2.1 + 6 条 wisdom 曲线 + Evolve 种子） | 入口零摩擦 + usage 事件总线 + 6 条 SPEC-AMEND + LOCOMO/LongMemEval 基线 + RRF/rerank + Consistency Phase 3/4 + Evolve Engine MVP | `engram wisdom report` 6 条曲线渲染出来；README 顶部贴 LOCOMO 跑分对比表;一个 workflow 自学习 10 轮单调提升。详细周计划见 `docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md` |
| **M5** — 工作流 + 自学习 | 工作流资产完整 + 自学习引擎棘轮 + 阶段闸门 | 单个工作流自学习 10 轮，指标单调提升 |
| **M6** — 知识库 + 收件箱 + 一致性引擎 Phase 3-4 | 知识库编译 + 收件箱完整 + 语义一致性 + 执行一致性阶段 | 跨仓 bug-report → 确认 → 解决 完整流程可用；知识库 `_compiled.md` 自动标记过期 |
| **M7** — Web UI P0 | engram-web 6 个 P0 页面（总览面板、记忆详情、工作流详情、知识文章、收件箱、上下文预览） | `engram web serve` → 点击 6 个页面 → 无 500 错误；WCAG AA 检查通过 |
| **M8** — 演化 + 团队完整 + TS SDK + 剩余 Web UI + 迁移源 | 演化引擎、池传播 notify+pinned、智慧指标面板、TypeScript SDK、剩余 5 个 Web UI 页面、6 个额外迁移源、剧本命令族 | 覆盖 DESIGN §13.2 的全部 P1 范围 |

M8 完成后，工作转向 DESIGN §13.3 中的 P2 项目：多机器同步守护进程、本地小模型重排序、Obsidian 插件、IDE 深度集成、多语言嵌入向量。这些均无需修改 SPEC。列出它们是为了避免贡献者重复提出已有记录的设计问题，并非已排期里程碑。

---

## 3. 任务列表

### M1 — SPEC + DESIGN 冻结

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-01 | 编写 SPEC v0.2 全部 14 章 | done | | | 14 章已在 main 分支 |
| T-02 | 编写 DESIGN v0.2 全部 14 章 | done | | | §0–§13 已在 main 分支 |
| T-03 | 建立 docs/glossary.md + docs/superpowers/plans/ | done | | | |
| T-04 | 将 v0.1 归档至 docs/archive/v0.1/ | done | | | |
| T-05 | 建立 GitHub Pages 落地页（中英双语） | done | | | docs/index.html 已上线 |
| T-06 | 制作 Web UI 静态效果图（11 页，中英双语） | done | | | docs/design/ 静态页面 |
| T-07 | SPEC + DESIGN 外部审核 — 至少 5 位读者 | todo | | T-01, T-02 | 开 GitHub Discussion 征集审核者；将反馈汇总为 Issue |
| T-08 | 解决 T-07 产生的全部审核 Issue | todo | | T-07 | 每个 Issue 关闭前需有解决说明 |
| T-09 | 审核 Issue 全部关闭后打 v0.2.0-pre 标签 | todo | | T-08 | 触发 M2 实现工作 |

---

### M2 — CLI 核心

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-10 | cli/ 骨架：pyproject.toml + click 集成 + 包骨架 | done | | T-09 | 入口点 `engram`；版本来自 pyproject；`pip install -e "cli[dev]"` 可用。T-09 硬门槛按路径 B 搁置（M1 外审与 M2 骨架并行） |
| T-11 | `engram/core/paths.py` — 项目根目录探测 + ENGRAM_DIR 支持 | done | | T-10 | `find_project_root` 从 cwd 向上走找 `.memory/`；`ENGRAM_DIR` 环境变量短路；另外 `user_root`、`memory_dir`、`engram_dir` 三个工具函数。单测 100% 覆盖 |
| T-12 | `engram/core/frontmatter.py` — YAML 解析 + 按 SPEC §4.1 校验 | done | | T-10 | 类型化 `MemoryFrontmatter` + `Confidence` dataclass(frozen+slots)+ 3 个 enum;严格校验 required / enum / scope-conditional(org/team/pool/subscribed_at)/ 子类型专属(feedback→enforcement、workflow_ptr→workflow_ref、agent→source)/ confidence 块。未知字段按 SPEC §4.1 要求保留到 `extra`(不抛异常 —— SPEC 优先于任务条目早期措辞)。39 单测,96% 覆盖率 |
| T-13 | `engram/core/fs.py` — 原子写入 + 锁 + 符号链接 | done | | T-10 | `write_atomic(path, content)` tempfile+fsync+os.replace；`acquire_lock(path)` fcntl.flock 上下文管理器(exclusive/shared 两种模式);`atomic_symlink(target, link)` 同目录 tmp symlink + rename 替换。仅 POSIX(macOS+Linux)。19 单测含线程串行化测试,93% 覆盖 |
| T-14 | `engram/core/graph_db.py` — 按 DESIGN §3.2 建 SQLite schema + WAL 模式 + 迁移 | done | | T-10 | `open_graph_db(path)` 上下文管理器应用 PRAGMA journal_mode=WAL / synchronous=NORMAL / foreign_keys=ON。DESIGN §3.2 全部 7 张表(assets / references_ / subscriptions / inbox_messages / consistency_proposals / usage_events / schema_version)+ 5 个 index 通过 SCHEMA_VERSION 键控的前向迁移框架建立。AssetRow dataclass + insert_asset / get_asset / list_asset_ids 辅助函数(其他表留给各自消费任务)。19 单测 98% 覆盖。说明:原任务行说"assets / references / scopes / journal"措辞不准,DESIGN §3.2 为权威,实际不存在 scopes / journal 表(journal 是 §3.4 磁盘 JSONL) |
| T-15 | `engram/core/journal.py` — 追加式 JSONL 辅助函数 | done | | T-10 | `append_event(path, event)` 带 fcntl.flock(50×20 并发写入 1000 事件无丢失无损坏);`read_events(path)` 生成器跳过空行、拒非对象事件、解析错误带行号。16 单测,100% 覆盖 |
| T-16 | `engram/cli.py` — click 主调度器 + 全局标志 | done | | T-10 | 根 group 接 `--dir PATH` / `--format {text,json}` / `--quiet -q` / `--debug`。类型化 `GlobalConfig`(frozen dataclass)挂 `ctx.obj`。`resolve_project_root()` 按 DESIGN §9.3 顺序(--dir > ENGRAM_DIR > cwd 向上走)。日志级别从 flag 派生(debug>quiet>info)。21 单测,98% 覆盖 |
| T-17 | `engram init` — 交互式 + 非交互式两种模式 | done | | T-11, T-13 | `engram init` + 纯函数 `init_project()` 建 `.memory/{local,pools,workflows,kb}/` + `.engram/version=0.2` + 符合 SPEC §7.2 结构的 `MEMORY.md` 骨架 + `pools.toml` 占位。`--name` 覆盖目录名;`--no-adapter` 预留 no-op(T-55 补完);`--force` 改写骨架但保留用户在 local/workflows/kb 下的内容。19 单测含 E2E,命令 100% 覆盖。seeds 目录内容待定 —— 仓库里 seeds/ 仍是占位 |
| T-18 | `engram version` + `engram config get/set` | done | | T-16 | `version` 输出 CLI semver + store schema + Python + 平台(text/json)。`config get/set/list` 读写 `~/.engram/config.toml`(tomli + tomli-w);点分 key 映射嵌套 TOML 表;值自动推断(true / 42 / 3.14 / str);写入走 write_atomic 原子;缺失 key 抛 ConfigKeyError。40 单测 97% 新代码覆盖 |
| T-19 | `engram memory add / list / read / update / archive / search` | done | | T-11, T-12, T-13, T-14 | 6 个子命令全部可用。add:flag 驱动,通过 frontmatter 往返强制 SPEC §4.1 子类型字段;--body 接受 `-` 读 stdin;--force 覆盖。list:text 表格 + json。read:文件 text + json frontmatter/body。update:--description / --body / --enforcement / --lifecycle / --tags,自动刷新 `updated` 日期。archive:移动文件到 `~/.engram/archive/YYYY/MM/` 并翻 lifecycle_state。search:纯 Python BM25 打 name+description+body,--limit,text + json。**M2 决定**:graph.db 在 `<project>/.engram/graph.db`(DESIGN §3.2 写的是 `~/.engram/graph.db` 但有跨项目唯一性 schema 缺口,M3 重审)。45 单测,memory.py 94% 覆盖 |
| T-20 | `engram validate` — 执行全部 SPEC §12 规则；JSON + 文本输出；CI 友好退出码 | done | | T-12, T-14 | M2 子集:STR(§12.1)、FM(§12.2)、MEM(§12.3)、IDX(§12.6)、REF(§12.9)。SCO/ENF/POOL/INBOX/WF/KB/CONS 各自消费任务补齐。text + JSON 按 §12.13 输出;退出码 0 干净 / 1 警告 / 2 错误(原任务行把 1 和 2 写反,SPEC §12.13 为准)。35 单测,validator 93% 覆盖 |
| T-21 | `engram review` — 综合健康状况摘要 | done | | T-14, T-20 | 包 run_validate + graph.db 资产统计。类型化 `Review` dataclass(total_assets / by_subtype / by_lifecycle / by_severity / by_category / issues)。text:Assets + Validation issues 按严重度/分类分组。json:嵌套 {assets, validation}。**始终 exit 0**(信息性,不当 CI 门)。11 单测,100% 覆盖 |
| T-22 | `engram status` — 项目 + 范围摘要 | done | | T-11, T-14 | 读 `.engram/version` + `.memory/pools.toml` + `.engram/graph.db`。类型化 `Status` dataclass(project_root / initialized / store_version / total_assets / by_subtype / by_lifecycle / pool_subscriptions)。未初始化(提示 `engram init`);pools.toml malformed 容错。text + json;始终 exit 0。10 单测,94% 覆盖 |
| T-23 | 全部核心模块单测（pytest + 80% 覆盖率） | done | | T-11, T-12, T-13, T-14, T-15 | 在 T-11~T-15 每个任务里 TDD 同步完成:paths 100% / frontmatter 96% / fs 93% / graph_db 98% / journal 100%。T-23 作为里程碑 checkpoint 翻 done |
| T-24 | E2E 测试：空项目 → init → 添加 10 条记忆 → review/validate 全绿 | done | | T-17, T-19, T-20, T-21 | `tests/e2e/test_m2_smoke.py` 跑完整 M2 流程:init → add×10(5 子类型:user/feedback/project/reference/agent)→ list → search → validate(errors==0)→ review(10 资产,5×2 subtype)→ status + 第二条 smoke 验 update + archive 往返。另 subprocess 级 `engram --version` smoke。"全绿"定义为 `errors==0`;agent 上的 W-MEM-002 警告是预期的(confidence flag 留到 M2 polish 或 M5) |

---

### M3 — 范围 + 池 + 迁移

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-30 | `engram/pool/` 模块 — 按 SPEC §8/§9 实现订阅/取消订阅/列表 | done | | T-13, T-14 | `commands/pool.py` 含 subscribe/unsubscribe/list。按 SPEC §9.2 写 `[subscribe.<name>]` 到 pools.toml(修掉了 T-17 init 用的错误 `[[subscription]]` schema,T-22 status 读取同步更新)。通过 `atomic_symlink` 建 `.memory/pools/<name>` 软链。严格校验:pool 不在 `~/.engram/pools/<name>/` 则报错。--at(org/team/user/project)、--mode(auto-sync/notify/pinned)、--revision(pinned 必填)、--force。15 单测,整库 306 条通过 |
| T-31 | `engram/pool/propagation.py` — 仅实现自动同步模式 | done | | T-30 | commands/pool.py 里做符号链接目标解析:auto-sync/notify → `rev/current`(无 rev/ 时回退到 pool 根);pinned → `rev/<revision>/`(必须存在)。`engram pool sync [name | --all]` 刷 `last_synced_rev` + 追加 `propagation_completed` 事件到 `~/.engram/journal/propagation.jsonl`(SPEC §9.4)。pinned 订阅跳过。subscribe 现在自动从当前 rev 记 last_synced_rev。13 新单测,整库 319 通过 |
| T-32 | `engram/pool/git_sync.py` — 基于 git 的池同步 | done | | T-30 | `engram pool pull [<name> | --all]` 通过 subprocess 跑 `git pull --ff-only`;用 `git diff --name-status` 比对 before/after HEAD,报告 added/modified/removed 计数。pool 代码重构为 `engram/pool/{subscriptions,propagation,git_sync,commands}.py` 多文件结构(DESIGN §4.2)。9 新单测(用真实 git 仓库,git 不在时跳过),整库 328 通过 |
| T-33 | `engram/team/` + `engram/org/` — join / sync / publish / status | done | | T-14, T-30 | 抽出 `engram/core/git.py`(run_git / head_sha / diff_name_status / pull_ff / clone / commit_all / push / status_porcelain)—— pool 同步也用。`engram/scope/{git_ops,factory}.py` 抽共享 team/org 逻辑;`engram/team/__init__.py` + `engram/org/__init__.py` 选 kind 并导出 click group。命令:join `<name> <url>` / sync `[<name> | --all]` / publish `<name> --message` / status `<name>` / list。32 个参数化测试(真实 git),整库 360 通过 |
| T-34 | `engram/migrate/v0_1.py` — SPEC §13.4 合约；dry-run + 正式迁移 + 回滚 | done | | T-12, T-13 | `engram/migrate/{__init__, commands, v0_1}.py` 多文件(DESIGN §4.2)。`engram migrate --from=v0.1` 支持 --dry-run / --rollback。写任何文件前先建 `.memory.pre-v0.2.backup/`;flat `*.md` 挪进 `local/`;注入 `scope: project`;feedback 加 `enforcement: default`;agent 加零态 `confidence`(SPEC §13.4 写 `{}` 但解析器要子字段,按 §13.7 "additive default" 原则用零块)。未知字段保留;MEMORY.md 重建并按 type 归类到 Identity / Always-on rules / Topics;迁移事件写入 `~/.engram/journal/migration.jsonl`;幂等重入。26 单测 + CLI smoke,整库 386 通过,94% 覆盖 |
| T-35 | E2E：用真实 20 条记忆样本测试 v0.1 存储迁移 | done | | T-34 | `tests/fixtures/v0.1_store/` 20 条通用示例(3 user / 5 feedback / 5 project / 4 reference / 3 agent)+ v0.1 `MEMORY.md` + 2 个自定义 frontmatter 字段(`priority` / `origin_tool`)+ unicode 正文。`tests/e2e/test_m3_migration_e2e.py` 14 个测试断言:(a) dry-run 不改磁盘,(b) 迁移后每条 body 字节一致,(c) v0.1 所有 fm key 全部保留,(d) `scope: project` / `enforcement: default` / 零态 `confidence` 按需注入,(e) 备份与原始 byte-for-byte 相同,(f) migration journal 记录 20 条,(g) 迁移后 validate errors=0,(h) rollback byte-for-byte 还原,(i) 再跑一次是 no-op。同时修掉 `plan_migration` 的 bug(把 `MEMORY.md` 当资产,dry-run 报 21 条,实际迁 20 条)。+14 测试,整库 400 通过 |
| T-36 | 更新 `engram init` 以支持 `--subscribe=<pool>` 和 `--org` / `--team` | done | | T-17, T-30, T-33 | `--subscribe <pool>`(可重复)写入 `[subscribe.<pool>]` 并创建 `.memory/pools/<pool>` 符号链接。`--org <name>` / `--team <name>` 断言该范围已经 join 到 `~/.engram/<kind>/<name>/.git`,否则给出可操作的错误(提示 `engram <kind> join`)。前置校验在写 scaffold 之前完成,避免误用留下半初始化的项目。抽出 `engram/pool/actions.py::subscribe_to_pool` 作为订阅的规范函数,`engram pool subscribe` 现在委托调用它,init 和 pool 子命令共用一条代码路径。11 新增单测,整库 411 通过 |
| T-37 | `pools.toml` schema 校验（在 `engram validate` 中） | done | | T-20, T-30 | 新增 `engram/commands/validate_pool.py` POOL 家族规则。SPEC §12.10 既有编号:E-POOL-001(pinned 无 revision)、E-POOL-002(订阅池在 `~/.engram/pools/<name>/` 缺失)、E-POOL-003(auto-sync/notify 指向的 rev/current 悬挂)、W-POOL-002(池缺 `.engram-pool.toml`)。新增编号(在 commit 说明中记为 SPEC §12.10 扩展):E-POOL-000(pools.toml 解析失败以 Issue 形式暴露,不再抛异常)、E-POOL-004(subscribed_at 枚举)、E-POOL-005(propagation_mode 枚举)、E-POOL-006(非 pinned 模式带 pinned_revision)、E-POOL-007(pinned_revision 指向不存在的 rev 目录)。延后:W-POOL-001(需要 propagation engine)/ W-POOL-003(需要 pool manifest 的 publisher 字段)。+14 测试,整库 425 通过 |
| T-38 | `engram memory search` 中的范围感知相关性排序 | done | | T-19, T-30, T-33 | `engram/commands/memory.py` 导出 `SCOPE_WEIGHTS`(project=1.5 / user=1.2 / team=1.0 / org=0.8 / pool 默认 1.0,DESIGN §5.1 Stage 6)和 `ENFORCEMENT_WEIGHTS`(mandatory=2.0 / default=1.0 / hint=0.5)。`apply_scope_weighting(ranked, meta)` 把两个乘子叠到 BM25 原始分上;`scope=pool` 的资产按它在 `subscribed_at` 的层级取对应权重。未知枚举值降级为 1.0(不崩)。`engram memory search` JSON 现在每条 hit 返回 `raw_score` / `score` / `scope` / `enforcement`;文本输出每行尾加 `[scope/enforcement]` 标签。M3 用乘子而不是 M4 Relevance Gate 的 Stage-1 mandatory bypass,这个选择的理由在代码里写了。+11 测试,整库 436 通过 |
| T-39 | 按 SPEC §8.4 决策树测试范围冲突解决 | done | | T-30, T-33, T-38 | 新增 `engram/core/scope_conflict.py`,纯函数 `resolve_conflict(candidates) -> Resolution` 编码 §8.4 五条规则(enforcement 绝对优先 → hierarchy specificity → native-before-pool → LLM 仲裁 → 同池内部冲突 raise)。公开 `ConflictCandidate` / `Resolution` / `PoolInternalConflict`。`tests/unit/cli/test_scope_conflict.py` 20 个场景(超过 15+ 要求):arity 边界、§8.4 四个 worked example、rule 1 压过 rule 2、每个层级的 pool vs native、每个 enforcement 层级的 rule 4 仲裁、rule 5 同池冲突。函数无副作用,M4 Relevance Gate(T-40)和后续 `engram review` 都会直接 import。+20 测试,整库 456 通过,ruff + mypy 全绿 |

---

### M4 — 智能层 Phase 1-2 + 适配器 + MCP

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-40 | `engram/relevance/gate.py` — DESIGN §5.1 七阶段管道 | done | | T-14, T-42, T-43 | 纯函数 `run_relevance_gate(RelevanceRequest) -> RelevanceResult`。六阶段落地:mandatory 绕过(Stage 1) → BM25 recall(Stage 2 / T-42) → 向量 recall(Stage 3,T-41 占位,pass-through) → 时间加权(Stage 4 / T-43) → scope + enforcement 权重(Stage 5,从 `relevance/weights.py` 取常量) → 按 score/token 贪心填预算(Stage 6)。零分文档被丢弃;mandatory 资产和 ranked 列表分开返回。**关键 design**:recency 衰减 + temporal 乘子都绑在"query 里有时间 phrase"这个条件上 —— 没有 "yesterday" / "last week" 的 query 不会把老的精心编辑的规则衰减掉。+11 测试 |
| T-41 | `engram/relevance/embedder.py` — 本地默认 bge-reranker-v2-m3 + 云端提供商配置 | todo | | T-40 | 首次使用时惰性加载模型；模型缺失时降级为仅 BM25 |
| T-42 | `engram/relevance/bm25.py` + 停用词表 | done | | — | 新模块。`STOP_WORDS` frozenset(32) + `MIN_TOKEN_LENGTH=3`,DESIGN §17。`tokenize()` 小写化,按非 alnum 切分,过滤停用词和短 token。Okapi-BM25 k1=1.5 b=0.75(MemPalace 基线);零分文档直接丢弃,不挂 0。`engram.commands.memory` 继续 re-export `bm25_scores`,老测试不动。+16 测试 |
| T-43 | `engram/relevance/temporal.py` — "N 周前"解析 + 时间邻近加权 | done | | — | 新模块。`parse_temporal_hint(query, now)` 识别 today / yesterday / last week / last month / N {days,weeks,months} ago,返回最早匹配的参考日期或 None。`temporal_distance_multiplier(candidate, reference)` 在 `[0.6, 1.0]`;30 天窗口内线性衰减(0 天 → 0.6 即 40% 距离削减,≥30 天 → 1.0)。月按 30 天算,确保可重现(日历感知留到 M5+)。+18 测试 |
| T-44 | 相关性闸门中的范围 + 强制级权重 + 时效衰减 | todo | | T-41, T-42, T-43 | DESIGN §9 中的 `confidence_score` 驱动时效衰减 |
| T-45 | 相关性缓存 — LRU，按 DESIGN §3.3 | done | | T-40 | `engram/relevance/cache.py`。`RelevanceCache` 类,OrderedDict LRU + 每条记时戳 TTL。`cache_key(request)` SHA256 合入(query / budget / now / 资产 id+scope+enforcement+subscribed_at+updated+size_bytes 升序排列)。默认 TTL=300s(DESIGN §3.3)+ max_entries=128。TTL=0 永不过期。过期项在 read 时回收。hit 时 LRU touch。stats API 返回 hits/misses/size/max。+15 测试 |
| T-46 | `engram/consistency/engine.py` — 四阶段调度器 | done | | T-14 | `engram/consistency/` 多文件(DESIGN §4.2):`engine.py` 调度器 + `types.py`(ConflictClass 枚举 7 类、ConflictReport、Resolution、ResolutionKind、ConsistencyReport)+ `phase1_static.py`(包 validate,映射 E-IDX-001 / E-REF-001 / 003 → REFERENCE_ROT)+ `phase2_semantic.py`(body-hash 重复 → FACTUAL;名字 OPPOSITES 对撞检测 → RULE)+ `phase3_references.py` / `phase4_staleness.py` 显式 stub 并写明不做的理由 + `evaluator.py` 确定性规则评分器(按产品化计划 §3 GAN 模式:拒绝对 team/org 范围的 ARCHIVE 提案 SPEC §8.3,拒绝缺 related 的 SUPERSEDE/MERGE,拒绝瞄错资产的 UPDATE)。`run_consistency_scan(store_root) -> ConsistencyReport` 返 phase_counts + evaluator_rejected 计数。+14 测试 |
| T-47 | `engram/consistency/phase1_static.py` — 写入时静态 SPEC §12 错误检测 | todo | | T-12, T-46 | 7 个冲突类别；返回结构化 ConflictReport 列表 |
| T-48 | `engram/consistency/phase2_semantic.py` — DBSCAN 聚类 + 6 条聚类规则 | todo | | T-41, T-46 | 按嵌入向量聚类；检测事实冲突和同题分歧 |
| T-49 | `engram/consistency/resolve.py` — 6 种处置方式实现 | done | | T-47, T-48 | `engram/consistency/resolve.py`:`apply_resolution(store_root, Resolution, *, consent=False) -> ApplyResult`。默认 dry-run(SPEC §1.2 原则 4) —— 必须 `consent=True` 才碰磁盘。6 种处置:ARCHIVE(挪到 `~/.engram/archive/<YYYY-MM>/`)/ DISMISS(不动文件,只记 journal)/ ESCALATE(写 `~/.engram/escalations/<ts>-<slug>.md`)/ SUPERSEDE(目标里注入 `supersedes:` + 归档被替代者)/ MERGE(把源 body 追加到目标 + 归档源)/ UPDATE(写 `.proposed.md` 兄弟文件,原文件绝不动)。每次真正执行都 append 一条 `consistency-resolve` 事件到 `~/.engram/journal/consistency.jsonl`,可审计。+10 测试 |
| T-50 | `engram/inbox/` — SPEC §10 Inter-Repo Messenger + 去重 + 频率限制 | done | | T-14, T-15 | `engram/inbox/` 多文件(identity / messenger / lifecycle / list_)+ `engram/commands/inbox.py` CLI。repo-id 解析:`.engram/config.toml` `[project] repo_id` > git remote SHA-256 前缀 > 路径哈希(SPEC §10.6)。发送写到 `~/.engram/inbox/<recipient-slug>/pending/<ts>-from-<sender-slug>-<topic>.md`,frontmatter 按 §10.2。三级去重:显式 `dedup_key` > 排序 `related_code_refs` 哈希 > `from + 首行` 兜底;重复追加 body 段落 + `duplicate_count` 自增 + `message_duplicated` 事件。速率限制按 **SPEC §10.5 默认(20 pending / 50 每 24h)**,TASKS 老条目写的 "10/每天" 按权威链覆盖。生命周期:ack/resolve/reject 移动文件 + 改 frontmatter + journal + 拒绝终态后续转移(§10.4 单向)。`resolve` 必须带非空 note;`reject` 必须带非空 reason。`list_messages` 按 severity → intent → deadline → created 排序(§10.3)。CLI:`engram inbox {send,list,acknowledge,resolve,reject}`。+21 测试 |
| T-51 | `engram/mcp/server.py` — 无状态 MCP 服务（stdio + SSE 传输） | done (stdio 已落地) | | T-14, T-40 | `engram/mcp/server.py` 无状态 line-delimited JSON-RPC 2.0 over stdio。协议版本 2024-11-05。方法:`initialize` / `tools/list` / `tools/call` + notification 静默 ack。纯函数 `dispatch(payload, ctx) -> response` + 薄 `serve_stdio` 驱动。零非必要依赖(直接实现 wire 协议,不拉 MCP SDK)。`engram mcp serve` CLI 命令。SSE transport 延后。+13 测试(握手 / tools 列举 / 真实 store 的 tool call / 错误 envelope / stdio round-trip) |
| T-52 | `engram/mcp/tools.py` — 全部读取 + 收件箱 MCP 工具的 JSON-Schema | done (read 三件套已落地) | | T-51 | `engram/mcp/tools.py` 3 个 read 工具,每个带完整 JSON-Schema `inputSchema`:`engram_memory_search`(BM25 + scope/enforcement 加权 + 分页)/ `engram_memory_read`(asset id → frontmatter + body)/ `engram_context_pack`(透传 Relevance Gate + 预算)。Inbox 工具 `engram_inbox_list` / `engram_inbox_send` 留给 T-50 Inter-Repo Messenger。`docs/adapter-guides/MCP-CLIENTS.md` 覆盖 Claude Desktop / Claude Code CLI / Opencode / Codex / Zed / Cursor / VS Code(Continue.dev / Cline / Copilot)全部配置片段 |
| T-53 | `adapters/claude-code/` + hooks：`engram_stop.sh` + `engram_precompact.sh` | done | | T-40 | `adapters/claude-code/hooks/engram_stop.sh` + `engram_precompact.sh`(两者 best-effort <500ms,DESIGN §20,失败静默降级)+ `adapters/claude-code/README.md` 安装说明。CLAUDE.md 通过 `engram adapter install claude-code` 落地 |
| T-54 | `adapters/codex/` + `adapters/gemini-cli/` + `adapters/cursor/` + `adapters/raw-api/` | done | | T-53 | 共 5 个适配器在 `engram/adapters/registry.py`:claude-code → CLAUDE.md / codex → AGENTS.md(与 Opencode 共用)/ gemini-cli → GEMINI.md / cursor → `.cursor/rules/engram.mdc`(带 MDC frontmatter)/ raw-api → ENGRAM_PROMPT.md。都共享 `_COMMON_BODY` 模板(memory 系统概览 / enforcement 语义 / 工具 + 写入接口 / 交互规则)。Cursor 版本包上 `alwaysApply: true` MDC frontmatter |
| T-55 | `engram adapter <tool>` CLI — 生成 + 使用标记边界更新 | done | | T-53, T-54 | `engram/adapters/renderer.py::apply_managed_block` 容忍 3 种初始形态:空文件 → 写块;有用户内容无标记 → 前置块;已有标记 → 替换最外层 BEGIN/END 之间(多余标记对自动合并为一个区域)。CLI 子命令:`engram adapter list` / `install <name>` / `refresh [<name>]`(不带参数刷新所有已装)。标记外用户内容 refresh 时字节保留。+17 测试(7 renderer + 10 CLI 含 hook 文件存在断言) |
| T-56 | `engram context pack` — DESIGN §6.3 输出格式 | done | | T-40 | `engram/commands/context.py`:`engram context pack --task=<text> [--budget=<tokens>] [--format=prompt\|json\|markdown]`。从 graph.db 装载项目 memory → 过 Relevance Gate → 三种输出:`prompt`(mandatory + ranked 两段,直接 pipe 进 LLM)/ `json`(结构化给 MCP/SDK)/ `markdown`(人类预览,含 bm25 × scope × enforcement 分解)。mandatory 永远最前(DESIGN §5.1 Stage 1);ranked 尾巴按 token 预算截断。+7 测试 |
| T-57 | E2E：全部 P0 CLI 等价测试 | todo | | T-19, T-20, T-22, T-30, T-50, T-51, T-55 | 针对 fixture 存储运行全部 P0 命令；断言退出码 + 输出格式 |

---

### M4.5 — 基准测试基础设施

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-58 | `benchmarks/BENCHMARKS.md` — 模板（MemPalace 规范：变更前建立基线，追踪增量） | todo | | T-57 | 包含可复现说明；CI 仅在发布标签上运行 |
| T-59 | `benchmarks/consistency_test/` — 50 个合成样本 × 7 个冲突类别 | todo | | T-47, T-48 | 每类 7–8 个样本；每个样本是一对资产 + 预期 ConflictReport |
| T-60 | `benchmarks/scope_isolation_test/` — 30 个范围场景 | todo | | T-38, T-39 | 覆盖强制级/默认级/建议级交互 + 池 subscribed_at 层级 |
| T-61 | `docs/HISTORY.md` — 修正日志起始条目（每次基准测试运行一条记录） | todo | | T-58 | 格式：日期、指标名称、变更前、变更后、原因 |
| T-62 | CI hook：基准测试仅在发布标签时运行（不在每次提交时运行） | todo | | T-58, T-59, T-60 | GitHub Actions job 由 `v*` 标签触发；结果追加至 HISTORY.md |

---

### M4.6 — 越用越好用 12 周主线 sprint

**权威 spec**: `docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md`。共 12 周节点,T-ID 按周分组。

#### 第 1 周 — 入口零摩擦(降 C3 用户写入摩擦)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-160 | `engram memory quick "<body>"` 一行命令(issue #2) | todo | | T-19 | name/description 从 body 自动派生(首行 ≤80 字符 / 前 150 字符);`--type` 默认 `project`;`--scope` 默认 `project`;name 冲突自动加 `-1/-2/...` 后缀;派生资产必须 validate 零 error 零 warning |
| T-161 | `engram init --adopt` 默认接管已有 `.memory/`(issue #1) | todo | | T-17 | 检测到 SPEC-compliant `.memory/` 时跳过 MEMORY.md 写;扫描 `local/`/`workflows/`/`kb/` 把合法 frontmatter 资产注册到 graph.db;非法文件给 warning,不阻断 |
| T-162 | `engram doctor` 体检 + 可执行修复建议 | done | | T-20, T-21 | `engram/doctor/` 多文件(types + 5 类检查:layout / graph_db / index / pools / mandatory_budget) + `engram/commands/doctor.py` CLI。每个 issue 带 `code`(DOC-LAYOUT-* / DOC-GRAPH-* / DOC-INDEX-* / DOC-POOL-* / DOC-MAND-*) + severity + message + `fix_command`(可执行 shell)。confidence 异常等 T-170 usage bus 落地后补。12 单测,整库 668 |
| T-163 | `engram mcp install --target=<client>` 一键写 MCP 配置 | done | | T-51 | `engram/mcp/install.py` 9 个 target registry,两种 action:**write**(claude-desktop / cursor / zed —— JSON 深合并入稳定配置文件)+ **paste**(claude-code / codex / opencode / vscode-{continue,cline,copilot} —— 配置位置不稳定的客户端只打印 snippet 给用户手贴)。幂等(重装不重复 engram entry)。`--list` 枚举,`--dry-run` 打印计划不写盘。19 单测,整库 687 |

#### 第 2 周 — usage 事件总线(整个学习神经系统的脊柱)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-170 | `engram/usage/` 模块 — append-only `~/.engram/journal/usage.jsonl` | done | | T-15 | `engram/usage/` 多文件(DESIGN §4.2):types(UsageEvent + 3 enum + 8 EvidenceKind 值)/ trust_weights(DEFAULT_TRUST_WEIGHTS 权威表按 issue #9 + EVIDENCE_VERSION)/ appender(对 journal.append_event 的类型化包装)/ reader(按 asset_uri/task_hash/event_type/actor_type/evidence_kind 过滤)/ recompute(derive_confidence_cache,co_assets 平摊:weight / N per asset)。14 单测,整库 701 |
| T-171 | 所有写入路径接入 usage bus | todo | | T-170 | `context.py` 记 `loaded` 事件 + `co_assets`;`consistency/resolve.py` 记 dismiss 理由;`validate.py` 记 mandatory 覆盖事件 |
| T-172 | trust_weight 表权威定义入 SPEC §11.4 | todo | | T-170 | 8 类 evidence_kind × 默认 trust_weight(explicit_user_confirmation=+1.0 ...);每类带 SPEC 测试 fixture |
| T-173 | task_hash 自动从 git context 派生 | todo | | T-170 | 读 HEAD SHA + branch + GH issue 编号(commit message 解析);兜底用时间窗 bucket。CLI / MCP 都不要求用户填 task_hash |

#### 第 3-4 周 — v0.2.1 SPEC-AMEND PR 包(6 条 issue 一次合)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-180 | graph.db canonical URI(issue #4) | todo | | T-14, T-161 | `(store_root_id, scope_kind, scope_name, asset_path)` URI;`store_root_id` = git remote SHA-256 前缀或路径 hash(复用 inbox repo-id);`assets` 主键改为 `canonical_uri`;旧 `id` 保留作 scope 内便利字段 |
| T-181 | MEMORY.md reachable vs directly-listed(issue #5) | todo | | T-20 | SPEC §7/§11/§12 amend:每个 asset 从 L1 在 2 跳内可达;新增 frontmatter 字段 `primary_topic`(必填) + `tags`(可选);conformance INV-I1 拆为 reachability 检查 + INV-I3 no-duplicate-primary |
| T-182 | ambiguous_conflict 协议(issue #6) | todo | | T-39 | SPEC §8.4 rule 4 改 `ambiguous_conflict`(无 winner);可选 `[source_priority]` 表恢复确定性;LLM 不再进协议层决议;gate.py 输出 ambiguous 标记 |
| T-183 | pool notify 模式拆 accepted/available revision(issue #7) | todo | | T-31 | pools.toml 新增字段;新命令 `engram pool accept <name> [--rev=]` / `engram pool diff <name>`;`last_synced_rev` 保留作为只读展示字段 |
| T-184 | mandatory `directive` 字段 + Stage 1 directive bypass(issue #8) | todo | | T-40 | SPEC §4.3 amend:mandatory feedback 必须有 `directive`(≤200 字符);Relevance Gate Stage 1 bypass 只用 `directive`;完整 body 按需加载或 `--include-mandatory-bodies` |
| T-185 | confidence 改为 derived cache + usage bus 联动(issue #9) | todo | | T-170 | SPEC §4.8 frontmatter `confidence` 重定义:`validated_score` / `contradicted_score` / `exposure_count` / `last_validated` / `evidence_version`;工具不能直接改 frontmatter,只能往 usage.jsonl append;`engram graph rebuild --recompute-confidence` 全量重算 |
| T-186 | `engram migrate --from=v0.2 --to=v0.2.1` | todo | | T-180~T-185 | 备份 → 写 `primary_topic`(默认按当前 topic sub-index slug 或 `_unsorted`)→ 写 `directive`(默认取 description / body 第一句)→ 把 `validated_count`/`contradicted_count` 整数迁到 `validated_score`/`contradicted_score`(假设 trust_weight=0.5 / 计数)→ 从 `last_synced_rev` 初始化 `accepted_revision`/`available_revision` |

#### 第 5 周 — LOCOMO + LongMemEval 跑分(C1 基线)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-187 | LOCOMO + LongMemEval wrapper + README 跑分对比表 | todo | | T-152 | `benchmarks/locomo/` + `benchmarks/longmemeval/`;可复现脚本;README 第二屏加 engram vs mem0 vs Letta vs Zep 对比表 |

#### 第 6-7 周 — Relevance 升级到业界 SOTA(提升 C1)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-150r | Stage 3 融合换 RRF(G-01) | todo | | T-40 | Reciprocal Rank Fusion(BM25 排名 + 向量排名);替换硬编码 `fused_dist = dist * (1 - 0.30 * overlap)` |
| T-151r | Stage 7.5 cross-encoder rerank(G-02) | todo | | T-40, T-150r | bge-reranker-v2-m3 对 top-20 过一遍;模型可配置;CPU + GPU 路径都支持 |
| T-188 | `engram wisdom report` ASCII 6 曲线 | todo | | T-170, T-187 | M7 之前的过渡版本;C1-C6 用 ASCII sparkline + 周环比;管道接终端友好 |

#### 第 8 周 — Consistency Phase 3/4 + 自动 merge 提案(提升 C5)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-47r | Consistency Phase 3 references — 全量启用 | todo | | T-46 | Phase 3 从 stub 升级为完整引用图遍历,detect REFERENCE_ROT |
| T-48r | Consistency Phase 4 staleness — 全量启用 | todo | | T-46 | 时间衰减 + DBSCAN 同主题聚类用于 topic-divergence 检测 |
| T-189 | Evaluator 在 body-hash 相似度 ≥ 0.85 时自动 propose MERGE | todo | | T-46 | Phase 2 已检测 body-hash 重复;这条把 MERGE 建议主动浮出;用户仍需确认 |

#### 第 9-12 周(M6)— Evolve Engine(从不退化升级到主动变好)

| ID | 任务 | 状态 | Owner | 依赖 | Notes |
|----|------|------|-------|------|-------|
| T-190 | `engram/evolve/` 模块骨架 | todo | | T-46, T-170 | `Proposal` 抽象 + 4 种具体类型(SPLIT / PROMOTE / DEMOTE / FORK);跟 Consistency Engine 共用 evaluator/journal 接口 |
| T-191 | Workflow fork-and-evaluate 循环 | todo | | T-71, T-72, T-190 | `engram workflow evolve <name> --variants=N --budget=` 从 `rev/` archive 抽 N 变体并发跑 fixtures,按 metrics 排名,top-1 → `rev/proposed`;人 review → promote |
| T-192 | Memory promote/demote 自动提案 | todo | | T-185, T-190 | confidence cache 阈值(如 validated_score ≥ 5.0 + 30 天零矛盾 → 建议 hint→default)触发 Evolve 提案;**永不自动执行** |
| T-193 | `engram autolearn run --duration=Nh` 后台 daemon | todo | | T-190, T-191, T-192 | Karpathy NEVER STOP 有界版本;在指定时间窗循环 evolve + consistency + wisdom recompute;append `journal/autolearn.jsonl`;结束输出汇总报告 |
| T-194 | simplicity criterion 硬规则 | todo | | T-190 | 任何 evolve 提案如果让 asset 体积增加 > 30% 或引用图复杂度上升 > 20%,evaluator 自动 reject(autoresearch 第 7 条) |

---

### M5 — 工作流 + 自学习

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-70 | `engram/workflow/` 模块 + CLI 子命令：add / run / revise / promote / rollback / list / test | todo | | T-13, T-14 | 按 SPEC §6 的工作流目录结构；`add` 创建骨架 |
| T-71 | `engram/workflow/runner.py` — spine 执行（python / bash / toml）+ 沙箱 | todo | | T-70 | toml spine 是声明式步骤；python + bash 在子进程运行；捕获 stdout/stderr |
| T-72 | `engram/workflow/fixtures.py` — fixture 测试框架 | todo | | T-70, T-71 | 加载 `fixtures/`；运行 spine；对比实际输出与预期输出 |
| T-73 | `engram/workflow/rev.py` — rev / current 符号链接管理，基于 git | todo | | T-70, T-71 | 每个版本是一次 git 提交；`current` 符号链接指向活跃版本 |
| T-74 | `engram/autolearn/engine.py` — Darwin 棘轮循环 | todo | | T-71, T-72, T-73 | 棘轮：每轮是一次提交；指标回退 → 自动撤回；提升 → 保留 |
| T-75 | `engram/autolearn/proposer.py` — 独立 LLM 子代理负责变更提案 | todo | | T-74 | 以子进程调用；接收工作流 + fixture 结果；仅提出 diff |
| T-76 | `engram/autolearn/judge.py` — 独立 LLM 评估器 | todo | | T-74, T-75 | 与提案者上下文独立；不自我评估；按双维度评分标准打分 |
| T-77 | 双维度评分标准：静态 60 分（SPEC 合规 + fixture + 可解析 + 无密钥）+ 执行 40 分（fixture 通过 + 指标 Δ > 0） | todo | | T-75, T-76 | 评分标准以 `engram/autolearn/rubric.toml` 文件形式版本化管理 |
| T-78 | 阶段闸门：连续 K=5 轮自学习后暂停；将差异摘要写入 `engram review` | todo | | T-74, T-76 | K 可配置；下一阶段开始前需人工确认 |
| T-79 | `engram workflow autolearn <name>` CLI | todo | | T-74, T-75, T-76, T-77, T-78 | 标志：`--rounds=N`、`--dry-run`、`--phase-gate=K` |
| T-80 | E2E：release-checklist 工作流自学习 10 轮，指标单调提升 | todo | | T-79 | fixture 工作流在 `tests/fixtures/workflows/release-checklist/`；指标不得回退 |
| T-81 | `workflows/<name>/journal/evolution.tsv` 写入器 | todo | | T-74, T-77 | 列：round、score_static、score_perf、total、change_summary、kept |

---

### M6 — 知识库 + 收件箱完整 + 一致性引擎 Phase 3-4

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-90 | `engram/kb/` 模块 + CLI 子命令：new-article / compile / list / read | todo | | T-13, T-14 | 按 SPEC §7 的知识库目录结构；`new-article` 创建章节骨架 |
| T-91 | `engram/kb/compiler.py` — 生成 `_compiled.md` + `_compile_state.toml` | todo | | T-90 | 调用 LLM 提供商（可配置）；写入摘要；记录章节哈希值 |
| T-92 | 知识库章节监视器 → 在 `engram review` 中检测过期摘要 | todo | | T-90, T-91 | 对比存储的章节哈希与当前值；在 review 输出中标记过期条目 |
| T-93 | `engram/consistency/phase3_llm.py` — LLM 辅助审核（可选，需在配置中开启） | todo | | T-46, T-47, T-48 | 默认关闭；与提供商无关；提示 LLM 审核冲突提案 |
| T-94 | `engram/consistency/phase4_execution.py` — 工作流的 fixture 验证 | todo | | T-71, T-72, T-93 | 运行工作流 fixture；fixture 失败时标记工作流衰变冲突 |
| T-95 | 池传播的通知式 + 钉版模式（M3 自动同步之外） | todo | | T-30, T-31 | `notify`：日志条目 + `engram review` 标记；`pinned`：在 pools.toml 中锁定到版本 ID |
| T-96 | 收件箱反向通知：发送方在下次会话启动时看到解决状态 | todo | | T-50 | 向收件箱日志添加 `resolved_at` + `resolution_note`；在启动摘要中展示 |
| T-97 | 完整的 `engram_inbox_*` MCP 写工具（send / acknowledge / resolve / reject） | todo | | T-52, T-50 | 将 M4 的只读 MCP 扩展为包含写操作 |
| T-98 | 使用结果日志 → 置信分批量更新流水线 | todo | | T-14, T-15 | 从日志读取结果事件；按 DESIGN §9 重新计算每条资产的 `confidence_score` |
| T-99 | E2E：跨仓收件箱完整流程（send → acknowledge → resolve → 反向通知） | todo | | T-50, T-96 | 在 `tests/fixtures/` 中建立两个 fixture 仓库；断言四个状态全部达到 |

---

### M7 — Web UI P0

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-110 | `web/backend/` FastAPI 骨架 + `engram web serve / open` CLI 集成 | todo | | T-14 | Python 3.11+；uvicorn；`open` 时自动打开浏览器 |
| T-111 | `web/backend/app/sse.py` — 实时更新的 Server-Sent Events | todo | | T-110 | 每个连接的客户端一条 SSE 流；从监视器发送资产变更事件 |
| T-112 | `web/backend/app/watcher.py` — inotify（Linux）/ FSEvents（macOS）文件系统监视器 | todo | | T-110 | 向 SSE 发送事件；200ms 去抖；忽略 `.git/` 和 `__pycache__/` |
| T-113 | `web/backend/app/auth.py` — none / basic / token 鉴权模式（配置驱动） | todo | | T-110 | 默认 = none（仅本地）；basic 和 token 通过 `config.toml` 配置；无云端鉴权 |
| T-114 | `web/frontend/` SvelteKit 骨架 | todo | | T-110 | SvelteKit + Vite；开发时由 FastAPI 静态挂载服务；构建输出至 `web/frontend/build/` |
| T-115 | i18n 文件：`en.json` + `zh.json` | todo | | T-114 | 所有 UI 字符串从第一天起就外部化；`.svelte` 文件中不硬编码英文字符串 |
| T-116 | 总览面板页面（P0） | todo | | T-114, T-115, T-111 | 资产数量、智慧指标迷你图、待处理项（validate 错误 + 过期知识库 + 未读收件箱） |
| T-117 | 记忆详情页面 | todo | | T-116 | frontmatter + body 只读视图；入/出引用；来自日志的归属时间线 |
| T-118 | 工作流详情页面（仅查看 — 从 CLI 运行） | todo | | T-116 | 文档 + spine 并排显示；版本列表及评分；最后一轮自学习摘要 |
| T-119 | 知识文章页面（仅读取） | todo | | T-116 | 源章节 + `_compiled.md` 并排显示；摘要过期时显示过期徽章 |
| T-120 | 收件箱页面 | todo | | T-116, T-111 | 按状态列出消息（未读 / 已确认 / 已解决）；发送表单 |
| T-121 | 上下文预览页面（DESIGN §7.1 中关键的调试页面） | todo | | T-116, T-40 | 任务输入 → 模拟上下文打包 → 显示每条加载的资产及排名和原因 |
| T-122 | 所有 6 个 P0 页面的 Playwright 冒烟测试 | todo | | T-116, T-117, T-118, T-119, T-120, T-121 | 无 500 错误；无断链；通过 axe-playwright 的 WCAG AA 检查 |
| T-123 | `engram web serve / open` CLI 集成 | todo | | T-110, T-114 | `serve` 启动后端；`open` 打开浏览器；`--port` 标志；优雅关闭 |

---

### M8 — 演化 + 团队完整 + TS SDK + 剩余 Web UI + 迁移源

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-130 | `engram/evolve/engine.py` — ReMem 行动-思考-精炼循环（受 evo-memory 启发） | todo | | T-14, T-48 | 默认每月执行一次；仅提案，绝不自动执行；写入 review 队列 |
| T-131 | 4 种演化精炼类型：merge / split / promote-to-KB / rewrite | todo | | T-130 | 每种类型有提案 schema 和 `engram review` 中的差异预览 |
| T-132 | 智慧指标聚合流水线 | todo | | T-15, T-77, T-98 | 读取日志；计算 4 条曲线；写入 `wisdom_snapshot.json` |
| T-133 | `engram/wisdom/curves.py` — 按 DESIGN §5.6 计算 4 条曲线 | todo | | T-132 | 曲线：工作流掌握度、任务复现效率、记忆精选率、上下文效率 |
| T-134 | Web UI 知识图谱页面（D3 力导向布局 — 资产 + 引用 + 订阅） | todo | | T-116 | 节点：记忆 / 工作流 / 知识库；边：引用 + 池订阅；点击 → 详情页面 |
| T-135 | Web UI 池管理页面 | todo | | T-116, T-95 | 池 × 订阅者表格；传播 UI；按订阅者显示传播模式 |
| T-136 | Web UI 项目总览页面 | todo | | T-116, T-132 | 本机所有 engram 项目；智慧指标对比表格 |
| T-137 | Web UI 智慧指标页面 | todo | | T-116, T-132, T-133 | 4 条曲线图表及回退标注；`engram wisdom report` 以文本形式镜像此页 |
| T-138 | Web UI 自学习控制台页面 | todo | | T-116, T-81 | 实时滚动 `evolution.tsv`；启动/暂停控制；历史运行及评分记录 |
| T-139 | TypeScript SDK — `@engram/sdk` npm 包 | todo | | T-51, T-52 | 镜像 Python SDK 基础功能；MCP 客户端包装；从 pydantic schema 生成类型 |
| T-140 | 6 个额外迁移源：chatgpt / mem0 / obsidian / letta / mempalace / markdown | todo | | T-34 | 每个源是 `engram/migrate/` 中的独立模块；每个源拆为一个子任务也可以 |
| T-141 | `engram playbook` 命令族：install / publish / list / uninstall | todo | | T-70, T-90 | 剧本 = 工作流 + 知识库文章 + 种子记忆；通过 GitHub URL 分发 |

---

### M4.5 增补 / M5 / M6 / M8 — 业界对照差距收口（来自 `docs/superpowers/specs/2026-04-25-industry-comparison-and-gaps.md`）

| ID | 任务 | 状态 | Owner | 依赖 | 备注 |
|----|------|------|-------|------|------|
| T-150 | Stage 3 融合换 RRF（Reciprocal Rank Fusion） | todo | | T-40, T-44 | M4.5；替换 `cli/engram/relevance/gate.py` 现有 `fused_dist = dist * (1.0 - 0.30 * overlap)`；对应 G-01 |
| T-151 | Stage 7.5 cross-encoder rerank（bge-reranker-v2-m3，top-20） | todo | | T-150 | M4.5；DESIGN §5.1 已命名模型；对应 G-02 |
| T-152 | LOCOMO + LongMemEval 跑分提到 M4.5 并发表 | todo | | T-150, T-151 | M4.5；写入 `benchmarks/BENCHMARKS.md`，可复现脚本；对应 G-03 |
| T-153 | SPEC-AMEND：bi-temporal frontmatter（`event_time` × `record_time`） | todo | | — | M5；先用户裁定 Q1（重命名 vs 新增）；对应 G-04 |
| T-154 | `entities` + `entity_mentions` 缓存表（graph.db 内，不引入新存储引擎） | todo | | T-14 | M5；LLM 异步抽取，失败退化到 tag；对应 G-05 |
| T-155 | Stage 7.6 主动 context 压缩（可选 opt-in） | todo | | T-150 | M5；先用户裁定 Q2（真资产 vs 临时缓存);对应 G-06 |
| T-156 | SPEC-AMEND：`episodic` 作为 Memory 第 7 子类型 + Evolve promote 规则 | todo | | T-130 | M5；先用户裁定 Q3（子类型 vs 顶层类）；对应 G-07 |
| T-157 | 可选 `agent_id` namespace（多 agent 隔离） | todo | | T-30 | M8；frontmatter 加可选字段 + Gate 过滤 + `--include-other-agents`；对应 G-08 |
| T-158 | 每资产 `last_accessed_at` + Ebbinghaus 访问重置 | todo | | T-15 | M8；持久化需 SPEC-AMEND；对应 G-09 |
| T-159 | Phase 3（LLM review）默认开启并文档化 token 预算 | todo | | T-49 | M6；先用户裁定 Q4（默认本地审查模型）；对应 G-11 |
| T-160 | MCP shim：兼容 Anthropic memory tool 6 命令（view/create/str_replace/insert/delete/rename） | todo | | T-50 | M8；映射到 `.memory/`，强制走 review，禁止 auto-delete；对应 G-12 |

完整背景、对标证据、护城河约束、Open Question 见 `docs/superpowers/specs/2026-04-25-industry-comparison-and-gaps.md`。

---

## 4. 并行化建议

M2 的核心模块大多是顺序的，因为每个模块都依赖前一个（paths → fs → graph_db → frontmatter）。T-14（graph_db）和 T-15（journal）完成后，后续任务开始分支。

按阶段的并行机会：

- **M2 期间**：T-10 到 T-15 是顺序的基础设施；T-16 到 T-22 在 T-10 完成后可以交叉进行。
- **M3 和 M4 可并行**：M2 合并后，M3 范围任务（T-30–T-39）和 M4 适配器任务（T-53–T-56）涉及不同模块，可以并行推进。相关性闸门（T-40–T-45）和一致性引擎（T-46–T-49）彼此独立，也与适配器工作独立。
- **M5 / M6 / M7 是独立功能**：M4 打标签后，三个里程碑可以并行进行。工作流（M5）、知识库（M6 T-90–T-92）和 Web UI 后端骨架（M7 T-110–T-113）没有共享代码路径。
- **M4.5 基准测试**与 M5–M6 并行运行。它依赖 M4 的一致性引擎（T-47、T-48）和范围引擎（T-38、T-39），但不依赖 M5 或 M6 的任何内容。
- **M8 Web UI 页面**（T-134–T-138）可与 M8 迁移源（T-140）和 TypeScript SDK（T-139）并行开始 — 三者彼此独立。
- **需注意的跨里程碑依赖**：T-98（置信分更新流水线）是 T-132（智慧指标聚合）的前置。T-132 不得在 T-98 完成之前开始。

---

## 5. 新手友好任务

好的第一个 Issue — 范围明确，不需要深入了解架构：

- **T-07** — 参与 SPEC + DESIGN 的外部审核。读两份文档，对不清楚的地方开 Issue。无需写代码。
- **T-61** — 编写 `docs/HISTORY.md` 起始条目。按格式写一条修正日志：日期、指标名称、变更前、变更后、原因。纯 markdown 工作。
- **T-53 / T-54（任选一个适配器）** — 每个适配器是一个模板文件。选一个你已经在用的工具（Cursor、Codex、raw-api）。范围明确，自成一体，无共享状态。
- **T-115** — i18n 翻译改进。向 `en.json` / `zh.json` 补充缺失字符串。术语必须与 `docs/glossary.md` 完全一致。
- **T-59 或 T-60（添加一个 fixture）** — 添加一个合成基准测试样本。T-59 = 一对资产 + 预期 ConflictReport。T-60 = 一个范围冲突场景。每个只需几个文件。
- **T-140（选一个迁移源）** — 每个迁移源是独立模块。obsidian 和 markdown 是最容易的起点；不需要 API 访问。

如果你初次接触代码库，建议先读 `SPEC.md §4`（记忆格式）和 `DESIGN.md §3`（存储层），再选任务。`docs/glossary.md` 是权威术语表 — 使用它，不要自创同义词。

---

## 6. 争议/延后项

这些是 SPEC + DESIGN 审核期间出现的设计问题，已被有意推迟。它们不是任务。如果你想重新讨论某个问题，请开 GitHub Discussion，而不是 Issue。

- **跨机器同步**：v0.2 建议通过 rsync 或 git 跨机器同步 `~/.engram/user/`。第一方 `engram sync` 守护进程（可能基于 CRDT）是 P2 项目。v0.2 有意将同步方案简化，以避免将 engram 建成云服务。
- **LLM 侧一致性强制执行**：一致性引擎目前是事后处理（扫描 → 提案 → 人工处置）。在运行时拦截 LLM 输出以阻止违反 `enforcement=mandatory` 规则的行为是 P2 项目，需要 v0.2 中尚不存在的代理层，这也是一个复杂的信任和正确性问题。
- **联邦式池注册表**：池通过 GitHub URL 安装（`engram playbook install github:<owner>/<repo>`）。可发现的社区注册表是 P2 项目。本地优先的设计使集中式注册表成为一个严肃的信任和治理问题，项目目前尚未准备好解决。
- **移动端 Web 支持**：Web UI 在 v0.2 中仅面向桌面浏览器。移动端只读浏览可能偶然可用，但不会获得专门的设计适配。没有原生应用计划（参见 DESIGN §13.4 非目标）。
- **记忆并发编辑的 CRDT**：v0.2 使用乐观并发（原子重命名），并将真实冲突上报给一致性引擎由人工处理。完整的 OT 或 CRDT 在 P2；两个人同时编辑同一条记忆资产的场景极少，不足以证明复杂度合理。
- **多语言嵌入向量**：默认嵌入向量模型（bge-reranker-v2-m3）主要在英文上训练。非英文检索质量尚未测试。模型可通过配置替换；第一方非英文支持是 P2，待硬件性能评估和质量测量后推进。

---

## 7. 任务板维护规则

- 所有涉及某条任务的 PR 必须在本文件中更新该任务的状态。PR 描述应引用对应 T-ID。
- 新任务使用下一个可用的 T-XX 编号。不要复用已废弃任务的编号。
- 已完成的任务保留行，将状态改为 `done`。不要删除行。
- 拆分任务：将子任务 ID 内联附加（T-11a、T-11b）。父任务行的 Notes 列指向子任务。
- 已废弃的任务：将状态改为 `abandoned`，在 Notes 中写明简短原因。保留该行。
- 里程碑顺序调整需要 PR，同时修改本文件和 DESIGN §13（如适用）。里程碑重排是方向性决策 — 先在 GitHub Discussions 讨论，再提 PR。
- 每次触及本文件的 PR 都要更新页眉中的"最后更新"日期。

---

任务板由 engram 社区维护。提 PR 来添加或更新任务。方向性讨论（里程碑顺序、P2 升级为 P1）请使用 GitHub Discussions。
