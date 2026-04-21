"""engram Model Context Protocol server (T-51 / T-52).

Implements a stateless, stdio-transport MCP server so any MCP-capable
client can read engram's store without bespoke integration code:

- **Claude Desktop** — add entry to ``claude_desktop_config.json``.
- **Claude Code CLI** — ``claude mcp add engram engram mcp serve``.
- **Opencode / Codex / other terminal agents** — point their MCP config
  at ``engram mcp serve``.
- **Zed** — add to ``~/.config/zed/settings.json`` under ``context_servers``.
- **Cursor** — add to ``~/.cursor/mcp.json``.
- **VS Code** — via Continue.dev / Cline / other MCP-aware extensions.

The server implements the MCP 2024-11-05 baseline: ``initialize``,
``tools/list``, ``tools/call``. Tools are the read-surface of engram
(``engram_memory_read``, ``engram_memory_search``, ``engram_context_pack``).
Write tools (inbox, consistency-apply) land later once their invariants
are stable enough to expose to arbitrary clients.

The protocol handler is a pure ``dispatch(payload, ctx) -> response``
function. The stdio driver is a thin wrapper around it. This split
keeps the protocol unit-testable without a real subprocess.
"""

from engram.mcp.server import ServerContext, dispatch, serve_stdio
from engram.mcp.tools import TOOLS

__all__ = ["TOOLS", "ServerContext", "dispatch", "serve_stdio"]
