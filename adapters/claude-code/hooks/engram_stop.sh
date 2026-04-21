#!/usr/bin/env bash
# engram Claude Code stop hook.
#
# Runs when a Claude Code session ends. Lightweight by contract:
# DESIGN §20 caps hook latency at 500ms, so this must not block on
# network or long-running work. Keep it to cheap local commands.
#
# Install: copy into Claude Code's hook config (see Claude Code docs)
# or symlink from ~/.claude/hooks/stop/engram.sh.
#
# Environment:
#   CLAUDE_PROJECT_ROOT  absolute path to the project Claude had open.
#                        Falls back to $PWD when missing.

set -euo pipefail

project_root="${CLAUDE_PROJECT_ROOT:-$PWD}"
cd "$project_root" 2>/dev/null || exit 0

# Record a session-stop marker in the store's status snapshot (best-effort).
engram status --format=json >/dev/null 2>&1 || true

exit 0
