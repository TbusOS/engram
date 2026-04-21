"""Build a click ``Group`` for a given scope kind (``team`` / ``org``).

The CLI shape for every git-backed scope is identical, so we build it once
and instantiate it per kind. This keeps ``engram team``, ``engram org`` (and
any future scope kind) in lockstep: adding a new subcommand to this factory
propagates to every scope automatically.
"""

from __future__ import annotations

import json
from typing import Any

import click

from engram.cli import GlobalConfig
from engram.scope.git_ops import (
    join_scope,
    list_scopes,
    publish_scope,
    status_scope,
    sync_scope,
)

__all__ = ["build_scope_group"]


def build_scope_group(kind: str) -> click.Group:
    """Return a fresh click group implementing ``engram <kind> …`` commands."""

    @click.group(kind)
    def scope_group() -> None:
        pass

    scope_group.help = f"Manage git-backed {kind} scope (SPEC §8.5)."

    # -- join -----------------------------------------------------
    @scope_group.command("join")
    @click.argument("name")
    @click.argument("url")
    @click.pass_obj
    def join_cmd(cfg: GlobalConfig, name: str, url: str) -> None:
        """Clone URL into ``~/.engram/<kind>/<name>/``."""
        dest = join_scope(kind, name, url)
        if cfg.output_format == "json":
            click.echo(json.dumps({"name": name, "path": str(dest)}))
        else:
            click.echo(f"joined {kind} {name!r} at {dest}")

    # -- sync -----------------------------------------------------
    @scope_group.command("sync")
    @click.argument("name", required=False)
    @click.option("--all", "sync_all", is_flag=True, help=f"Sync every joined {kind}.")
    @click.pass_obj
    def sync_cmd(cfg: GlobalConfig, name: str | None, sync_all: bool) -> None:
        """``git pull --ff-only`` one scope or every joined scope with --all."""
        if not sync_all and not name:
            raise click.ClickException(f"specify a {kind} name or pass --all")
        if sync_all and name:
            raise click.ClickException(f"--all is mutually exclusive with a {kind} name")

        if sync_all:
            targets: list[str] = list_scopes(kind)
        else:
            assert name is not None
            targets = [name]
        results = [sync_scope(kind, t) for t in targets]

        if cfg.output_format == "json":
            payload: Any = results if sync_all else (results[0] if results else {})
            click.echo(json.dumps(payload))
            return

        if not any(r["changed"] for r in results):
            if sync_all:
                click.echo(f"all {kind}s up to date")
            elif results:
                click.echo(f"{results[0]['name']}: up to date")
            else:
                click.echo(f"no joined {kind}s")
            return
        for r in results:
            if r["changed"]:
                click.echo(
                    f"{r['name']}: {r['before'][:8]}..{r['after'][:8]} "
                    f"({r['added']}A {r['modified']}M {r['removed']}D)"
                )
            elif sync_all:
                click.echo(f"{r['name']}: up to date")

    # -- publish --------------------------------------------------
    @scope_group.command("publish")
    @click.argument("name")
    @click.option(
        "--message",
        "-m",
        required=True,
        help="Commit message (required, non-empty).",
    )
    @click.pass_obj
    def publish_cmd(cfg: GlobalConfig, name: str, message: str) -> None:
        """``git add -A && git commit -m MSG && git push`` inside the scope."""
        if not message.strip():
            raise click.ClickException("--message cannot be empty")
        result = publish_scope(kind, name, message)
        if cfg.output_format == "json":
            click.echo(json.dumps(result))
            return
        if not result["pushed"]:
            click.echo(f"{name}: nothing to commit (clean working tree)")
        else:
            click.echo(f"published {name}: {result['from_rev'][:8]} → {result['to_rev'][:8]}")

    # -- status ---------------------------------------------------
    @scope_group.command("status")
    @click.argument("name")
    @click.pass_obj
    def status_cmd(cfg: GlobalConfig, name: str) -> None:
        """Print ``git status --porcelain`` for the scope."""
        result = status_scope(kind, name)
        if cfg.output_format == "json":
            click.echo(json.dumps(result))
            return
        if result["clean"]:
            click.echo(f"{name}: clean")
            return
        click.echo(f"{name}: {len(result['changes'])} change(s)")
        for line in result["changes"]:
            click.echo(f"  {line}")

    # -- list -----------------------------------------------------
    @scope_group.command("list")
    @click.pass_obj
    def list_cmd(cfg: GlobalConfig) -> None:
        """List every joined scope under ``~/.engram/<kind>/``."""
        names = list_scopes(kind)
        if cfg.output_format == "json":
            click.echo(json.dumps([{"name": n} for n in names]))
            return
        if not names:
            click.echo(f"no joined {kind}s")
            return
        for n in names:
            click.echo(n)

    return scope_group
