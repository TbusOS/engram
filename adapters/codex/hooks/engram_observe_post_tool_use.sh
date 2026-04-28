#!/usr/bin/env bash
# engram observer — OpenAI Codex CLI PostToolUse hook.
#
# See adapters/claude-code/hooks/engram_observe_post_tool_use.sh for
# the full contract. Codex passes a different JSON shape on stdin;
# `engram observe --from=codex` handles the translation.

set -euo pipefail

session_id="${CODEX_SESSION_ID:-${ENGRAM_SESSION_ID:-default}}"

if ! command -v engram >/dev/null 2>&1; then
    exit 0
fi

engram observe \
    --session="${session_id}" \
    --client=codex \
    --from=codex 2>/dev/null \
  || engram observe \
    --session="${session_id}" \
    --client=codex 2>/dev/null \
  || true

exit 0
