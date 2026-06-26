"""Asset id, file-path, and content-hash helpers for memory assets.

Pure functions with no click / no graph.db dependency, so any caller (the
CLI command layer, the MCP server, doctor, the web UI) can import them
without dragging in the command-registration chain.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from engram.core.paths import engram_dir, memory_dir

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
