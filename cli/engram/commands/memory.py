"""``engram memory`` — CRUD + BM25 search over project-scope memories.

This module is the click/CLI layer: the ``memory`` command group and its
``add`` / ``quick`` / ``list`` / ``read`` / ``update`` / ``archive`` /
``search`` subcommands. The domain logic lives in the :mod:`engram.memory`
package — id/path helpers (``ident``), serialization (``render``), the
MEMORY.md index (``index_md``), quick-derivation (``derive``), and the shared
write path (``write``).

For backward compatibility this module re-exports that surface, so existing
callers (``from engram.commands.memory import graph_db_path`` /
``create_memory`` / ``slugify`` / …) keep working unchanged.

**M2 deviation from DESIGN §3.2**: graph.db lives at
``<project>/.engram/graph.db`` instead of ``~/.engram/graph.db`` (see
:func:`engram.memory.ident.graph_db_path` and the project memory
``project_graph_db_location_m2_vs_design``).
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import click

from engram.config_types import GlobalConfig
from engram.core.frontmatter import (
    Enforcement,
    FrontmatterError,
    MemoryFrontmatter,
    MemoryType,
    Scope,
    parse_file,
)
from engram.core.fs import write_atomic
from engram.core.graph_db import get_asset, open_graph_db
from engram.core.paths import memory_dir, user_root
from engram.memory.derive import derive_quick_description, derive_quick_name
from engram.memory.ident import (
    compute_id,
    graph_db_path,
    memory_file_path,
    sha256_hex,
    slugify,
)
from engram.memory.index_md import remove_from_memory_index
from engram.memory.render import frontmatter_to_dict, render_asset_file
from engram.memory.write import (
    MemoryWriteError,
    create_memory,
    resolve_quick_slug,
)
from engram.relevance.bm25 import bm25_scores as _bm25_scores
from engram.relevance.weights import (
    ENFORCEMENT_WEIGHTS,
    SCOPE_WEIGHTS,
    apply_scope_weighting,
)

__all__ = [
    "ENFORCEMENT_WEIGHTS",
    "SCOPE_WEIGHTS",
    "MemoryWriteError",
    "apply_scope_weighting",
    "bm25_scores",
    "compute_id",
    "create_memory",
    "derive_quick_description",
    "derive_quick_name",
    "graph_db_path",
    "memory_file_path",
    "memory_group",
    "render_asset_file",
    "sha256_hex",
    "slugify",
]


def _read_body_flag(raw: str) -> str:
    """Resolve --body; ``-`` reads from stdin."""
    if raw == "-":
        return sys.stdin.read()
    return raw


# ------------------------------------------------------------------
# click group
# ------------------------------------------------------------------


@click.group("memory")
def memory_group() -> None:
    """Manage memory assets in the current engram project."""


# -- add -----------------------------------------------------------


@memory_group.command("add")
@click.option(
    "--type",
    "memory_type",
    required=True,
    type=click.Choice([t.value for t in MemoryType]),
    help="Memory subtype (SPEC §4).",
)
@click.option("--name", required=True, help="Short human-readable title.")
@click.option(
    "--description",
    required=True,
    help="One-line relevance hook (≤150 chars).",
)
@click.option(
    "--body",
    required=True,
    help="Asset body; pass `-` to read from stdin.",
)
@click.option(
    "--scope",
    default=Scope.PROJECT.value,
    type=click.Choice([s.value for s in Scope]),
    show_default=True,
    help="Scope (M2 focuses on project; other scopes land in M3).",
)
@click.option(
    "--enforcement",
    default=None,
    type=click.Choice([e.value for e in Enforcement]),
    help="Enforcement level (required for type=feedback per SPEC §4.3).",
)
@click.option("--tags", multiple=True, help="Repeatable topic tag.")
@click.option("--source", default=None, help="Origin of the claim.")
@click.option(
    "--workflow-ref",
    default=None,
    help="Required for type=workflow_ptr per SPEC §4.6.",
)
@click.option("--force", is_flag=True, help="Overwrite existing asset with the same id.")
@click.pass_obj
def add_cmd(
    cfg: GlobalConfig,
    memory_type: str,
    name: str,
    description: str,
    body: str,
    scope: str,
    enforcement: str | None,
    tags: tuple[str, ...],
    source: str | None,
    workflow_ref: str | None,
    force: bool,
) -> None:
    """Create a memory asset from flags."""
    root = cfg.resolve_project_root()
    body_text = _read_body_flag(body)
    try:
        result = create_memory(
            root,
            memory_type=memory_type,
            name=name,
            description=description,
            body=body_text,
            scope=scope,
            enforcement=enforcement,
            tags=tags,
            source=source,
            workflow_ref=workflow_ref,
            force=force,
        )
    except MemoryWriteError as exc:
        raise click.ClickException(str(exc)) from exc

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "id": result["id"],
                    "path": result["path"],
                    "sha256": result["sha256"],
                    "size_bytes": result["size_bytes"],
                }
            )
        )
    else:
        click.echo(f"added {result['id']} → {result['path']}")


# -- quick ---------------------------------------------------------


@memory_group.command("quick")
@click.argument("body", required=True)
@click.option(
    "--type",
    "memory_type",
    default=MemoryType.PROJECT.value,
    type=click.Choice([t.value for t in MemoryType]),
    show_default=True,
    help="Memory subtype (defaults to `project`; SPEC §4 has no `note` subtype, "
    "`project` is the closest semantic match for an ad-hoc fact).",
)
@click.option("--name", "name_override", default=None, help="Override the auto-derived name.")
@click.option(
    "--description",
    "description_override",
    default=None,
    help="Override the auto-derived description (≤150 chars).",
)
@click.option(
    "--scope",
    default=Scope.PROJECT.value,
    type=click.Choice([s.value for s in Scope]),
    show_default=True,
    help="Scope (defaults to project; the quick path is intentionally local).",
)
@click.option(
    "--enforcement",
    default=None,
    type=click.Choice([e.value for e in Enforcement]),
    help="Enforcement level. Defaults to `default` when --type=feedback "
    "(required by SPEC §4.3); ignored otherwise.",
)
@click.option("--tags", multiple=True, help="Repeatable topic tag.")
@click.pass_obj
def quick_cmd(
    cfg: GlobalConfig,
    body: str,
    memory_type: str,
    name_override: str | None,
    description_override: str | None,
    scope: str,
    enforcement: str | None,
    tags: tuple[str, ...],
) -> None:
    """Record a memory in one line — name/description auto-derived from BODY.

    Reads BODY positionally; pass ``-`` to read from stdin. The asset is
    written under ``local/<type>_<slug>.md`` and registered to graph.db
    exactly like ``engram memory add``, but with auto-derived name and
    description so a session can capture a thought without four required
    flags.
    """
    body_text = _read_body_flag(body)
    if not body_text.strip():
        raise click.ClickException("body is empty; pass non-empty text or stdin via `-`")

    derived_name = name_override or derive_quick_name(body_text)
    derived_description = description_override or derive_quick_description(body_text)

    # SPEC §4.3 requires enforcement on feedback assets; quick supplies a
    # safe default so the operator does not have to remember.
    if memory_type == MemoryType.FEEDBACK.value and enforcement is None:
        enforcement = Enforcement.DEFAULT.value

    root = cfg.resolve_project_root()
    scope_dir = "local"
    base_slug = slugify(derived_name)
    final_slug, final_name = resolve_quick_slug(
        root, scope_dir, memory_type, base_slug, derived_name
    )

    try:
        result = create_memory(
            root,
            memory_type=memory_type,
            name=final_name,
            description=derived_description,
            body=body_text,
            scope=scope,
            enforcement=enforcement,
            tags=tags,
            slug=final_slug,
        )
    except MemoryWriteError as exc:
        raise click.ClickException(str(exc)) from exc

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "id": result["id"],
                    "path": result["path"],
                    "name": result["name"],
                    "sha256": result["sha256"],
                    "size_bytes": result["size_bytes"],
                }
            )
        )
    else:
        click.echo(f"added {result['id']} → {result['path']}")


# -- list ----------------------------------------------------------


@memory_group.command("list")
@click.pass_obj
def list_cmd(cfg: GlobalConfig) -> None:
    """List every memory asset registered in the project graph.db."""
    root = cfg.resolve_project_root()
    with open_graph_db(graph_db_path(root)) as conn:
        rows = conn.execute(
            "SELECT id, subtype, scope, lifecycle_state, enforcement "
            "FROM assets WHERE kind = 'memory' ORDER BY id"
        ).fetchall()

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                [
                    {
                        "id": r["id"],
                        "subtype": r["subtype"],
                        "scope": r["scope"],
                        "lifecycle_state": r["lifecycle_state"],
                        "enforcement": r["enforcement"],
                    }
                    for r in rows
                ]
            )
        )
        return

    if not rows:
        click.echo("no memories")
        return
    for r in rows:
        click.echo(
            f"{r['id']:<45s} {r['subtype']:<12s} {r['scope']:<8s} "
            f"{r['lifecycle_state']:<10s} {r['enforcement'] or '-'}"
        )


# -- read ----------------------------------------------------------


@memory_group.command("read")
@click.argument("memory_id")
@click.pass_obj
def read_cmd(cfg: GlobalConfig, memory_id: str) -> None:
    """Print a memory asset by its id (e.g. ``local/user_kernel_fluency``)."""
    root = cfg.resolve_project_root()
    with open_graph_db(graph_db_path(root)) as conn:
        row = get_asset(conn, memory_id)
    if row is None:
        raise click.ClickException(f"asset not found: {memory_id}")

    file_path = memory_dir(root) / row["path"]
    fm, body = parse_file(file_path)

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "id": memory_id,
                    "path": str(file_path),
                    "frontmatter": frontmatter_to_dict(fm),
                    "body": body,
                }
            )
        )
        return

    click.echo(file_path.read_text(encoding="utf-8"))


# -- update --------------------------------------------------------


_LIFECYCLE_STATES = ("draft", "active", "stable", "deprecated", "archived")


@memory_group.command("update")
@click.argument("memory_id")
@click.option("--description", default=None, help="Replace the description field.")
@click.option("--body", default=None, help="Replace the body (`-` reads from stdin).")
@click.option(
    "--enforcement",
    default=None,
    type=click.Choice([e.value for e in Enforcement]),
    help="Change enforcement level.",
)
@click.option(
    "--lifecycle",
    default=None,
    type=click.Choice(_LIFECYCLE_STATES),
    help="Change lifecycle_state (per SPEC §4.0 lifecycle).",
)
@click.option(
    "--tags",
    multiple=True,
    help="Replace tags with these values (repeatable; pass zero to clear).",
)
@click.pass_obj
def update_cmd(
    cfg: GlobalConfig,
    memory_id: str,
    description: str | None,
    body: str | None,
    enforcement: str | None,
    lifecycle: str | None,
    tags: tuple[str, ...],
) -> None:
    """Update fields on an existing memory asset. Bumps the ``updated`` date."""
    root = cfg.resolve_project_root()
    with open_graph_db(graph_db_path(root)) as conn:
        row = get_asset(conn, memory_id)
        if row is None:
            raise click.ClickException(f"asset not found: {memory_id}")
        file_path = memory_dir(root) / row["path"]
        fm, old_body = parse_file(file_path)

        new_description = description if description is not None else fm.description
        new_body = _read_body_flag(body) if body is not None else old_body
        new_enforcement = Enforcement(enforcement) if enforcement is not None else fm.enforcement
        new_tags = tuple(tags) if tags else fm.tags
        today_iso = date.today().isoformat()

        updated_fm = MemoryFrontmatter(
            name=fm.name,
            description=new_description,
            type=fm.type,
            scope=fm.scope,
            enforcement=new_enforcement,
            org=fm.org,
            team=fm.team,
            pool=fm.pool,
            subscribed_at=fm.subscribed_at,
            created=fm.created,
            updated=date.today(),
            tags=new_tags,
            expires=fm.expires,
            valid_from=fm.valid_from,
            valid_to=fm.valid_to,
            source=fm.source,
            references=fm.references,
            overrides=fm.overrides,
            supersedes=fm.supersedes,
            limitations=fm.limitations,
            confidence=fm.confidence,
            workflow_ref=fm.workflow_ref,
            extra=fm.extra,
        )
        content = render_asset_file(updated_fm, new_body)
        write_atomic(file_path, content)

        new_lifecycle = lifecycle if lifecycle is not None else row["lifecycle_state"]
        conn.execute(
            "UPDATE assets SET "
            "updated = ?, enforcement = ?, lifecycle_state = ?, "
            "sha256 = ?, size_bytes = ? WHERE id = ?",
            (
                today_iso,
                new_enforcement.value,
                new_lifecycle,
                sha256_hex(content),
                len(content.encode("utf-8")),
                memory_id,
            ),
        )
        conn.commit()

    if cfg.output_format == "json":
        click.echo(json.dumps({"id": memory_id, "path": str(file_path)}))
    else:
        click.echo(f"updated {memory_id}")


# -- archive -------------------------------------------------------


@memory_group.command("archive")
@click.argument("memory_id")
@click.pass_obj
def archive_cmd(cfg: GlobalConfig, memory_id: str) -> None:
    """Move the asset file to ``~/.engram/archive/YYYY/MM/`` and mark it archived.

    SPEC §3.5 retains archived files for six months before physical removal.
    Deletion is never performed by ``engram memory archive``; that action
    belongs to a separate archive-cleanup routine.
    """
    root = cfg.resolve_project_root()
    with open_graph_db(graph_db_path(root)) as conn:
        row = get_asset(conn, memory_id)
        if row is None:
            raise click.ClickException(f"asset not found: {memory_id}")
        src = memory_dir(root) / row["path"]
        today = date.today()
        archive_dir = (
            user_root()
            / "archive"
            / f"{today.year:04d}"
            / f"{today.month:02d}"
            / Path(row["path"]).parent
        )
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / Path(row["path"]).name
        shutil.move(src, dest)

        conn.execute(
            "UPDATE assets SET lifecycle_state = 'archived', updated = ? WHERE id = ?",
            (today.isoformat(), memory_id),
        )
        conn.commit()

    # T-181: keep MEMORY.md links honest. Without this, archived assets
    # leave dangling [name](local/...) entries that trip E-IDX-001.
    remove_from_memory_index(root, rel_path=row["path"])

    if cfg.output_format == "json":
        click.echo(json.dumps({"id": memory_id, "archived_to": str(dest)}))
    else:
        click.echo(f"archived {memory_id} → {dest}")


# -- search (BM25) -------------------------------------------------
#
# The real implementation lives in engram.relevance.bm25 (T-42). This
# thin re-export keeps the legacy `engram.commands.memory.bm25_scores`
# import path working for existing tests and downstream consumers.


def bm25_scores(
    query: str,
    documents: list[tuple[str, str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    """Backwards-compat re-export of :func:`engram.relevance.bm25.bm25_scores`."""
    return _bm25_scores(query, documents, k1=k1, b=b)


@memory_group.command("search")
@click.argument("query")
@click.option(
    "--limit",
    default=10,
    show_default=True,
    type=int,
    help="Maximum number of hits to return.",
)
@click.pass_obj
def search_cmd(cfg: GlobalConfig, query: str, limit: int) -> None:
    """BM25 search over name + description + body of every memory asset.

    M2 implementation: pure-Python BM25 computed on-the-fly. M4's T-40
    Relevance Gate takes over with vector + temporal + enforcement weighting.
    """
    root = cfg.resolve_project_root()
    with open_graph_db(graph_db_path(root)) as conn:
        rows = conn.execute("SELECT id, path FROM assets WHERE kind = 'memory'").fetchall()

    documents: list[tuple[str, str]] = []
    meta: dict[str, tuple[str, str, str | None]] = {}
    for r in rows:
        path = memory_dir(root) / r["path"]
        if not path.exists():
            continue
        try:
            fm, body = parse_file(path)
        except FrontmatterError:
            continue
        corpus = f"{fm.name}\n{fm.description}\n{body}"
        documents.append((r["id"], corpus))
        meta[r["id"]] = (fm.scope.value, fm.enforcement.value, fm.subscribed_at)

    raw_ranked = bm25_scores(query, documents)
    raw_lookup = dict(raw_ranked)
    weighted = apply_scope_weighting(raw_ranked, meta)[:limit]

    if cfg.output_format == "json":
        payload = [
            {
                "id": did,
                "score": round(weighted_score, 4),
                "raw_score": round(raw_lookup.get(did, 0.0), 4),
                "scope": meta.get(did, ("project", "default", None))[0],
                "enforcement": meta.get(did, ("project", "default", None))[1],
            }
            for did, weighted_score in weighted
        ]
        click.echo(json.dumps(payload))
        return
    for did, weighted_score in weighted:
        scope, enforcement, _ = meta.get(did, ("project", "default", None))
        click.echo(f"{weighted_score:7.3f}  {did}  [{scope}/{enforcement}]")
