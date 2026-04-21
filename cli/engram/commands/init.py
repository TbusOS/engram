"""``engram init`` — create the project-level ``.memory/`` tree.

Writes the minimum viable engram project:

- ``.memory/MEMORY.md`` — landing index skeleton with SPEC §7.2 required
  sections (Identity / Always-on rules / Topics / Subscribed pools /
  Recently added). Sections are empty; the operator fills them as memories
  accumulate.
- ``.memory/pools.toml`` — empty pool subscription file with an example stub
  comment so users know the schema shape.
- ``.memory/{local,pools,workflows,kb}/`` — the SPEC §3.1 project-scope tree.
- ``.engram/version`` — the store version marker (``0.2``) used for v0.1 →
  v0.2 migration detection per SPEC §13.4.

``--no-adapter`` is accepted today as a no-op — adapter file generation
(``CLAUDE.md``, ``AGENTS.md``, ``.cursor/rules/``, etc.) lands with T-55
``engram adapter``. ``--force`` overwrites the skeleton files but **preserves
any content** the user has added under ``local/``, ``workflows/``, ``kb/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from engram.cli import GlobalConfig
from engram.core.fs import write_atomic

__all__ = ["STORE_VERSION", "init_cmd", "init_project"]

STORE_VERSION = "0.2"

_MEMORY_SUBDIRS: tuple[str, ...] = ("local", "pools", "workflows", "kb")


def _memory_md_skeleton(project_name: str) -> str:
    return (
        f"# MEMORY.md\n"
        f"\n"
        f"<!-- engram v{STORE_VERSION} landing index for {project_name}. See SPEC.md §7. -->\n"
        f"\n"
        f"## Identity\n"
        f"\n"
        f"<!-- User profile + any always-loaded identity facts. -->\n"
        f"\n"
        f"## Always-on rules\n"
        f"\n"
        f"<!-- enforcement=mandatory / default feedback rules that must load every session. -->\n"
        f"\n"
        f"## Topics\n"
        f"\n"
        f"<!-- Topic sub-indexes (index/<topic>.md) plus high-frequency inline items. -->\n"
        f"\n"
        f"## Subscribed pools\n"
        f"\n"
        f"<!-- One line per subscribed pool; written by `engram pool subscribe`. -->\n"
        f"\n"
        f"## Recently added\n"
        f"\n"
        f"<!-- Last ~5 assets added, newest first. -->\n"
    )


def _pools_toml_stub() -> str:
    return (
        "# Pool subscriptions for this project. See SPEC §9.2 for the schema.\n"
        "# Example:\n"
        "#\n"
        "# [subscribe.compliance-checklists]\n"
        '# subscribed_at = "team"          # org | team | user | project\n'
        '# propagation_mode = "auto-sync"  # auto-sync | notify | pinned\n'
        '# pinned_revision = null          # required when propagation_mode = "pinned"\n'
    )


def init_project(root: Path, *, name: str | None = None, force: bool = False) -> dict[str, Path]:
    """Create (or re-initialize) the engram project tree at ``root``.

    Returns a dict of logical-name → absolute path for the key artifacts. Raises
    :class:`click.ClickException` if ``.memory/`` already exists and ``force``
    is False. With ``force=True`` the skeleton files (MEMORY.md, pools.toml,
    .engram/version) are overwritten but existing subdirectory content under
    ``local/``, ``workflows/``, ``kb/`` is left untouched.
    """
    memory = root / ".memory"
    engram = root / ".engram"

    if memory.exists() and not force:
        raise click.ClickException(
            f"{memory}/ already exists; re-run with --force to re-initialize."
        )

    project_name = name or root.resolve().name

    memory.mkdir(parents=True, exist_ok=True)
    for sub in _MEMORY_SUBDIRS:
        (memory / sub).mkdir(parents=True, exist_ok=True)

    engram.mkdir(parents=True, exist_ok=True)
    write_atomic(engram / "version", f"{STORE_VERSION}\n")
    write_atomic(memory / "MEMORY.md", _memory_md_skeleton(project_name))
    write_atomic(memory / "pools.toml", _pools_toml_stub())

    return {
        "memory": memory,
        "engram": engram,
        "version_file": engram / "version",
        "landing_index": memory / "MEMORY.md",
        "pools_toml": memory / "pools.toml",
    }


@click.command("init")
@click.option(
    "--name",
    default=None,
    metavar="NAME",
    help="Project name used in the MEMORY.md skeleton header. "
    "Defaults to the target directory name.",
)
@click.option(
    "--no-adapter",
    is_flag=True,
    default=False,
    help="Skip adapter file generation. Accepted today as a no-op — "
    "adapter file generation (CLAUDE.md / AGENTS.md / .cursor/rules) "
    "lands with T-55 `engram adapter`.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-initialize even if .memory/ already exists. Skeleton files are "
    "overwritten; existing local/, workflows/, kb/ content is preserved.",
)
@click.pass_obj
def init_cmd(
    cfg: GlobalConfig,
    name: str | None,
    no_adapter: bool,
    force: bool,
) -> None:
    """Initialize an engram project at the target directory (cwd or --dir)."""
    target = cfg.dir_override.expanduser().resolve() if cfg.dir_override else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    paths = init_project(target, name=name, force=force)

    if cfg.output_format == "json":
        click.echo(json.dumps({k: str(p) for k, p in paths.items()}))
    else:
        click.echo(f"engram initialized at {paths['memory']}")
