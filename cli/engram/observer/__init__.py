"""``engram/observer/`` — automatic session continuation pipeline.

T-200 ~ T-212. Spec frozen 2026-04-26 in
``docs/superpowers/specs/2026-04-26-auto-continuation.md``.

This package is the engram answer to claude-mem's "automatic session
continuation": any LLM in any client can stream tool-use events through
``engram observe``; a single-instance daemon then runs a 4-tier compactor
pipeline (mechanical → local LLM → semantic distiller → procedural
recognizer) and produces Session assets that ride a brand-new Stage 0
of the Relevance Gate.

Layout follows DESIGN §4.2 — separate concerns from day one so adding
tiers / providers / decay rules later does not require splitting a
monolith:

- :mod:`engram.observer.paths` — queue / pid / raw / archive locations
- :mod:`engram.observer.protocol` — event schema + validation
- :mod:`engram.observer.queue` — append-only enqueue with fcntl.flock
- :mod:`engram.observer.cli` — ``engram observe`` click command

Tier 0/1/2/3 compactors and the daemon land in subsequent tasks
(T-201, T-202, T-204, T-208, T-210).
"""

from __future__ import annotations

from engram.observer.paths import (
    observe_queue_dir,
    queue_file_for_session,
    raw_session_file,
)
from engram.observer.protocol import (
    ALLOWED_EVENT_KINDS,
    ObserveEvent,
    ProtocolError,
    parse_event,
)
from engram.observer.queue import (
    QueueError,
    QueueFullError,
    enqueue,
    queue_depth,
)
from engram.observer.tier1 import (
    Tier1Result,
    compact_to_narrative,
    compact_to_session_asset,
)

__all__ = [
    "ALLOWED_EVENT_KINDS",
    "ObserveEvent",
    "ProtocolError",
    "QueueError",
    "QueueFullError",
    "Tier1Result",
    "compact_to_narrative",
    "compact_to_session_asset",
    "enqueue",
    "observe_queue_dir",
    "parse_event",
    "queue_depth",
    "queue_file_for_session",
    "raw_session_file",
]
