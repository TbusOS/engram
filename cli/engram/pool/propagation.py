"""Pool propagation: auto-sync rev/current resolution + sync journal (SPEC §9.3 / §9.4)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from engram.core.journal import append_event
from engram.core.paths import user_root
from engram.pool.subscriptions import user_pool_path

__all__ = [
    "append_propagation_completed",
    "current_revision",
    "now_iso",
    "propagation_journal_path",
    "resolve_pool_target",
]


def propagation_journal_path() -> Path:
    """``~/.engram/journal/propagation.jsonl`` — the SPEC §9.4 append-only log."""
    return user_root() / "journal" / "propagation.jsonl"


def current_revision(pool_name: str) -> str | None:
    """Return the revision id that the pool's ``rev/current`` symlink points at.

    ``rev/current`` is a relative symlink to a sibling ``rev/<rN>`` directory
    per SPEC §9.1. Returns ``None`` if the pool has no rev tree yet.
    """
    current = user_pool_path(pool_name) / "rev" / "current"
    if not current.is_symlink():
        return None
    target = os.readlink(current)
    return Path(target).name


def resolve_pool_target(
    pool_name: str, mode: str, pinned_revision: str | None
) -> tuple[Path, str | None]:
    """Pick the concrete symlink target + initial ``last_synced_rev`` for a new subscription.

    - ``auto-sync`` / ``notify`` → ``rev/current`` (or pool root if no ``rev/``).
    - ``pinned`` → ``rev/<pinned_revision>/`` (must exist; raises otherwise).
    """
    pool_dir = user_pool_path(pool_name)
    if mode == "pinned":
        assert pinned_revision is not None
        rev_dir = pool_dir / "rev" / pinned_revision
        if not rev_dir.is_dir():
            raise click.ClickException(f"revision {pinned_revision!r} not found at {rev_dir}")
        return rev_dir, pinned_revision

    # auto-sync + notify share propagation target (notify journal-entry logic is T-95).
    current_link = pool_dir / "rev" / "current"
    if current_link.is_symlink():
        return current_link, current_revision(pool_name)
    return pool_dir, None


def now_iso() -> str:
    """RFC 3339 timestamp with ``Z`` suffix, matching SPEC §9.4 examples."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_propagation_completed(
    pool: str, subscriber: Path, from_rev: str | None, to_rev: str
) -> None:
    """Write a ``propagation_completed`` event to the propagation journal."""
    append_event(
        propagation_journal_path(),
        {
            "timestamp": now_iso(),
            "event": "propagation_completed",
            "pool": pool,
            "subscriber": str(subscriber),
            "from_rev": from_rev,
            "to_rev": to_rev,
        },
    )


def sync_subscriptions(
    subs: dict[str, dict[str, Any]], subscriber: Path, names: list[str]
) -> list[dict[str, Any]]:
    """Apply one sync pass to the named subscriptions. Mutates ``subs`` in place.

    Pinned subscriptions are skipped. Auto-sync / notify subscriptions whose
    pool has advanced get ``last_synced_rev`` bumped and a
    ``propagation_completed`` journal entry written.
    """
    results: list[dict[str, Any]] = []
    for name in names:
        entry = subs.get(name)
        if entry is None:
            continue
        mode = entry.get("propagation_mode", "auto-sync")
        if mode == "pinned":
            continue
        latest = current_revision(name)
        if latest is None:
            continue
        from_rev = entry.get("last_synced_rev")
        if from_rev == latest:
            results.append({"pool": name, "from_rev": from_rev, "to_rev": latest, "changed": False})
            continue
        entry["last_synced_rev"] = latest
        append_propagation_completed(name, subscriber, from_rev, latest)
        results.append({"pool": name, "from_rev": from_rev, "to_rev": latest, "changed": True})
    return results
