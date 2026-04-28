"""``engram observer install`` CLI command.

Wires :mod:`engram.observer.install` into the click hierarchy so users
can run::

    engram observer install --target=claude-code
    engram observer install --list
    engram observer install --target=codex --dry-run

The command lives under a top-level ``observer`` group so that future
observer subcommands (status, daemon, ...) all share a namespace. The
existing :func:`engram.observer.cli.observe_cmd` is registered at the
top level (``engram observe``) for the hot path; ``engram observer
*`` covers operational commands.
"""

from __future__ import annotations

import json
import sys

import click

from engram.observer.install import (
    INSTALL_TARGETS,
    InstallTargetUnknown,
    apply_install_plan,
    build_install_plan,
    list_install_targets,
)

__all__ = ["observer_group"]


@click.group("observer", help="Operational commands for the observer pipeline.")
def observer_group() -> None:
    pass


@observer_group.command("install", help="Install observer hooks into a host client.")
@click.option(
    "--target",
    type=click.Choice(sorted(INSTALL_TARGETS.keys())),
    required=False,
    default=None,
    help="Which client to install for. Use --list to see all targets.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    default=False,
    help="List all install targets and exit.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned action without writing anything.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def install_cmd(
    target: str | None,
    list_only: bool,
    dry_run: bool,
    fmt: str,
) -> None:
    if list_only:
        _emit_list(fmt)
        return

    if target is None:
        click.echo(
            "error: provide --target or --list. See 'engram observer install --help'.",
            err=True,
        )
        sys.exit(2)

    try:
        plan = build_install_plan(target)
    except InstallTargetUnknown as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(
            json.dumps(
                {
                    "target": plan.target,
                    "action": plan.action,
                    "hook_path": str(plan.hook_path),
                    "config_path": (
                        str(plan.config_path) if plan.config_path is not None else None
                    ),
                    "note": plan.note,
                    "dry_run": dry_run,
                    "snippet": plan.snippet,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"target:      {plan.target}")
        click.echo(f"action:      {plan.action}")
        click.echo(f"hook script: {plan.hook_path}")
        if plan.config_path is not None:
            click.echo(f"config:      {plan.config_path}")
        if plan.note:
            click.echo(f"note:        {plan.note}")
        click.echo("--- snippet ---")
        click.echo(plan.snippet.rstrip("\n"))
        click.echo("--- end ---")

    if plan.action == "write":
        apply_install_plan(plan, dry_run=dry_run)
        if not dry_run:
            click.echo(f"wrote: {plan.config_path}")
        else:
            click.echo("(dry-run; nothing written)")


def _emit_list(fmt: str) -> None:
    rows = [
        {"name": t.name, "action": t.action, "describe": t.describe}
        for t in list_install_targets()
    ]
    if fmt == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            click.echo(f"  {row['name']:<14} [{row['action']}]  {row['describe']}")
