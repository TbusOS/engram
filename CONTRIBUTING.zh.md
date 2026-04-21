[English](CONTRIBUTING.md) · [中文](CONTRIBUTING.zh.md)

# 为 engram 做贡献

感谢你考虑为这个项目做贡献。本文档涵盖：如何找到适合自己的任务、如何搭建开发环境、如何提交改动、以及我们要求的质量标准。

如有任何疑问，请开一个 GitHub Discussion。以下规则都不是一成不变的 —— 社区可以通过 PR 修改它们。

---

## 1. 如何开始

两条路径：

### 路径 A：我有一个具体想法

1. 在 GitHub Discussions 的 **Ideas** 分类下开一个讨论帖。
2. 等待社区或维护者回应 —— 通常在 3 天内。
3. 如果想法原则上被接受，提一个 Issue，明确写出范围和边界。
4. Fork 仓库，建分支，写代码，提 PR。

### 路径 B：我想帮忙，但不知道做什么

1. 读 [`TASKS.md`](TASKS.md) —— 9 个里程碑，105+ 个任务。
2. 找一个 Owner 列为空、状态为 `todo` 的任务。
3. 提一个标题为 `Claim T-XX` 的 Issue，并自我分配。
4. 在第一个 commit 里更新 `TASKS.md` 的 Owner 和状态字段。
5. Fork、建分支、提 PR。

**对新贡献者友好的起点任务：**

- 为 `migrate` 命令新增一个迁移源（T-140 子任务 —— 每个都是独立的 Python 模块）
- 改进 [`docs/glossary.md`](docs/glossary.md) 中的术语定义或翻译
- 为 `tests/conformance/` 补充一个一致性测试夹具
- 在 `playbooks/` 里写一个剧本（Playbook）示例
- 为某个已有 CLI 命令补测试

优先从 M1–M3 的任务开始。M4+ 的任务往往需要跨层理解。

---

## 2. 开发环境搭建

**依赖要求：**

- Python 3.10+（测试版本：3.10、3.11、3.12、3.13）
- Node.js 18+（仅在改 `web/frontend/` 或 `sdk-ts/` 时需要）
- Git 2.20+

**克隆并安装：**

```bash
git clone https://github.com/TbusOS/engram.git
cd engram
pip install -e "cli/[dev]"        # 可编辑安装，包含开发依赖
pre-commit install                # 在每次 commit 前自动跑 linter
```

**跑测试：**

```bash
cd cli
pytest                            # 单元测试 + 集成测试
pytest --cov=engram               # 带覆盖率报告
pytest -k test_memory             # 只跑指定名称的测试
pytest tests/e2e/                 # 只跑 E2E 测试
```

**本地启动 Web UI（仅在需要改 Web 时）：**

```bash
# 后端
cd web/backend
pip install -e ".[dev]"
uvicorn engram_web.app:create_app --reload --factory

# 前端 —— 另开一个终端
cd web/frontend
npm install
npm run dev
```

**代码检查工具：**

```bash
ruff check .                      # Python lint
ruff format --check .             # Python 格式检查
mypy cli/engram                   # Python 类型检查
npm run lint                      # TypeScript/Svelte lint
npm run format:check              # Prettier 格式检查
```

**提 PR 前，以上所有检查都必须通过。** CI 运行的是同一套命令。

---

## 3. 分支与 commit 规范

**分支命名：**

| 模式 | 用于 |
|------|------|
| `feat/<name>` | 新功能 |
| `fix/<name>` | 修复缺陷 |
| `docs/<name>` | 只改文档 |
| `refactor/<name>` | 不改行为的代码重构 |
| `test/<name>` | 只改测试 |

`main` 是稳定分支。`main` 上的每个 commit 都必须通过 CI。

**Commit 格式 —— Conventional Commits：**

```
type(scope): subject
```

- subject：祈使语气，≤72 个字符
- body（可选）：每行 ~72 字符；解释*为什么*，而不是*做了什么*
- 禁止 AI 署名行（`Co-Authored-By: Claude ...` 等）

**类型（type）：**

| 类型 | 使用时机 |
|------|----------|
| `feat` | 新功能（SPEC 改动永远用 feat） |
| `fix` | 修复缺陷 |
| `docs` | 只改文档（README、SPEC 说明等） |
| `refactor` | 既非功能也非修复的代码变动 |
| `test` | 只改测试 |
| `chore` | 构建脚本、CI、脚手架 |
| `perf` | 性能改进 |
| `ci` | CI 配置变更 |
| `spec` | SPEC.md 内容更新 |
| `design` | DESIGN.md 内容更新 |
| `methodology` | METHODOLOGY.md 内容更新 |

