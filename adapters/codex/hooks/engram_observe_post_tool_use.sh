#!/usr/bin/env bash
# engram observer — OpenAI Codex CLI PostToolUse hook.
#
# See adapters/claude-code/hooks/engram_observe_post_tool_use.sh for
# the full contract. Codex passes a different JSON shape on stdin;
# `engram observe --from=codex` handles the translation.

set -euo pipefail

engram_bin="${ENGRAM_BIN:-$(command -v engram 2>/dev/null || true)}"
[ -x "$engram_bin" ] || exit 0

session_id="${CODEX_SESSION_ID:-${ENGRAM_SESSION_ID:-}}"
[ -n "$session_id" ] || exit 0

"$engram_bin" observe \
    --session="${session_id}" \
    --client=codex \
    --from=codex 2>/dev/null \
  || "$engram_bin" observe \
    --session="${session_id}" \
    --client=codex 2>/dev/null \
  || true

exit 0
