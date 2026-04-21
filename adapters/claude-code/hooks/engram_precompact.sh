#!/usr/bin/env bash
# engram Claude Code pre-compact hook.
#
# Runs immediately before Claude Code compacts the conversation
# transcript. This is the cheapest moment to surface engram review
# information for the upcoming compacted prompt — the consistency
# scan runs cheaply against the local store (no LLM, no network) and
# writes its own journal.
#
# DESIGN §20: <500ms hook latency ceiling. Strict.

set -euo pipefail

project_root="${CLAUDE_PROJECT_ROOT:-$PWD}"
cd "$project_root" 2>/dev/null || exit 0

# Best-effort health snapshot. Never block the compaction on failure.
engram review --format=json >/dev/null 2>&1 || true

exit 0
