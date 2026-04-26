"""Click binding for ``engram migrate`` (SPEC §13.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from engram.config_types import GlobalConfig
from engram.migrate.v0_1 import plan_migration, run_migration, run_rollback

__all__ = ["migrate_cmd"]


@click.command("migrate")
@click.option(
    "--from",
    "from_version",
    default=None,
    metavar="SOURCE",
    help="Source format to migrate from. Currently supported: v0.1.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the migration plan without touching disk (SPEC §13.4).",
)
@click.option(
    "--rollback",
    "rollback",
    is_flag=True,
    default=False,
    help="Restore from .memory.pre-v0.2.backup/ (one-time escape hatch).",
)
@click.pass_obj
def migrate_cmd(
    cfg: GlobalConfig,
    from_version: str | None,
    dry_run: bool,
    rollback: bool,
) -> None:
    """Migrate a store to the current v0.2 format (SPEC §13)."""
    if not rollback and not from_version:
        raise click.ClickException("specify --from=<source> or --rollback (see SPEC §13.4)")
    if rollback and from_version:
        raise click.ClickException("--rollback is mutually exclusive with --from")

    root = _resolve_root(cfg)

    if rollback:
        result = run_rollback(root)
        _emit(cfg, result, text=f"rolled back {root} from backup")
        return

    if from_version not in ("v0.1", "0.1"):
        raise click.ClickException(
            f"unsupported migration source {from_version!r}; v0.2 only supports "
            "--from=v0.1 today (SPEC §13.6 adds claude-code / chatgpt / mem0 / "
            "obsidian / letta / mempalace / markdown in M8)"
        )

    if dry_run:
        plan = plan_migration(root)
        _emit(cfg, plan, text=_format_plan_text(plan))
        return

    result = run_migration(root)
    if result.get("already_v0_2"):
        _emit(cfg, result, text=f"{root}: store is already at v0.2 — nothing to do")
        return
    _emit(
        cfg,
        result,
        text=(
            f"migrated {root}: {result['assets_moved']} asset(s) moved to .memory/local/; "
            f"backup at {result['backup_path']}"
        ),
    )


def _resolve_root(cfg: GlobalConfig) -> Path:
    if cfg.dir_override is not None:
        return cfg.dir_override.expanduser().resolve()
    return Path.cwd().resolve()


def _emit(cfg: GlobalConfig, payload: dict[str, Any], *, text: str) -> None:
    if cfg.output_format == "json":
        click.echo(json.dumps(payload))
    else:
        click.echo(text)


def _format_plan_text(plan: dict[str, Any]) -> str:
    lines = [f"dry-run migration for {plan['project_root']}:"]
    for move in plan["moves"]:
        added = ", ".join(move["fields_added"]) or "(no injected fields)"
        lines.append(f"  {move['from']} → {move['to']}  [type={move['type']}, adds: {added}]")
    lines.append(f"backup will be created at {plan['backup_to']}")
    return "\n".join(lines)
