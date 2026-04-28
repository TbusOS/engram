#!/usr/bin/env bash
# engram observer — Opencode post-tool-use hook (advisory).
#
# Opencode shares hook plumbing with Codex in some configurations.
# When Opencode emits Claude-Code-shaped hook payloads, the
# `--from=claude-code` translator handles them; otherwise we fall
# back to engram-format JSON on stdin.

set -euo pipefail

session_id="${OPENCODE_SESSION_ID:-${ENGRAM_SESSION_ID:-default}}"

if ! command -v engram >/dev/null 2>&1; then
    exit 0
fi

engram observe \
    --session="${session_id}" \
    --client=opencode \
    --from=claude-code 2>/dev/null \
  || engram observe \
    --session="${session_id}" \
    --client=opencode 2>/dev/null \
  || true

exit 0
