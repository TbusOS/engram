"""pools.toml IO + subscription symlink helpers (SPEC §9.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import tomli
import tomli_w

from engram.core.fs import write_atomic
from engram.core.paths import memory_dir, user_root

__all__ = [
    "pools_toml_path",
    "read_subscriptions",
    "read_toml",
    "subscription_link_path",
    "user_pool_path",
    "write_toml",
]


def pools_toml_path(project_root: Path) -> Path:
    """``<project>/.memory/pools.toml`` — the subscriber's subscription file."""
    return memory_dir(project_root) / "pools.toml"


def user_pool_path(pool_name: str) -> Path:
    """``~/.engram/pools/<pool_name>/`` — the machine-local pool directory."""
    return user_root() / "pools" / pool_name


def subscription_link_path(project_root: Path, pool_name: str) -> Path:
    """``<project>/.memory/pools/<pool_name>`` — the symlink a subscribe creates."""
    return memory_dir(project_root) / "pools" / pool_name


def read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file (or return ``{}`` if missing). Click-friendly errors."""
    if not path.is_file():
        return {}
    try:
        return tomli.loads(path.read_text(encoding="utf-8"))
    except tomli.TOMLDecodeError as exc:
        raise click.ClickException(f"malformed pools.toml: {exc}") from exc


def write_toml(path: Path, data: dict[str, Any]) -> None:
    """Atomic TOML write (tomli_w + write_atomic). Ensures trailing newline."""
    rendered = tomli_w.dumps(data)
    if not rendered.endswith("\n"):
        rendered += "\n"
    write_atomic(path, rendered)


def read_subscriptions(project_root: Path) -> dict[str, dict[str, Any]]:
    """Parse ``[subscribe.<name>]`` tables from the project's pools.toml."""
    data = read_toml(pools_toml_path(project_root))
    subs = data.get("subscribe", {})
    if not isinstance(subs, dict):
        return {}
    return {name: body for name, body in subs.items() if isinstance(body, dict)}
