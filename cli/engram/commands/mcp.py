"""``engram mcp`` — Model Context Protocol server command (T-51 / T-163)."""

from __future__ import annotations

import json

import click

from engram.cli import GlobalConfig
from engram.mcp import ServerContext, serve_stdio
from engram.mcp.install import INSTALL_TARGETS, install_target, plan_install

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


@mcp_cmd.command("install")
@click.option(
    "--target",
    "target",
    default=None,
    help="MCP client to configure (e.g. claude-desktop, cursor, zed).",
)
@click.option(
    "--list",
    "list_targets",
    is_flag=True,
    default=False,
    help="List supported install targets and exit.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Print the planned change without writing or modifying any file.",
)
@click.pass_obj
def install_cmd(
    cfg: GlobalConfig,
    target: str | None,
    list_targets: bool,
    dry_run: bool,
) -> None:
    """One-line install of the engram MCP server config for a known client.

    Two action modes per target: ``write`` (merges JSON entry into the
    client's stable config file) or ``paste`` (prints a snippet for
    manual installation when the client's config location varies).
    """
    if list_targets:
        for name, spec in INSTALL_TARGETS.items():
            click.echo(f"  {name:<18s} — {spec.describe} [{spec.action}]")
        return

    if target is None:
        raise click.ClickException("--target is required (use --list to see options)")
    if target not in INSTALL_TARGETS:
        raise click.ClickException(
            f"unknown target {target!r}; run `engram mcp install --list`"
        )

    if dry_run:
        plan = plan_install(target)
    else:
        plan = install_target(target)

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "target": plan.target,
                    "action": plan.action,
                    "config_path": str(plan.config_path) if plan.config_path else None,
                    "snippet": plan.snippet,
                    "dry_run": dry_run,
                }
            )
        )
        return

    click.echo(f"target: {plan.target}  action: {plan.action}")
    if plan.config_path:
        verb = "would write" if dry_run else "wrote"
        click.echo(f"  {verb}: {plan.config_path}")
    if plan.action == "paste" or dry_run:
        click.echo("  snippet:")
        for line in plan.snippet.splitlines():
            click.echo(f"    {line}")
