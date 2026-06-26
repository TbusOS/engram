"""The shared memory write path.

:func:`create_memory` is the single write path used by ``engram memory add`` /
``quick`` and the MCP ``engram_memory_add`` tool — file write + graph.db
register + MEMORY.md index update happen in exactly one place. ``body`` must
already be resolved (no ``-`` stdin sentinel); resolving that flag is a
CLI concern and stays in the command layer.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from engram.core.frontmatter import FrontmatterError, MemoryFrontmatter
from engram.core.fs import write_atomic
from engram.core.graph_db import AssetRow, insert_asset, open_graph_db
from engram.core.paths import memory_dir
from engram.memory.ident import (
    compute_id,
    graph_db_path,
    memory_file_path,
    sha256_hex,
    slugify,
)
from engram.memory.index_md import append_to_memory_index
from engram.memory.render import render_asset_file


class MemoryWriteError(Exception):
    """Raised by :func:`create_memory` on validation failure or id collision.

    Non-click so non-CLI callers (the MCP server) can handle it; the CLI
    converts it to a ``click.ClickException`` at the command boundary.
    """


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
    # fires uniformly instead of us re-implementing it here. Raises
    # FrontmatterError on invalid input; callers (create_memory) wrap it.
    yaml_block = yaml.dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    doc = f"---\n{yaml_block}---\n"
    return _from_yaml_doc(doc)


def create_memory(
    root: Path,
    *,
    memory_type: str,
    name: str,
    description: str,
    body: str,
    scope: str = "project",
    enforcement: str | None = None,
    tags: tuple[str, ...] = (),
    source: str | None = None,
    workflow_ref: str | None = None,
    force: bool = False,
    slug: str | None = None,
) -> dict[str, Any]:
    """Create a memory asset: write file + register in graph.db + index.

    The single write path shared by ``engram memory add`` / ``quick`` and
    the MCP ``engram_memory_add`` tool. ``body`` must already be resolved
    (no ``-`` stdin sentinel). Pass ``slug`` to override the name-derived
    slug (the quick path pre-resolves a collision-free slug). Raises
    :class:`MemoryWriteError` on validation failure or an id collision
    when ``force`` is False. Returns ``{id, path, sha256, size_bytes, name}``.
    """
    try:
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
    except FrontmatterError as exc:
        raise MemoryWriteError(str(exc)) from exc

    final_slug = slug or slugify(name)
    scope_dir = "local"  # M2: everything under local/; M3 extends
    file_path = memory_file_path(root, scope_dir, memory_type, final_slug)
    if file_path.exists() and not force:
        raise MemoryWriteError(
            f"{file_path} already exists; use force=True to overwrite."
        )

    content = render_asset_file(fm, body)
    write_atomic(file_path, content)

    asset_id = compute_id(scope_dir, memory_type, final_slug)
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

    append_to_memory_index(root, rel_path=str(rel_path), name=name, description=description)
    return {
        "id": asset_id,
        "path": str(file_path),
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "name": name,
    }


def _from_yaml_doc(doc: str) -> MemoryFrontmatter:
    from engram.core.frontmatter import parse_frontmatter

    return parse_frontmatter(doc)


def resolve_quick_slug(
    project_root: Path,
    scope_dir: str,
    subtype: str,
    base_slug: str,
    base_name: str,
) -> tuple[str, str]:
    """Return a non-colliding (slug, display_name). Appends ``_2``, ``_3``, ..."""
    candidate = base_slug
    suffix = 2
    while memory_file_path(project_root, scope_dir, subtype, candidate).exists():
        candidate = f"{base_slug}_{suffix}"
        suffix += 1
    if candidate == base_slug:
        return candidate, base_name
    # Reflect the disambiguation in the display name so MEMORY.md / list output
    # is not surprising.
    return candidate, f"{base_name} ({suffix - 1})"
