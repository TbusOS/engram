"""``engram mcp`` — Model Context Protocol server command (T-51)."""

from __future__ import annotations

import click

from engram.cli import GlobalConfig
from engram.mcp import ServerContext, serve_stdio

__all__ = ["mcp_cmd"]


@click.group("mcp")
def mcp_cmd() -> None:
    """Expose engram over the Model Context Protocol (DESIGN §6.2).

    After ``engram mcp serve`` is wired into your client's MCP config,
    any MCP-aware tool — Claude Desktop, Claude Code, Zed, Cursor,
    Opencode, VS Code via Continue.dev / Cline / Copilot — can read
    the store with the ``engram_memory_search`` / ``engram_memory_read``
    / ``engram_context_pack`` tools.
    """


@mcp_cmd.command("serve")
@click.pass_obj
def serve_cmd(cfg: GlobalConfig) -> None:
    """Run a stateless MCP server on stdio until stdin closes."""
    ctx = ServerContext(store_root=cfg.resolve_project_root())
    serve_stdio(ctx)
