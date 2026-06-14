# Connecting MCP clients to engram

Every tool in this list can read an engram store through the same
``engram mcp serve`` command. The server is stateless and stdio-based;
no port to open, no daemon to keep alive — the client launches the
subprocess, talks JSON-RPC over stdin/stdout, and kills it when done.

Each snippet below assumes ``engram`` is on your ``PATH`` (``pip install -e
./cli`` in the engram repo, or a release build). If you want the server
to serve a specific store regardless of the client's cwd, pass
``--dir=/abs/path/to/project``.

---

## Claude Desktop

Edit ``~/Library/Application Support/Claude/claude_desktop_config.json``
(macOS) or the equivalent on Windows / Linux:

```json
{
  "mcpServers": {
    "engram": {
      "command": "engram",
      "args": ["mcp", "serve"]
    }
  }
}
```

## Claude Code CLI

One-shot config:

```bash
claude mcp add engram engram mcp serve
```

Or edit ``~/.claude/mcp.json`` directly:

```json
{
  "mcpServers": {
    "engram": { "command": "engram", "args": ["mcp", "serve"] }
  }
}
```

## Opencode (opencode.ai)

Opencode reads ``AGENTS.md`` + supports MCP. Add to
``~/.config/opencode/mcp.json``:

```json
{
  "mcpServers": {
    "engram": { "command": "engram", "args": ["mcp", "serve"] }
  }
}
```

## Zed

Edit ``~/.config/zed/settings.json``:

```json
{
  "context_servers": {
    "engram": {
      "command": { "path": "engram", "args": ["mcp", "serve"] }
    }
  }
}
```

## Cursor

Edit ``~/.cursor/mcp.json``:

```json
{
  "mcpServers": {
    "engram": { "command": "engram", "args": ["mcp", "serve"] }
  }
}
```

## VS Code

VS Code supports MCP through several extensions; pick any one:

- **Continue.dev** — settings.json → ``continue.experimental.modelContextProtocolServers``:

  ```json
  [
    {
      "transport": { "type": "stdio", "command": "engram", "args": ["mcp", "serve"] }
    }
  ]
  ```

- **Cline** — ``~/.cline/mcp_settings.json``:

  ```json
  { "mcpServers": { "engram": { "command": "engram", "args": ["mcp", "serve"] } } }
  ```

- **GitHub Copilot Chat (MCP preview)** — follow the extension's
  in-app "Add MCP server" flow, pointing ``command`` at ``engram`` and
  ``args`` at ``["mcp", "serve"]``.

## Codex CLI

Codex reads AGENTS.md and supports MCP. Configure in
``~/.codex/mcp.json``:

```json
{
  "mcpServers": {
    "engram": { "command": "engram", "args": ["mcp", "serve"] }
  }
}
```

## Generic — any MCP-speaking client

If your tool supports the MCP 2024-11-05 spec, point its MCP config at:

- **command**: ``engram``
- **args**: ``["mcp", "serve"]``
- **transport**: stdio

The exposed tools are:

Read:

- ``engram_memory_search`` — BM25 + scope/enforcement-weighted search.
- ``engram_memory_read`` — read one asset by id.
- ``engram_context_pack`` — Relevance Gate context assembly.
- ``engram_inbox_list`` — list inbox messages addressed to this repo.

Write (a connected client can curate the store):

- ``engram_memory_add`` — create a new memory asset (project scope, ``local/``).
- ``engram_inbox_send`` — send a cross-repo message (rate-limited, deduplicated).

Enabling the server grants the connected client these mutation rights;
writes are deliberate actions (the same consent model as ``engram
distill promote``) and are validated + size-capped server-side.

---

## Troubleshooting

**Nothing happens when the client starts up.** Run ``engram mcp serve``
by hand from the project dir; it should block on stdin. If it exits
immediately, check that you ran ``pip install -e ./cli`` and that the
current directory has a ``.memory/`` (or pass ``--dir``).

**Tool calls return "asset not found".** The server resolves the store
from its cwd. Either ``cd`` into the project before launching the
client, or pass ``--dir=/abs/path`` in the client's ``args``.

**Search returns nothing.** Run ``engram memory list`` at the same
project — if that returns the assets, the MCP server will too. If
memory list is empty, you're pointing at the wrong store.
