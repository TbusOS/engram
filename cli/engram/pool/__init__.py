"""engram ``pool`` module — SPEC §8 / §9 subscriptions, propagation, git sync.

Split into submodules per DESIGN §4.2 file layout:

- :mod:`subscriptions` — ``pools.toml`` read/write + subscription symlink helpers.
- :mod:`propagation` — auto-sync ``rev/current`` resolution, ``last_synced_rev``
  bookkeeping, and the ``engram pool sync`` command logic.
- :mod:`git_sync` — ``git pull --ff-only`` via subprocess + diff name-status counts.
- :mod:`commands` — the click root group and subcommand bindings.

Every subcommand registers under the ``pool`` click group in ``commands.py``.
The public CLI surface is exposed only through ``commands.pool_group``; other
modules export pure-Python helpers that tests (and future callers like the
validator) can import directly.
"""

from engram.pool.commands import pool_group
from engram.pool.propagation import (
    current_revision,
    propagation_journal_path,
)
from engram.pool.subscriptions import (
    pools_toml_path,
    read_subscriptions,
    user_pool_path,
)

__all__ = [
    "current_revision",
    "pool_group",
    "pools_toml_path",
    "propagation_journal_path",
    "read_subscriptions",
    "user_pool_path",
]
