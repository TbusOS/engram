"""Leaf module for ``GlobalConfig`` so command modules can import it
without pulling ``engram.cli`` (which triggers ``_register_subcommands``
at module load and produces hard-to-debug circular imports).

Anything mutating click groups stays in ``engram.cli``. Anything that
just needs the typed runtime config object lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = ["GlobalConfig", "OutputFormat"]


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

        1. ``--dir`` flag (``self.dir_override``)
        2. ``ENGRAM_DIR`` environment variable (handled inside ``find_project_root``)
        3. Walk up from cwd looking for a ``.memory/`` directory

        When no project can be found, raises :class:`click.ClickException`
        so the CLI prints a one-line "run `engram init`" hint and exits
        cleanly, rather than dumping a ``ProjectNotFoundError`` traceback
        (every command funnels through here).
        """
        # Lazy imports keep this module a pure leaf (no engram.cli pull-in).
        import click

        from engram.core.paths import ProjectNotFoundError, find_project_root

        if self.dir_override is not None:
            return self.dir_override.expanduser().resolve()
        try:
            return find_project_root()
        except ProjectNotFoundError as exc:
            raise click.ClickException(
                "no engram project found here. Run `engram init` to create "
                "one, or pass `--dir <path>` to point at an existing store."
            ) from exc
