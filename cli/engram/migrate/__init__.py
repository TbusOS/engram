"""``engram migrate`` — cross-version and cross-tool store migration (SPEC §13).

Each migration source lives in its own submodule:

- :mod:`v0_1` — the v0.1 → v0.2 upgrade contract (SPEC §13.4).
- Future: ``chatgpt``, ``mem0``, ``obsidian``, ``letta``, ``mempalace``,
  ``markdown`` (SPEC §13.6 / TASKS T-140). Each added as a separate file,
  same dispatcher in :mod:`commands`.

The click group + dispatch lives in :mod:`commands` so ``from`` value parsing
and safety gates (backup path, preconditions) stay in one place.
"""

from engram.migrate.commands import migrate_cmd

__all__ = ["migrate_cmd"]
