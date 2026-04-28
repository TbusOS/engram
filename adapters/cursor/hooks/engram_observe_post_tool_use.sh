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

session_id="${CURSOR_SESSION_ID:-${ENGRAM_SESSION_ID:-default}}"

if ! command -v engram >/dev/null 2>&1; then
    exit 0
fi

engram observe \
    --session="${session_id}" \
    --client=cursor 2>/dev/null \
  || true

exit 0
