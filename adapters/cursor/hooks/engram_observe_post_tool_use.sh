#!/usr/bin/env bash
# engram observer — Cursor IDE post-tool-use hook (advisory).
#
# Cursor does not yet expose a first-class PostToolUse hook surface in
# its public API the way Claude Code / Codex do. This script exists so
# that:
#   1. when Cursor adds the surface, the install path is already in
#      place;
#   2. users running custom MCP/SDK wrappers around Cursor can call
#      this script directly to feed events.
#
# It accepts engram-format JSON on stdin (the standard wire protocol)
# and forwards to `engram observe`. Translation from a host-specific
# format is a future enhancement.

set -euo pipefail

engram_bin="${ENGRAM_BIN:-$(command -v engram 2>/dev/null || true)}"
[ -x "$engram_bin" ] || exit 0

session_id="${CURSOR_SESSION_ID:-${ENGRAM_SESSION_ID:-}}"
[ -n "$session_id" ] || exit 0

"$engram_bin" observe \
    --session="${session_id}" \
    --client=cursor 2>/dev/null \
  || true

exit 0
