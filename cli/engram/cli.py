"""engram CLI dispatcher — the click root group + global flags.

Subcommands register against this group in later tasks (``engram init`` in
T-17, ``engram memory ...`` in T-19, etc.). This file intentionally stays
thin: it parses global flags, constructs a typed :class:`GlobalConfig`,
configures logging, and stows the config on ``ctx.obj`` so subcommands can
access it via ``@click.pass_obj``. The dispatcher must not know what any
individual subcommand does.

Global flags (DESIGN §9.3 config resolution order):

- ``--dir PATH`` — override the project root. Beats ``ENGRAM_DIR`` and the
  upward walk performed by :func:`engram.core.paths.find_project_root`.
- ``--format {text,json}`` — output format for commands that support
  machine-readable output.
- ``--quiet`` / ``-q`` — suppress non-error output (logging WARNING+).
- ``--debug`` — verbose logging (DEBUG+); wins over ``--quiet`` for level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click

from engram import __version__
from engram.core.paths import find_project_root

__all__ = ["GlobalConfig", "OutputFormat", "cli", "main"]

OutputFormat = Literal["text", "json"]


@dataclass(frozen=True, slots=True)
class GlobalConfig:
    """Runtime configuration shared with every subcommand via ``ctx.obj``."""

    dir_override: Path | None = None
    output_format: OutputFormat = "text"
    quiet: bool = False
    debug: bool = False

    def resolve_project_root(self) -> Path:
        """Return the effective project root.

        Resolution order (DESIGN §9.3):

        1. ``--dir`` CLI flag (``dir_override`` field on this dataclass).
        2. ``ENGRAM_DIR`` env var (honored inside
           :func:`engram.core.paths.find_project_root`).
        3. Walk upward from the current working directory looking for
           ``.memory/``.
        """
        if self.dir_override is not None:
            return self.dir_override.expanduser().resolve()
        return find_project_root()


def _configure_logging(*, quiet: bool, debug: bool) -> None:
    if debug:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    # Force overrides any basicConfig applied by imported libraries.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="engram — long-horizon memory for AI agents.",
)
@click.version_option(__version__, "-V", "--version", prog_name="engram")
@click.option(
    "--dir",
    "dir_override",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    metavar="PATH",
    help=("Override the engram project root. Beats ENGRAM_DIR and the upward walk for .memory/."),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format for commands that support machine-readable output.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress non-error output (logging at WARNING and above only).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging (DEBUG level). Overrides --quiet.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    dir_override: Path | None,
    output_format: OutputFormat,
    quiet: bool,
    debug: bool,
) -> None:
    ctx.obj = GlobalConfig(
        dir_override=dir_override,
        output_format=output_format,
        quiet=quiet,
        debug=debug,
    )
    _configure_logging(quiet=quiet, debug=debug)


main = cli


def _register_subcommands() -> None:
    """Attach subcommands to the root group.

    Deferred to a function so that command modules can import ``GlobalConfig``
    from this module without introducing a circular import.
    """
    from engram.commands.adapter import adapter_cmd
    from engram.commands.config import config_group
    from engram.commands.context import context_cmd
    from engram.commands.doctor import doctor_cmd
    from engram.commands.inbox import inbox_cmd
    from engram.commands.init import init_cmd
    from engram.commands.mcp import mcp_cmd
    from engram.commands.memory import memory_group
    from engram.commands.review import review_cmd
    from engram.commands.status import status_cmd
    from engram.commands.validate import validate_cmd
    from engram.commands.version import version_cmd
    from engram.commands.wisdom import wisdom_cmd
    from engram.migrate import migrate_cmd
    from engram.org import org_group
    from engram.pool import pool_group
    from engram.team import team_group

    cli.add_command(init_cmd)
    cli.add_command(version_cmd)
    cli.add_command(config_group)
    cli.add_command(memory_group)
    cli.add_command(validate_cmd)
    cli.add_command(review_cmd)
    cli.add_command(status_cmd)
    cli.add_command(pool_group)
    cli.add_command(team_group)
    cli.add_command(org_group)
    cli.add_command(migrate_cmd)
    cli.add_command(context_cmd)
    cli.add_command(mcp_cmd)
    cli.add_command(adapter_cmd)
    cli.add_command(inbox_cmd)
    cli.add_command(doctor_cmd)
    cli.add_command(wisdom_cmd)


_register_subcommands()


if __name__ == "__main__":
    main()
