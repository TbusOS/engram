"""Git operations for team + org scopes (SPEC §8.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from engram.core.git import (
    clone,
    commit_all,
    pull_ff,
    push,
    status_porcelain,
)
from engram.core.paths import user_root

__all__ = [
    "join_scope",
    "list_scopes",
    "publish_scope",
    "scope_root",
    "scopes_root",
    "status_scope",
    "sync_scope",
]


def scopes_root(kind: str) -> Path:
    """Return ``~/.engram/<kind>/`` — the parent of every joined scope of that kind."""
    return user_root() / kind


def scope_root(kind: str, name: str) -> Path:
    """Return ``~/.engram/<kind>/<name>/`` — the specific scope directory."""
    return scopes_root(kind) / name


def list_scopes(kind: str) -> list[str]:
    """Return the sorted names of every joined scope of ``kind`` that has ``.git/``."""
    root = scopes_root(kind)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / ".git").is_dir())


def join_scope(kind: str, name: str, url: str) -> Path:
    """Clone ``url`` into ``~/.engram/<kind>/<name>/``. Fails if already joined."""
    dest = scope_root(kind, name)
    if dest.exists():
        raise click.ClickException(f"{kind} {name!r} already joined at {dest}")
    clone(dest, url)
    return dest


def sync_scope(kind: str, name: str) -> dict[str, Any]:
    """``git pull --ff-only`` on the scope. Returns the core.git ``pull_ff`` dict."""
    dest = scope_root(kind, name)
    if not dest.is_dir():
        raise click.ClickException(f"{kind} {name!r} is not joined; run `engram {kind} join` first")
    if not (dest / ".git").is_dir():
        raise click.ClickException(f"{kind} {name!r} at {dest} is not a git repository")
    return pull_ff(dest)


def publish_scope(kind: str, name: str, message: str) -> dict[str, Any]:
    """``git add -A`` + ``git commit -m <msg>`` + ``git push`` for the scope.

    Returns ``{name, pushed, from_rev, to_rev}`` where ``pushed=False`` means
    the working tree was clean so no commit was created.
    """
    dest = scope_root(kind, name)
    if not dest.is_dir():
        raise click.ClickException(f"{kind} {name!r} is not joined")
    if not (dest / ".git").is_dir():
        raise click.ClickException(f"{kind} {name!r} is not a git repository")

    from engram.core.git import head_sha

    before = head_sha(dest)
    after = commit_all(dest, message)
    if after is None:
        return {"name": name, "pushed": False, "from_rev": before, "to_rev": before}
    push(dest)
    return {"name": name, "pushed": True, "from_rev": before, "to_rev": after}


def status_scope(kind: str, name: str) -> dict[str, Any]:
    """Return ``{name, clean, changes}`` for the scope repo."""
    dest = scope_root(kind, name)
    if not dest.is_dir():
        raise click.ClickException(f"{kind} {name!r} is not joined")
    if not (dest / ".git").is_dir():
        raise click.ClickException(f"{kind} {name!r} is not a git repository")
    changes = status_porcelain(dest)
    return {"name": name, "clean": not changes, "changes": changes}
