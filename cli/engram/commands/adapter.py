"""``engram adapter`` — install + refresh marker-bounded adapter files (T-55)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from engram.adapters import (
    ADAPTERS,
    AdapterSpec,
    apply_managed_block,
    find_adapter,
)
from engram.adapters.registry import target_path
from engram.cli import GlobalConfig
from engram.core.fs import write_atomic

__all__ = ["adapter_cmd"]


@click.group("adapter")
def adapter_cmd() -> None:
    """Generate and refresh adapter files for LLM-tool integration."""


@adapter_cmd.command("list")
@click.pass_obj
def list_cmd(cfg: GlobalConfig) -> None:
    """List the five canonical adapters and whether each is installed."""
    root = cfg.resolve_project_root()
    entries = [
        {
            "name": a.name,
            "description": a.description,
            "target": str(target_path(root, a).relative_to(root)),
            "installed": target_path(root, a).is_file(),
        }
        for a in ADAPTERS
    ]
    if cfg.output_format == "json":
        click.echo(json.dumps(entries))
        return
    for e in entries:
        status = "installed" if e["installed"] else "absent"
        click.echo(f"{e['name']:<12} {status:<10} {e['target']}")


def _install_one(root: Path, spec: AdapterSpec) -> Path:
    target = target_path(root, spec)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    rendered = apply_managed_block(existing, spec.render())
    write_atomic(target, rendered)
    return target


@adapter_cmd.command("install")
@click.argument("name")
@click.pass_obj
def install_cmd(cfg: GlobalConfig, name: str) -> None:
    """Install the adapter named NAME into the current project."""
    spec = find_adapter(name)
    if spec is None:
        raise click.ClickException(
            f"unknown adapter {name!r}; run `engram adapter list` for the "
            "five canonical names"
        )
    root = cfg.resolve_project_root()
    target = _install_one(root, spec)
    if cfg.output_format == "json":
        click.echo(json.dumps({"adapter": name, "path": str(target)}))
    else:
        click.echo(f"installed {name} → {target.relative_to(root)}")


@adapter_cmd.command("refresh")
@click.argument("name", required=False)
@click.pass_obj
def refresh_cmd(cfg: GlobalConfig, name: str | None) -> None:
    """Refresh one (or every installed) adapter file in place."""
    root = cfg.resolve_project_root()
    if name is not None:
        spec = find_adapter(name)
        if spec is None:
            raise click.ClickException(
                f"unknown adapter {name!r}; run `engram adapter list`"
            )
        _install_one(root, spec)
        click.echo(f"refreshed {name}")
        return

    refreshed: list[str] = []
    for spec in ADAPTERS:
        target = target_path(root, spec)
        if target.is_file():
            _install_one(root, spec)
            refreshed.append(spec.name)
    if cfg.output_format == "json":
        click.echo(json.dumps({"refreshed": refreshed}))
        return
    if not refreshed:
        click.echo("no installed adapters to refresh")
        return
    for n in refreshed:
        click.echo(f"refreshed {n}")
