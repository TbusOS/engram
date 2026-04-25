"""``engram/usage/`` — append-only event bus that feeds confidence and
the 6 wisdom curves (T-170, master plan
``docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md`` Week 2).

Public surface is intentionally small:

- types: ``UsageEvent`` / ``EventType`` / ``ActorType`` / ``EvidenceKind``
- writer: ``append_usage_event(event)``
- reader: ``iter_events(filters)``
- derived cache: ``derive_confidence_cache(asset_uri) -> ConfidenceCache``
- trust weight table: ``trust_weights.DEFAULT_TRUST_WEIGHTS``

Layout follows DESIGN §4.2: each concern lives in its own file from the
start so adding evidence kinds, filters, or derived caches later does not
require splitting a single file.
"""

from __future__ import annotations

from engram.usage.appender import append_usage_event
from engram.usage.reader import iter_events
from engram.usage.recompute import ConfidenceCache, derive_confidence_cache
from engram.usage.task_hash import derive_task_hash
from engram.usage.types import (
    ActorType,
    EventType,
    EvidenceKind,
    UsageEvent,
    usage_jsonl_path,
)

__all__ = [
    "ActorType",
    "ConfidenceCache",
    "EventType",
    "EvidenceKind",
    "UsageEvent",
    "append_usage_event",
    "derive_confidence_cache",
    "derive_task_hash",
    "iter_events",
    "usage_jsonl_path",
]
