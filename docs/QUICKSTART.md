# 5-Minute Quickstart

[English](#english) · [中文](#中文)

---

<a name="english"></a>

From zero to a working engram store in **five minutes**. If anything here
takes longer, please file a bug — this page is load-bearing for new
contributors and for the "first-look" audience.

## Prerequisites

- Python 3.10+ (`python3 --version`)
- Git (for team / org / pool sync features — not needed for a local-only
  store)
- POSIX shell (macOS, Linux, WSL — Windows native is on the roadmap)

## Install

```bash
git clone https://github.com/TbusOS/engram.git
cd engram/cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

engram --version
# → engram 0.2.0.dev0 (store 0.2, Python 3.14.x, darwin-arm64)
```

## First memory in 60 seconds

```bash
cd ~/my-kernel-work   # any directory you want to attach memory to

engram init --name=kernel-work
# → engram initialized at ~/my-kernel-work/.memory

engram memory add \
  --type=user \
  --name="linux kernel fluency" \
  --description="operator reads mm/ and fs/ routinely"
# → added local/user_linux_kernel_fluency
```

## Add a rule the assistant must follow

```bash
engram memory add \
  --type=feedback \
  --name="confirm before push" \
  --description="never push to any remote without explicit go-ahead" \
  --enforcement=mandatory \
  --body="Ask before pushing.

**Why:** a prior force-push lost a colleague's work on a shared branch.

**How to apply:** every git push, regardless of branch or remote."
# → added local/feedback_confirm_before_push [mandatory]
```

## Search and verify

```bash
engram memory search "kernel"
# →   2.850  local/user_linux_kernel_fluency  [project/default]

engram validate
# → clean — no errors, no warnings

engram status
# → .memory/ at ~/my-kernel-work · store 0.2 · 2 assets · 0 pools
```

## Subscribe to a shared pool (once one exists)

```bash
# The pool repository is hosted like any other git repo.
engram pool pull kernel-work-pool         # fetch latest
engram pool subscribe kernel-work-pool --at=user
# → subscribed to kernel-work-pool (subscribed_at=user, mode=auto-sync)
```

## Migrate a v0.1 store

```bash
# Dry run first — prints the plan, touches no files.
engram migrate --from=v0.1 --dry-run

# Live migration — writes a full backup to .memory.pre-v0.2.backup/
engram migrate --from=v0.1

# If anything looks wrong:
engram migrate --rollback
```

## Next steps

- `SPEC.md` — the on-disk format contract (what an engram store looks like)
- `CLAUDE.md` — LLM collaborator guide if you use Claude Code / Codex /
  Cursor to work on engram itself
- `CONTRIBUTING.md` — contribution workflow
- `https://TbusOS.github.io/engram/` — project site with roadmap + design

---

<a name="中文"></a>

# 5 分钟快速开始

从零到能跑的 engram 仓,**5 分钟以内**。如果哪一步超时,请提 issue
—— 这一页对新贡献者和"先看一眼"的访客都是门面。

## 前置

- Python 3.10+(`python3 --version`)
- Git(team / org / pool 同步要用;纯本地仓不需要)
- POSIX shell(macOS / Linux / WSL;Windows 原生在路线图上)

## 安装

```bash
git clone https://github.com/TbusOS/engram.git
cd engram/cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

engram --version
# → engram 0.2.0.dev0 (store 0.2, Python 3.14.x, darwin-arm64)
```

## 60 秒加第一条记忆

```bash
cd ~/my-kernel-work   # 你想挂 memory 的任意目录

engram init --name=kernel-work
# → engram initialized at ~/my-kernel-work/.memory

engram memory add \
  --type=user \
  --name="linux kernel fluency" \
  --description="operator reads mm/ and fs/ routinely"
# → added local/user_linux_kernel_fluency
```

## 加一条强制规则

```bash
engram memory add \
  --type=feedback \
  --name="confirm before push" \
  --description="never push to any remote without explicit go-ahead" \
  --enforcement=mandatory \
  --body="Ask before pushing.

**Why:** 之前一次 force-push 把同事共享分支的未提交改动冲没了。

**How to apply:** 所有 git push,不分分支、不分 remote。"
# → added local/feedback_confirm_before_push [mandatory]
```

## 搜索并校验

```bash
engram memory search "kernel"
# →   2.850  local/user_linux_kernel_fluency  [project/default]

engram validate
# → clean — no errors, no warnings

engram status
# → .memory/ at ~/my-kernel-work · store 0.2 · 2 assets · 0 pools
```

## 订阅共享池(池仓库就位后)

```bash
# 池仓库就是普通 git 仓。
engram pool pull kernel-work-pool         # 拉最新
engram pool subscribe kernel-work-pool --at=user
# → subscribed to kernel-work-pool (subscribed_at=user, mode=auto-sync)
```

## 迁移 v0.1 仓库

```bash
# 先 dry-run,只打印计划,不动文件。
engram migrate --from=v0.1 --dry-run

# 正式迁移;写 .memory.pre-v0.2.backup/ 全量备份。
engram migrate --from=v0.1

# 发现不对:
engram migrate --rollback
```

## 下一步

- `SPEC.md` —— 磁盘格式合约(一个 engram 仓长什么样)
- `CLAUDE.md` —— 给 Claude Code / Codex / Cursor 等协作者的 onboarding
- `CONTRIBUTING.md` —— 贡献流程
- `https://TbusOS.github.io/engram/` —— 项目站 + 路线图 + 设计
