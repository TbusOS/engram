"""Repo ID resolution (SPEC §10.6)."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import tomli

__all__ = ["resolve_repo_id", "slugify_repo_id"]

# A repo id becomes a path segment under ~/.engram/inbox/<slug>/. It can
# arrive from a model-driven MCP tool argument, so the slug MUST NOT be a
# path-traversal token. Anything outside this allowlist collapses to '-'.
_SLUG_BAD_RE = re.compile(r"[^A-Za-z0-9._-]+")


def resolve_repo_id(project_root: Path) -> str:
    """Explicit config > git-remote hash > path hash (SPEC §10.6)."""
    # 1. Explicit .engram/config.toml [project] repo_id
    cfg = project_root / ".engram" / "config.toml"
    if cfg.is_file():
        try:
            data = tomli.loads(cfg.read_text(encoding="utf-8"))
        except tomli.TOMLDecodeError:
            data = {}
        explicit = data.get("project", {}).get("repo_id")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

    # 2. Git remote url hash (short)
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return hashlib.sha256(out.stdout.strip().encode()).hexdigest()[:12]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 3. Path hash fallback
    return hashlib.sha256(
        str(project_root.resolve()).encode()
    ).hexdigest()[:12]


def slugify_repo_id(repo_id: str) -> str:
    """Make a repo id safe to use as a single path segment (SPEC §10.1).

    Replaces ``/`` (and any other char outside ``[A-Za-z0-9._-]``, incl.
    NUL / newline / whitespace) with ``-``. A slug that reduces to empty
    or to a traversal token (``.`` / ``..``) is replaced with a stable
    hash so it can never escape ``~/.engram/inbox/`` (security review:
    ``to=".."`` previously wrote one level above the inbox tree).
    """
    slug = _SLUG_BAD_RE.sub("-", repo_id).strip("-")
    if slug in ("", ".", ".."):
        return "id-" + hashlib.sha256(repo_id.encode()).hexdigest()[:12]
    return slug
