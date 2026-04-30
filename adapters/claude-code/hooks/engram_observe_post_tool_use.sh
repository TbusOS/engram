#!/usr/bin/env bash
# engram observer — Claude Code PostToolUse hook.
#
# Streams one tool-use event into engram's observer queue so the
# auto-continuation pipeline (T-200~T-212) can compact the session
# afterwards. The hook MUST stay under 10 ms (DESIGN §20 caps total
# hook latency at 500 ms; this is the hot path so we budget tight).
#
# Contract:
#   stdin   the JSON object Claude Code feeds the hook (tool_name,
#           tool_input, tool_response, ...).
#   stdout  one engram observe ack line. Ignored by Claude Code.
#   stderr  silenced; never block the host.
#
# Translation: we forward the raw payload to `engram observe --from=
# claude-code` which knows how to map Claude Code's hook JSON into
# engram's event protocol. If translation fails or engram is not on
# PATH, we exit 0 — the observer is best-effort by design.

set -euo pipefail

# Security: honour ENGRAM_BIN written by `engram observer install` so a
# malicious project bin/ on $PATH cannot shadow our binary (security
# reviewer F7). Fall back to PATH lookup only when the env var is not
# set (development checkouts).
engram_bin="${ENGRAM_BIN:-$(command -v engram 2>/dev/null || true)}"
[ -x "$engram_bin" ] || exit 0

# Security: do not invent a session id. F8 — falling back to "default"
# silently merges every Claude Code instance that forgets to set
# CLAUDE_SESSION_ID. Refuse cleanly instead.
session_id="${CLAUDE_SESSION_ID:-${ENGRAM_SESSION_ID:-}}"
[ -n "$session_id" ] || exit 0

# `--from=claude-code` lets engram parse the host-shaped JSON; if the
# flag is unrecognised by an older engram, fall back to passing
# through engram-format JSON verbatim.
"$engram_bin" observe \
    --session="${session_id}" \
    --client=claude-code \
    --from=claude-code 2>/dev/null \
  || "$engram_bin" observe \
    --session="${session_id}" \
    --client=claude-code 2>/dev/null \
  || true

exit 0
