"""Repo ID resolution (SPEC §10.6)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import tomli

__all__ = ["resolve_repo_id", "slugify_repo_id"]


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
    """SPEC §10.1: sender-id slug replaces ``/`` with ``-``."""
    return repo_id.replace("/", "-")
