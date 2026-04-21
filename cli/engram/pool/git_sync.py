"""Pool-side git sync: wraps :mod:`engram.core.git` + pool-directory walkers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engram.core.git import pull_ff
from engram.core.paths import user_root
from engram.pool.subscriptions import user_pool_path

__all__ = ["list_git_pools", "pool_has_git", "pull_pool"]


def pull_pool(pool_dir: Path) -> dict[str, Any]:
    """``git pull --ff-only`` inside a pool directory.

    Returns ``{pool, before, after, changed, added, modified, removed}``.
    The ``name`` key from :func:`engram.core.git.pull_ff` is renamed to
    ``pool`` here because downstream JSON serialisers key off ``pool``.
    """
    entry = pull_ff(pool_dir)
    entry["pool"] = entry.pop("name")
    return entry


def list_git_pools() -> list[str]:
    """Return the sorted names of every ``~/.engram/pools/<x>/`` that has ``.git/``."""
    root = user_root() / "pools"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / ".git").is_dir())


def pool_has_git(pool_name: str) -> bool:
    return (user_pool_path(pool_name) / ".git").is_dir()