**示例：**

```
feat(cli): add engram migrate for Claude Code sources
fix(spec): clarify MEMORY.md required fields
docs(glossary): add knowledge-base terms for v0.2
test(e2e): cover multi-adapter init flow
spec(§13): add migration default for agent subtype
```

**一个 commit 做一件事。** 如果 message 里想写"同时还..."，说明该拆了。

---

## 4. Pull Request

### 提 PR 前

- 在最新的 `main` 上 rebase
- 本地跑 `pytest` 和 `ruff check .` —— 两者都必须通过
- 如果认领或完成了任务，更新 `TASKS.md`（Owner 和状态字段）
- 为任何行为变化添加或更新测试
- 覆盖率不得比存档基线（`tests/.coverage-baseline.json`）下降超过 2%
- 如果 PR 涉及 `SPEC.md` 或 `DESIGN.md` 的结构性改动，先读第 5 节

### PR 描述模板

将以下内容复制到 PR 描述中：

```markdown
## 摘要
<1–3 句话说明这个 PR 做了什么>

## 关联任务
Closes T-XX。Relates to T-YY。

## 改动列表
- <重要改动 1>
- <重要改动 2>

## 测试情况
- <本地测试了什么>
- <CI 结果确认通过>

## 检查清单
- [ ] 测试已添加或更新
- [ ] 文档已更新（SPEC / DESIGN / METHODOLOGY / TASKS，视情况而定）
- [ ] 覆盖率 ≥ 基线
- [ ] 无术语滥用（对照 docs/glossary.md 语言规范检查）
- [ ] 所有用户可见内容使用了词表中的术语原文
```

### 评审 SLA

- 初次回应：3 天内
- 实质性评审：7 天内（非简单 PR）
- 合并：1 位维护者批准 + CI 通过；SPEC 改动需要 2 位维护者批准

### 评审时可能被要求修改的情况

- 新行为缺少测试
- 文档里有模糊或业务话术语言（见第 7 节）
- 未经 Discussion 就改 SPEC 或 DESIGN
- 新 CLI 命令没有 E2E 测试
- 覆盖率下降

---

## 5. SPEC / DESIGN 改动 —— 轻量 RFC 流程

`SPEC.md` 或 `DESIGN.md` 的结构性改动（不包括错别字修复和示例补充）需要在实现之前走一轮轻量 RFC。

**哪些算结构性改动（需要 RFC）：**

- 新增前置信息（frontmatter）字段（必填或选填）
- 新增记忆（Memory）子类型或资产类别
- 修改冲突解决规则（DESIGN §8.4）
- 修改一致性引擎（Consistency Engine）的冲突分类（SPEC §11）
- 新增校验错误码
- 修改 MCP 工具签名

**直接提 PR 即可（不需要 RFC）：**

- 错别字修复和说明性修改
- 添加示例或改进现有示例
- 修正或扩展词表术语
- 非规范性注释

### RFC 步骤

**第一步 —— 在 GitHub Discussions 的 Design Review 分类下发帖。**

- 标题：`RFC: <改动描述>`
- 内容：问题描述 / 提议的改动 / 考虑过的替代方案 / 是否为破坏性改动
- 用 `@` 标记维护者

**第二步 —— 社区反馈**（最少开放 3 天，通常约 1 周）。

- 维护者提出问题或意见
- 社区自由参与讨论
- 在写代码之前，先形成大致共识

**第三步 —— 实现 PR**

- PR 描述中链接到对应的 Discussion
- PR 包含 SPEC 或 DESIGN 更新 + 测试 + 实现新规则的组件代码
- SPEC 改动需要 2 位维护者批准；DESIGN 改动需要 1 位

**第四步 —— 对外通知**

- 若改动影响现有用户，更新 `docs/HISTORY.md`
- 若为破坏性改动（按 SPEC §13.1 定义）：提升 MAJOR 版本号，并按 SPEC §13.3–13.4 提供迁移路径

---

## 6. 测试要求

参考 DESIGN §10 测试策略。

**覆盖率目标：**

| 组件 | 目标 |
|------|------|
| Python `cli/engram/` | ≥80% 行覆盖率 |
| TypeScript `sdk-ts/` | ≥80% 行覆盖率 |
| Svelte `web/frontend/` | ≥70% 组件覆盖率 |

CI 强制执行覆盖率。超过 2% 的下降会阻塞 PR 合并。

**每个新 CLI 命令：**

