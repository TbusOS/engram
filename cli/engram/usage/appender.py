"""Single sanctioned writer for ``~/.engram/journal/usage.jsonl``.

Wraps ``engram.core.journal.append_event`` so consumers stay typed and
the file format stays uniform. The per-line schema is the
``UsageEvent.to_dict()`` shape.
"""

from __future__ import annotations

from engram.core.journal import append_event
from engram.usage.types import UsageEvent, usage_jsonl_path


def append_usage_event(event: UsageEvent) -> None:
    append_event(usage_jsonl_path(), event.to_dict())
