#!/usr/bin/env bash
# engram observer — Opencode post-tool-use hook (advisory).
#
# Opencode shares hook plumbing with Codex in some configurations.
# When Opencode emits Claude-Code-shaped hook payloads, the
# `--from=claude-code` translator handles them; otherwise we fall
# back to engram-format JSON on stdin.

set -euo pipefail

engram_bin="${ENGRAM_BIN:-$(command -v engram 2>/dev/null || true)}"
[ -x "$engram_bin" ] || exit 0

session_id="${OPENCODE_SESSION_ID:-${ENGRAM_SESSION_ID:-}}"
[ -n "$session_id" ] || exit 0

"$engram_bin" observe \
    --session="${session_id}" \
    --client=opencode \
    --from=claude-code 2>/dev/null \
  || "$engram_bin" observe \
    --session="${session_id}" \
    --client=opencode 2>/dev/null \
  || true

exit 0
