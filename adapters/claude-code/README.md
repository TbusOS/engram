# adapters/claude-code/

Reference hooks for wiring engram into Claude Code's session lifecycle.

- `hooks/engram_stop.sh` — runs when a session ends.
- `hooks/engram_precompact.sh` — runs right before conversation compaction.

Both are <500 ms best-effort per DESIGN §20. They never block a
session; any failure degrades silently.

## Install

```bash
chmod +x hooks/*.sh
mkdir -p ~/.claude/hooks/stop ~/.claude/hooks/precompact
ln -sf $PWD/hooks/engram_stop.sh      ~/.claude/hooks/stop/engram.sh
ln -sf $PWD/hooks/engram_precompact.sh ~/.claude/hooks/precompact/engram.sh
```

Claude Code picks up the hooks on next session.

## Also see

- `engram adapter install claude-code` — writes `CLAUDE.md` in the
  project with the marker-bounded engram brief. Separate concern
  from these hooks; install both for full Claude Code integration.
- `engram mcp serve` + `docs/adapter-guides/MCP-CLIENTS.md` — if you
  prefer MCP-based integration over file-based briefing.
