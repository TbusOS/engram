"""Project root + user-global directory resolution.

SPEC §3.1 fixes the on-disk layout:

- `<project>/.memory/` is the project-scope store root — walking upward from any
  working directory inside a project until a `.memory/` sibling appears is the
  canonical way to locate the root.
- `~/.engram/` is the user-global store (user assets, pool symlinks, inbox).
- `<project>/.engram/` is the project-local control dir (`version`, `topics.toml`).

The `ENGRAM_DIR` environment variable short-circuits the upward walk when set,
per DESIGN §9.3 config resolution order: CLI flags > env vars > config file >
defaults. At this layer we read only the env var; CLI-flag overrides are layered
on top in the dispatcher (T-16).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "ENV_VAR",
    "MEMORY_MARKER",
    "ProjectNotFoundError",
    "engram_dir",
    "find_project_root",
    "memory_dir",
    "user_root",
]

MEMORY_MARKER = ".memory"
ENV_VAR = "ENGRAM_DIR"


class ProjectNotFoundError(FileNotFoundError):
    """No engram project root was found walking upward from the given directory."""


def find_project_root(start: Path | str | None = None) -> Path:
    """Return the nearest engram project root, resolved to an absolute path.

    Resolution order:

    1. If ``ENGRAM_DIR`` is set, return it verbatim (expanduser + resolve). No
       existence check — ``engram init`` creates the directory when the user
       targets a new location.
    2. Otherwise walk upward from ``start`` (cwd when ``None``) and return the
       first ancestor containing a ``.memory/`` directory.
    3. If the walk hits the filesystem root with no match, raise
       :class:`ProjectNotFoundError`.
    """
    env_override = os.environ.get(ENV_VAR)
    if env_override:
        return Path(env_override).expanduser().resolve()

    base = Path(start).expanduser().resolve() if start is not None else Path.cwd().resolve()
    for candidate in (base, *base.parents):
        if (candidate / MEMORY_MARKER).is_dir():
            return candidate

    raise ProjectNotFoundError(
        f"no engram project root found walking up from {base}: no "
        f"{MEMORY_MARKER}/ directory and ENGRAM_DIR is not set"
    )


def user_root() -> Path:
    """Return the user-global engram directory (``~/.engram/``).

    Fixed per SPEC §3.1 — cross-tool portability depends on this location
    being predictable, so there is intentionally no env var override here.
    """
    return Path.home() / ".engram"


def memory_dir(project_root: Path) -> Path:
    """Return ``<project_root>/.memory/`` — the project-scope asset store."""
    return project_root / MEMORY_MARKER


def engram_dir(project_root: Path) -> Path:
    """Return ``<project_root>/.engram/`` — the project-local control directory.

    This holds the version file (SPEC §13.4) and optional ``topics.toml``
    (SPEC §7.6 manual topic assignments).
    """
    return project_root / ".engram"
