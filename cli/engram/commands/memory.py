"""``engram memory`` — CRUD + BM25 search over project-scope memories.

M2 scope covers what an operator needs to start using engram in a single
project: add a memory from flags, list / read / update / archive existing
ones, and search them with a pure-Python BM25 implementation. Other scopes
(org / team / user / pool) and the full Relevance Gate (DESIGN §5.1) arrive
in M3 and M4 respectively; this module intentionally stays narrow.

**M2 deviation from DESIGN §3.2**: graph.db lives at
``<project>/.engram/graph.db`` instead of ``~/.engram/graph.db``. The
cross-project query story requires a schema gap fix
(``(project_path, path)`` uniqueness) that belongs to M3. See the project
memory ``project_graph_db_location_m2_vs_design`` for the follow-up plan.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

import click
import yaml

from engram.cli import GlobalConfig
from engram.core.frontmatter import (
    Enforcement,
    FrontmatterError,
    MemoryFrontmatter,
    MemoryType,
    Scope,
    parse_file,
)
from engram.core.fs import write_atomic
from engram.core.graph_db import (
    AssetRow,
    get_asset,
    insert_asset,
    open_graph_db,
)
from engram.core.paths import engram_dir, memory_dir, user_root
from engram.relevance.bm25 import bm25_scores as _bm25_scores
from engram.relevance.weights import (
    ENFORCEMENT_WEIGHTS,
    SCOPE_WEIGHTS,
    apply_scope_weighting,
)

__all__ = [
    "ENFORCEMENT_WEIGHTS",
    "SCOPE_WEIGHTS",
    "apply_scope_weighting",
    "bm25_scores",
    "compute_id",
    "graph_db_path",
    "memory_file_path",
    "memory_group",
    "render_asset_file",
    "sha256_hex",
    "slugify",
]


# Scope + enforcement weighting — canonical implementation lives in
# engram.relevance.weights so the Relevance Gate (T-40) can import it
# without triggering click's command registration chain. Re-exported
# here (via the import block above) for backward compatibility with
# existing tests and callers.


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lower-case and replace non-alphanumeric runs with single underscores."""
    slug = _SLUG_RE.sub("_", text.lower()).strip("_")
    return slug or "untitled"


def compute_id(scope_dir: str, subtype: str, slug: str) -> str:
    """SPEC §4.1 asset id: ``<scope_dir>/<subtype>_<slug>`` (no extension)."""
    return f"{scope_dir}/{subtype}_{slug}"


def memory_file_path(project_root: Path, scope_dir: str, subtype: str, slug: str) -> Path:
    return memory_dir(project_root) / scope_dir / f"{subtype}_{slug}.md"


def graph_db_path(project_root: Path) -> Path:
    """Location of the SQLite graph index for this project (M2 choice)."""
    return engram_dir(project_root) / "graph.db"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_asset_file(fm: MemoryFrontmatter, body: str) -> str:
    """Serialize a MemoryFrontmatter + body to a SPEC-compliant .md file."""
    data = _frontmatter_to_dict(fm)
    yaml_block = yaml.dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    body_tail = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{body_tail}"


def _frontmatter_to_dict(fm: MemoryFrontmatter) -> dict[str, Any]:
    """Ordered dict suitable for YAML dump. Omits None / empty optional fields."""
    data: dict[str, Any] = {
        "name": fm.name,
        "description": fm.description,
        "type": fm.type.value,
        "scope": fm.scope.value,
        "enforcement": fm.enforcement.value,
    }
    for field_name, field_value in (
        ("org", fm.org),
        ("team", fm.team),
        ("pool", fm.pool),
        ("subscribed_at", fm.subscribed_at.value if fm.subscribed_at else None),
    ):
        if field_value:
            data[field_name] = field_value

    _maybe_date(data, "created", fm.created)
    _maybe_date(data, "updated", fm.updated)
    if fm.tags:
        data["tags"] = list(fm.tags)
    _maybe_date(data, "expires", fm.expires)
    _maybe_date(data, "valid_from", fm.valid_from)
    _maybe_date(data, "valid_to", fm.valid_to)
    if fm.source:
        data["source"] = fm.source
    if fm.references:
        data["references"] = list(fm.references)
    if fm.overrides:
        data["overrides"] = fm.overrides
    if fm.supersedes:
        data["supersedes"] = fm.supersedes
    if fm.limitations:
        data["limitations"] = list(fm.limitations)
    if fm.confidence:
        data["confidence"] = {
            "validated_count": fm.confidence.validated_count,
            "contradicted_count": fm.confidence.contradicted_count,
            "last_validated": fm.confidence.last_validated.isoformat(),
            "usage_count": fm.confidence.usage_count,
        }
    if fm.workflow_ref:
        data["workflow_ref"] = fm.workflow_ref

    # Unknown fields preserved last (SPEC §4.1).
    for k, v in fm.extra.items():
        if k not in data:
            data[k] = v

    return data


