#!/usr/bin/env bash
# engram observer — Gemini CLI post-tool-use hook (skeleton).
#
# Gemini CLI's hook system does not currently expose a PostToolUse
# surface; this script is the placeholder for when it does. Users can
# still wire it manually in scripted environments that wrap the CLI.

set -euo pipefail

engram_bin="${ENGRAM_BIN:-$(command -v engram 2>/dev/null || true)}"
[ -x "$engram_bin" ] || exit 0

session_id="${GEMINI_SESSION_ID:-${ENGRAM_SESSION_ID:-}}"
[ -n "$session_id" ] || exit 0

"$engram_bin" observe \
    --session="${session_id}" \
    --client=gemini-cli 2>/dev/null \
  || true

exit 0
