"""Click group + subcommand bindings for ``engram pool``."""

from __future__ import annotations

import json
import shutil
from typing import Any

import click

from engram.cli import GlobalConfig
from engram.pool.actions import subscribe_to_pool
from engram.pool.git_sync import list_git_pools, pool_has_git, pull_pool
from engram.pool.propagation import sync_subscriptions
from engram.pool.subscriptions import (
    pools_toml_path,
    read_toml,
    subscription_link_path,
    user_pool_path,
    write_toml,
)

__all__ = ["pool_group"]


_VALID_AT = ("org", "team", "user", "project")
_VALID_MODE = ("auto-sync", "notify", "pinned")


@click.group("pool")
def pool_group() -> None:
    """Manage pool subscriptions (SPEC §9)."""


# ------------------------------------------------------------------
# subscribe
# ------------------------------------------------------------------


@pool_group.command("subscribe")
@click.argument("name")
@click.option(
    "--at",
    "subscribed_at",
    type=click.Choice(_VALID_AT),
    default="project",
    show_default=True,
    help="Effective hierarchy level for conflict resolution (SPEC §8.2).",
)
@click.option(
    "--mode",
    "propagation_mode",
    type=click.Choice(_VALID_MODE),
    default="auto-sync",
    show_default=True,
    help="Propagation mode (SPEC §9.3).",
)
@click.option(
    "--revision",
    "pinned_revision",
    default=None,
    help="Pin to this revision id (required and only valid with --mode=pinned).",
)
@click.option("--force", is_flag=True, help="Overwrite an existing subscription.")
@click.pass_obj
def subscribe_cmd(
    cfg: GlobalConfig,
    name: str,
    subscribed_at: str,
    propagation_mode: str,
    pinned_revision: str | None,
    force: bool,
) -> None:
    """Subscribe the current project to pool NAME."""
    root = cfg.resolve_project_root()
    entry = subscribe_to_pool(
        root,
        name,
        subscribed_at=subscribed_at,
        propagation_mode=propagation_mode,
        pinned_revision=pinned_revision,
        force=force,
    )

    if cfg.output_format == "json":
        click.echo(json.dumps(entry))
    else:
        click.echo(f"subscribed to {name} (subscribed_at={subscribed_at}, mode={propagation_mode})")


# ------------------------------------------------------------------
# unsubscribe
# ------------------------------------------------------------------


@pool_group.command("unsubscribe")
@click.argument("name")
@click.pass_obj
def unsubscribe_cmd(cfg: GlobalConfig, name: str) -> None:
    """Remove a pool subscription from the current project."""
    root = cfg.resolve_project_root()
    data = read_toml(pools_toml_path(root))
    subs = data.get("subscribe", {}) if isinstance(data.get("subscribe"), dict) else {}
    if name not in subs:
        raise click.ClickException(f"not subscribed to {name!r}")

    del subs[name]
    if not subs:
        data.pop("subscribe", None)
    write_toml(pools_toml_path(root), data)

    link = subscription_link_path(root, name)
    if link.is_symlink() or link.exists():
        if link.is_symlink() or link.is_file():
            link.unlink()
        else:
            shutil.rmtree(link)

    if cfg.output_format == "json":
        click.echo(json.dumps({"unsubscribed": name}))
    else:
        click.echo(f"unsubscribed from {name}")


# ------------------------------------------------------------------
# sync
# ------------------------------------------------------------------


@pool_group.command("sync")
@click.argument("name", required=False)
@click.option(
    "--all",
    "sync_all",
    is_flag=True,
    help="Sync every auto-sync / notify subscription.",
)
@click.pass_obj
def sync_cmd(cfg: GlobalConfig, name: str | None, sync_all: bool) -> None:
    """Refresh ``last_synced_rev`` for auto-sync subscriptions (SPEC §9.3)."""
    if not sync_all and not name:
        raise click.ClickException("specify a pool name or pass --all")
    if sync_all and name:
        raise click.ClickException("--all is mutually exclusive with a pool name")

    root = cfg.resolve_project_root()
    data = read_toml(pools_toml_path(root))
    raw = data.get("subscribe")
    subs = raw if isinstance(raw, dict) else {}

    targets: list[str]
    if not sync_all:
        assert name is not None
        if name not in subs:
            raise click.ClickException(f"not subscribed to {name!r}")
        targets = [name]
    else:
        targets = list(subs.keys())

    results = sync_subscriptions(subs, root, targets)
    write_toml(pools_toml_path(root), data)

    if cfg.output_format == "json":
        payload: Any = results if sync_all else (results[0] if results else {})
        click.echo(json.dumps(payload))
        return

    advanced = [r for r in results if r["changed"]]
    if not advanced:
        click.echo("all subscriptions up to date" if sync_all else f"{name}: up to date")
        return
    for r in advanced:
        click.echo(f"{r['pool']}: {r['from_rev']} → {r['to_rev']}")


# ------------------------------------------------------------------
# pull (git sync)
# ------------------------------------------------------------------


@pool_group.command("pull")
@click.argument("name", required=False)
@click.option("--all", "pull_all", is_flag=True, help="Pull every git-backed pool.")
@click.pass_obj
def pull_cmd(cfg: GlobalConfig, name: str | None, pull_all: bool) -> None:
    """``git pull --ff-only`` inside pool directories (SPEC §9.1 git-sync)."""
    if not pull_all and not name:
        raise click.ClickException("specify a pool name or pass --all")
    if pull_all and name:
        raise click.ClickException("--all is mutually exclusive with a pool name")

    if pull_all:
        targets = list_git_pools()
    else:
        assert name is not None
        pool_dir = user_pool_path(name)
        if not pool_dir.is_dir():
            raise click.ClickException(f"pool {name!r} not found at {pool_dir}")
        if not pool_has_git(name):
            raise click.ClickException(f"pool {name!r} is not a git repository at {pool_dir}")
        targets = [name]

    results = [pull_pool(user_pool_path(n)) for n in targets]

    if cfg.output_format == "json":
        payload: Any = results if pull_all else (results[0] if results else {})
        click.echo(json.dumps(payload))
        return

    if not any(r["changed"] for r in results):
        if pull_all:
            click.echo("all git-backed pools up to date")
        elif results:
            click.echo(f"{results[0]['pool']}: up to date")
        else:
            click.echo("no git-backed pools found")
        return
    for r in results:
        if r["changed"]:
            before = r["before"][:8]
            after = r["after"][:8]
            click.echo(
                f"{r['pool']}: {before}..{after} ({r['added']}A {r['modified']}M {r['removed']}D)"
            )
        elif pull_all:
            click.echo(f"{r['pool']}: up to date")


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


@pool_group.command("list")
@click.pass_obj
def list_cmd(cfg: GlobalConfig) -> None:
    """List pool subscriptions for the current project."""
    from engram.pool.subscriptions import read_subscriptions

    root = cfg.resolve_project_root()
    subs = read_subscriptions(root)

    if cfg.output_format == "json":
        payload = [{"pool": name, **body} for name, body in sorted(subs.items())]
        click.echo(json.dumps(payload))
        return

    if not subs:
        click.echo("no pool subscriptions")
        return
    for name, body in sorted(subs.items()):
        at = body.get("subscribed_at", "?")
        mode = body.get("propagation_mode", "?")
        rev = body.get("pinned_revision")
        extra = f" @ {rev}" if rev else ""
        click.echo(f"{name:<32s} subscribed_at={at:<7s} mode={mode}{extra}")