- 在 `cli/tests/` 中至少有一个命令逻辑的单元测试
- 在 `tests/e2e/` 中至少有一个 E2E 测试
- 同时覆盖正常路径和至少一种失败路径

**每条新 SPEC 规则：**

- 在 `tests/conformance/` 中至少有一个一致性测试夹具
- 夹具需包含：一个合法示例、至少一个非法示例、以及 `engram validate --json` 的预期输出

**每次修改智能层（第 3 层）组件**（相关性闸门、一致性引擎、自学习引擎、演化引擎、智慧指标）：

- 若改动可能影响评分或排序结果，需补充基准测试
- 需对 `benchmarks/results_*.jsonl` 中的已提交基线进行回归测试

**测试隔离规则：**

- 单元测试：纯函数，不产生文件系统副作用 —— 使用 fixture 或 `tmp_path`
- E2E 测试：每个测试使用独立的 `pytest.tmp_path`；不得修改用户真实的 `~/.engram/`
- 集成测试：可使用内存 SQLite 或临时目录；测试函数之间不共享状态

---

## 7. 代码评审规范

**对评审者：**

- 重点关注正确性、可读性，以及是否与十二条不变量（DESIGN §8）兼容
- 指出文档中含有模糊语言的地方 —— 如有必要可引用 [`docs/glossary.md`](docs/glossary.md) 中的语言规范
- 对新增的复杂性提出挑战：现有机制能否覆盖？
- 确认测试真的在测行为，而不只是凑覆盖率
- 格式问题接受"够用就好"；对逻辑和规范符合性保持严格

**对收到评审意见的贡献者：**

- 7 天内回应，修改完成后重新申请评审
- 对不认同的意见可以提出反对 —— 引用 SPEC、DESIGN 或 README 作为依据
- 明确关闭每个讨论线程，不要悄悄不理

**合并规则：**

- 1 位维护者批准 + CI 通过 → 可以合并
- SPEC 改动：需要 2 位维护者批准
- 存在争议的 PR：先在 Discussions 中达成共识再合并

---

## 8. 发布流程

**版本节奏：**

| 类型 | 触发时机 |
|------|----------|
| 补丁版本（v0.2.1、v0.2.2、...） | 修复缺陷，按需发布 |
| 次要版本（v0.3、v0.4、...） | 里程碑 M5+ 完成时 |
| 主要版本（v1.0、v2.0、...） | SPEC 破坏性改动（按 SPEC §13.1 定义） |

**发布检查清单：**

- [ ] 所有里程碑任务在 `TASKS.md` 中标记为 `done`
- [ ] `CHANGELOG.md` 已更新，包含用户可见的变更
- [ ] `docs/HISTORY.md` 记录了本周期内的任何纠正或撤回
- [ ] 基准测试已运行，结果已提交至 `benchmarks/results_*`
- [ ] 手动检查清单 `tests/manual-checklist.md` 已完成
- [ ] 创建发布标签：`git tag -s v0.X.Y -m "engram v0.X.Y"`
- [ ] 推送标签 → 触发 `.github/workflows/release.yaml` → 发布到 PyPI
- [ ] 在 GitHub Releases 发布说明，并在 Discussions 中公告

---

## 9. 社区

**Discussions** —— https://github.com/TbusOS/engram/discussions

适合：
- 设计讨论（提 Issue 或 PR 之前）
- 功能提案和想法
- 使用方式和经验分享
- 答疑

**Issues** —— https://github.com/TbusOS/engram/issues

适合：
- 具体的缺陷报告
- 明确范围的功能请求（经过 Ideas 讨论之后）
- 任务认领：Issue 标题写 `Claim T-XX`

**PR** —— https://github.com/TbusOS/engram/pulls

适合：
- 代码、文档、测试贡献
- 遵循第 4 节的 PR 检查清单

**行为准则：**

保持友善、直接、有建设性。不人身攻击，不刷存在感，不对人设门槛。如果有人的行为让你感到不适，请私下联系维护者。

---

## 10. 许可证

engram 采用 MIT 许可证。提交贡献即表示你同意你的贡献同样以 MIT 许可证发布。

如果你代表雇主贡献代码并需要 CLA 相关条款，开一个 Discussion —— 我们会协商解决。

---

感谢你读到这里。engram 是一个长期项目，目标是把 LLM 记忆的控制权还给产生它的人。每一份贡献 —— 代码、测试、文档、设计评审意见、翻译、基准测试夹具 —— 都会积累起来。

有关本指南的问题：GitHub Discussions。