def _maybe_date(data: dict[str, Any], key: str, value: date | None) -> None:
    if value is not None:
        data[key] = value.isoformat()


def _read_body_flag(raw: str) -> str:
    """Resolve --body; ``-`` reads from stdin."""
    if raw == "-":
        return sys.stdin.read()
    return raw


def _build_frontmatter(
    *,
    memory_type: str,
    name: str,
    description: str,
    scope: str,
    enforcement: str | None,
    tags: tuple[str, ...],
    source: str | None,
    workflow_ref: str | None,
) -> MemoryFrontmatter:
    """Construct + validate a MemoryFrontmatter from CLI flags."""
    # Defer enforcement default to the frontmatter validator so feedback gets
    # its required-field check.
    raw: dict[str, Any] = {
        "name": name,
        "description": description,
        "type": memory_type,
        "scope": scope,
        "tags": list(tags),
    }
    if enforcement is not None:
        raw["enforcement"] = enforcement
    if source is not None:
        raw["source"] = source
    if workflow_ref is not None:
        raw["workflow_ref"] = workflow_ref
    raw["created"] = date.today().isoformat()

    # Round-trip through YAML → parse_frontmatter so all SPEC §4.1 validation
    # fires uniformly instead of us re-implementing it here.
    yaml_block = yaml.dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    doc = f"---\n{yaml_block}---\n"
    try:
        return _from_yaml_doc(doc)
    except FrontmatterError as exc:
        raise click.ClickException(str(exc)) from exc


def _from_yaml_doc(doc: str) -> MemoryFrontmatter:
    from engram.core.frontmatter import parse_frontmatter

    return parse_frontmatter(doc)


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

    fm = _build_frontmatter(
        memory_type=memory_type,
        name=name,
        description=description,
        scope=scope,
        enforcement=enforcement,
        tags=tags,
        source=source,
        workflow_ref=workflow_ref,
    )
    slug = slugify(name)
    scope_dir = "local"  # M2: everything under local/; M3 extends
    file_path = memory_file_path(root, scope_dir, memory_type, slug)
    if file_path.exists() and not force:
        raise click.ClickException(f"{file_path} already exists; re-run with --force to overwrite.")

    body_text = _read_body_flag(body)
    content = render_asset_file(fm, body_text)
    write_atomic(file_path, content)

    asset_id = compute_id(scope_dir, memory_type, slug)
    rel_path = file_path.relative_to(memory_dir(root))
    row = AssetRow(
        id=asset_id,
        scope=scope,
        scope_name=None,
        subtype=memory_type,
        kind="memory",
        path=str(rel_path),
        lifecycle_state="active",
        sha256=sha256_hex(content),
        created=fm.created.isoformat() if fm.created else None,
        updated=fm.updated.isoformat() if fm.updated else None,
        enforcement=fm.enforcement.value,
        confidence_score=0.0,
        size_bytes=len(content.encode("utf-8")),
    )
    with open_graph_db(graph_db_path(root)) as conn:
        if force:
            conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            conn.commit()
        insert_asset(conn, row)

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "id": asset_id,
                    "path": str(file_path),
                    "sha256": row.sha256,
                    "size_bytes": row.size_bytes,
                }
            )
        )
    else:
        click.echo(f"added {asset_id} → {file_path}")


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
                    "frontmatter": _frontmatter_to_dict(fm),
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
