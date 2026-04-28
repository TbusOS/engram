"""``engram version`` — print CLI, store schema, Python, and platform versions.

Distinct from the one-liner ``engram --version`` on the root group:
``--version`` prints just the CLI semver; the ``version`` subcommand prints
the full environment summary useful in bug reports.
"""

from __future__ import annotations

import json
import platform
import sys

import click

from engram import __version__
from engram.commands.init import STORE_VERSION
from engram.config_types import GlobalConfig

__all__ = ["version_cmd"]


def _collect() -> dict[str, str]:
    return {
        "engram": __version__,
        "store_schema": STORE_VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }


@click.command("version")
@click.pass_obj
def version_cmd(cfg: GlobalConfig) -> None:
    """Print engram CLI, store schema, Python, and platform versions."""
    info = _collect()
    if cfg.output_format == "json":
        click.echo(json.dumps(info))
        return
    click.echo(f"engram    {info['engram']}")
    click.echo(f"store     v{info['store_schema']}")
    click.echo(f"Python    {info['python']}")
    click.echo(f"platform  {info['platform']}")
