"""Memory asset domain logic.

Id / path helpers (:mod:`~engram.memory.ident`), serialization
(:mod:`~engram.memory.render`), the MEMORY.md landing index
(:mod:`~engram.memory.index_md`), quick-derivation
(:mod:`~engram.memory.derive`), and the shared write path
(:mod:`~engram.memory.write`).

The ``engram memory`` click command group lives in
:mod:`engram.commands.memory`; this package holds the click-free logic so any
caller — the CLI command layer, the MCP server, doctor, the web UI — can
import it without triggering command registration.
"""

from __future__ import annotations

from engram.memory.derive import derive_quick_description, derive_quick_name
from engram.memory.ident import (
    compute_id,
    graph_db_path,
    memory_file_path,
    sha256_hex,
    slugify,
)
from engram.memory.index_md import append_to_memory_index, remove_from_memory_index
from engram.memory.render import frontmatter_to_dict, render_asset_file
from engram.memory.write import (
    MemoryWriteError,
    create_memory,
    resolve_quick_slug,
)

__all__ = [
    "MemoryWriteError",
    "append_to_memory_index",
    "compute_id",
    "create_memory",
    "derive_quick_description",
    "derive_quick_name",
    "frontmatter_to_dict",
    "graph_db_path",
    "memory_file_path",
    "remove_from_memory_index",
    "render_asset_file",
    "resolve_quick_slug",
    "sha256_hex",
    "slugify",
]
