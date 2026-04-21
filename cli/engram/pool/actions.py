"""Reusable pool actions — callable by ``engram pool subscribe`` and by
``engram init --subscribe`` without duplicating logic.

The click subcommands in :mod:`engram.pool.commands` are thin wrappers
around :func:`subscribe_to_pool` below. Keeping the core as a plain
function lets ``init`` orchestrate multi-pool subscription atomically
without spawning nested click invocations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from engram.core.fs import atomic_symlink
from engram.pool.propagation import resolve_pool_target
from engram.pool.subscriptions import (
    pools_toml_path,
    read_toml,
    subscription_link_path,
    user_pool_path,
    write_toml,
)

__all__ = ["subscribe_to_pool"]


_VALID_AT = ("org", "team", "user", "project")
_VALID_MODE = ("auto-sync", "notify", "pinned")


def subscribe_to_pool(
    project_root: Path,
    pool_name: str,
    *,
    subscribed_at: str = "project",
    propagation_mode: str = "auto-sync",
    pinned_revision: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Subscribe ``project_root`` to the pool ``pool_name``.

    Writes a ``[subscribe.<pool_name>]`` table to ``<project>/.memory/pools.toml``
    (SPEC §9.2) and creates the symlink ``<project>/.memory/pools/<pool_name>``
    (SPEC §3.1) that points to the pool's active revision.

    Raises :class:`click.ClickException` on misuse:

    - invalid ``subscribed_at`` / ``propagation_mode``
    - ``pinned_revision`` combined with a non-pinned mode, or missing for pinned
    - pool directory missing at ``~/.engram/pools/<pool_name>/``
    - already subscribed (unless ``force=True``)
    """
    if subscribed_at not in _VALID_AT:
        raise click.ClickException(
            f"invalid subscribed_at {subscribed_at!r}; expected one of {_VALID_AT}"
        )
    if propagation_mode not in _VALID_MODE:
        raise click.ClickException(
            f"invalid propagation_mode {propagation_mode!r}; expected one of {_VALID_MODE}"
        )
    if propagation_mode == "pinned" and not pinned_revision:
        raise click.ClickException(
            "propagation_mode=pinned requires pinned_revision (SPEC §9.2)"
        )
    if propagation_mode != "pinned" and pinned_revision is not None:
        raise click.ClickException("pinned_revision only valid with propagation_mode=pinned")

    pool_dir = user_pool_path(pool_name)
    if not pool_dir.is_dir():
        raise click.ClickException(
            f"pool {pool_name!r} not found at {pool_dir}; "
            "create or git-sync it first (see `engram pool pull`)"
        )

    target, last_synced = resolve_pool_target(pool_name, propagation_mode, pinned_revision)

    toml_path = pools_toml_path(project_root)
    data = read_toml(toml_path)
    subs = data.setdefault("subscribe", {})
    if not isinstance(subs, dict):
        raise click.ClickException("pools.toml `subscribe` key is not a table")
    if pool_name in subs and not force:
        raise click.ClickException(
            f"already subscribed to {pool_name!r}; pass force=True to overwrite"
        )

    entry: dict[str, Any] = {
        "subscribed_at": subscribed_at,
        "propagation_mode": propagation_mode,
    }
    if pinned_revision is not None:
        entry["pinned_revision"] = pinned_revision
    if last_synced is not None:
        entry["last_synced_rev"] = last_synced

    subs[pool_name] = entry
    write_toml(toml_path, data)
    atomic_symlink(target, subscription_link_path(project_root, pool_name))

    return {"pool": pool_name, **entry}
