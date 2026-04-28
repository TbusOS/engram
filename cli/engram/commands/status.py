"""``engram status`` — project and scope summary.

Quick readout for "what is this engram project in". Reads:

- ``<project>/.engram/version`` for store schema version.
- ``<project>/.engram/graph.db`` asset counts (by subtype + lifecycle).
- ``<project>/.memory/pools.toml`` for pool subscriptions.

Always exits 0 — ``status`` is informational and must not fail scripts. For
hard validation, use ``engram validate``; for health aggregation use
``engram review``.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import tomli

from engram.commands.memory import graph_db_path
from engram.config_types import GlobalConfig
from engram.core.graph_db import open_graph_db
from engram.core.paths import engram_dir, memory_dir

__all__ = ["Status", "render_json", "render_text", "run_status", "status_cmd"]


@dataclass(frozen=True, slots=True)
class Status:
    project_root: Path
    initialized: bool
    store_version: str | None
    total_assets: int
    by_subtype: dict[str, int]
    by_lifecycle: dict[str, int]
    pool_subscriptions: tuple[dict[str, Any], ...]


def _read_store_version(project_root: Path) -> str | None:
    version_file = engram_dir(project_root) / "version"
    if not version_file.is_file():
        return None
    return version_file.read_text(encoding="utf-8").strip() or None


def _read_pool_subscriptions(project_root: Path) -> tuple[dict[str, Any], ...]:
    pools_toml = memory_dir(project_root) / "pools.toml"
    if not pools_toml.is_file():
        return ()
    try:
        data = tomli.loads(pools_toml.read_text(encoding="utf-8"))
    except tomli.TOMLDecodeError:
        # Malformed pools.toml is reported separately by validate/review;
        # status stays best-effort.
        return ()
    # SPEC §9.2: `[subscribe.<pool-name>]` table of tables.
    subs = data.get("subscribe", {})
    if not isinstance(subs, dict):
        return ()
    out: list[dict[str, Any]] = []
    for name, body in subs.items():
        if not isinstance(body, dict):
            continue
        entry: dict[str, Any] = {"pool": name}
        entry.update(body)
        out.append(entry)
    return tuple(out)


def _count_assets(project_root: Path) -> tuple[int, dict[str, int], dict[str, int]]:
    db_path = graph_db_path(project_root)
    if not db_path.exists():
        return 0, {}, {}
    with open_graph_db(db_path) as conn:
        rows = conn.execute(
            "SELECT subtype, lifecycle_state FROM assets WHERE kind='memory'"
        ).fetchall()
    by_subtype = dict(Counter(r["subtype"] for r in rows))
    by_lifecycle = dict(Counter(r["lifecycle_state"] for r in rows))
    return len(rows), by_subtype, by_lifecycle


def run_status(project_root: Path) -> Status:
    root = project_root.resolve()
    initialized = memory_dir(root).is_dir() and (engram_dir(root) / "version").is_file()
    store_version = _read_store_version(root)
    total, by_subtype, by_lifecycle = _count_assets(root)
    pools = _read_pool_subscriptions(root)
    return Status(
        project_root=root,
        initialized=initialized,
        store_version=store_version,
        total_assets=total,
        by_subtype=by_subtype,
        by_lifecycle=by_lifecycle,
        pool_subscriptions=pools,
    )


def render_text(status: Status) -> str:
    lines: list[str] = []
    lines.append("engram status")
    lines.append("=" * 13)
    lines.append(f"Project:      {status.project_root}")
    if not status.initialized:
        lines.append("Initialized:  no — run `engram init` to create .memory/")
        return "\n".join(lines)

    lines.append(f"Initialized:  yes (store v{status.store_version})")
    lines.append(f"Assets:       {status.total_assets}")
    if status.by_subtype:
        subtypes = ", ".join(f"{k}={v}" for k, v in sorted(status.by_subtype.items()))
        lines.append(f"  by subtype:   {subtypes}")
    if status.by_lifecycle:
        lifecycles = ", ".join(f"{k}={v}" for k, v in sorted(status.by_lifecycle.items()))
        lines.append(f"  by lifecycle: {lifecycles}")

    lines.append(f"Pools:        {len(status.pool_subscriptions)} subscription(s)")
    for sub in status.pool_subscriptions:
        pool = sub.get("pool", "?")
        at = sub.get("subscribed_at", "?")
        mode = sub.get("propagation_mode", "?")
        lines.append(f"  - {pool} (subscribed_at={at}, mode={mode})")
    return "\n".join(lines)


def render_json(status: Status) -> str:
    payload = {
        "project_root": str(status.project_root),
        "initialized": status.initialized,
        "store_version": status.store_version,
        "assets": {
            "total": status.total_assets,
            "by_subtype": status.by_subtype,
            "by_lifecycle": status.by_lifecycle,
        },
        "pools": list(status.pool_subscriptions),
    }
    return json.dumps(payload)


@click.command("status")
@click.pass_obj
def status_cmd(cfg: GlobalConfig) -> None:
    """Print project + scope summary for the current engram project."""
    root = cfg.resolve_project_root()
    status = run_status(root)
    if cfg.output_format == "json":
        click.echo(render_json(status))
    else:
        click.echo(render_text(status))
