"""Filtered reader for the usage event bus.

Filters compose AND-style: passing both ``asset_uri`` and ``evidence_kind``
yields only events matching both. Time-window and actor filters land in a
follow-up patch (Wisdom Metrics aggregation, T-188).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from engram.core.journal import read_events
from engram.usage.types import (
    ActorType,
    EventType,
    EvidenceKind,
    UsageEvent,
    usage_jsonl_path,
)


def iter_events(
    *,
    asset_uri: str | None = None,
    task_hash: str | None = None,
    event_type: EventType | None = None,
    actor_type: ActorType | None = None,
    evidence_kind: EvidenceKind | None = None,
) -> Iterator[UsageEvent]:
    """Yield :class:`UsageEvent` rows from ``~/.engram/journal/usage.jsonl``
    filtered by any combination of the keyword arguments."""
    raw = read_events(usage_jsonl_path())
    for entry in raw:
        if asset_uri is not None and entry.get("asset_uri") != asset_uri:
            continue
        if task_hash is not None and entry.get("task_hash") != task_hash:
            continue
        if event_type is not None and entry.get("event_type") != event_type.value:
            continue
        if actor_type is not None and entry.get("actor_type") != actor_type.value:
            continue
        if (
            evidence_kind is not None
            and entry.get("evidence_kind") != evidence_kind.value
        ):
            continue
        yield UsageEvent.from_dict(entry)


def all_assets_with_events() -> Iterable[str]:
    """Return the set of distinct ``asset_uri`` values seen in the journal.
    Useful for batch confidence recompute jobs."""
    return {ev.asset_uri for ev in iter_events()}
