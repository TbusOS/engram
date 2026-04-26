"""Daemon runner factories — bind Tier 0 / Tier 1 to ObserverDaemon.

The :class:`engram.observer.daemon.ObserverDaemon` accepts arbitrary
``tier0_runner`` / ``tier1_runner`` callables so it can be unit-tested
without LLMs or filesystem state. This module provides the production
wiring: factories that pin a ``timelines_dir``, a ``project_root``,
and a provider loader, then return runners ready to drop into the
daemon constructor.

Layout invariants this module owns:

- Per-session timelines live at ``<timelines_dir>/<session-id>.timeline.jsonl``.
  Default ``timelines_dir = ~/.engram/timelines/``. Tier 0 appends here.
- Session asset files (Tier 1 output) live at
  ``<project_root>/.memory/sessions/<YYYY-MM-DD>/sess_<id>.md`` if the
  daemon was invoked with a project root, or
  ``~/.engram/sessions/<YYYY-MM-DD>/sess_<id>.md`` otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from engram.core.paths import user_root
from engram.observer.config import load_tier_provider
from engram.observer.daemon import PendingSession
from engram.observer.providers import Provider, mechanical_provider
from engram.observer.tier0 import compact_session
from engram.observer.tier1 import compact_to_session_asset

__all__ = [
    "DEFAULT_TIMELINES_SUBDIR",
    "make_tier0_runner",
    "make_tier1_runner",
    "read_client_from_timeline",
    "timelines_dir",
]


DEFAULT_TIMELINES_SUBDIR = "timelines"


def timelines_dir(*, base: Path | None = None) -> Path:
    """Return the working directory where Tier 0 writes timeline jsonls."""
    root = base if base is not None else user_root()
    return root / DEFAULT_TIMELINES_SUBDIR


def read_client_from_timeline(timeline_path: Path) -> str | None:
    """Best-effort: read the ``client`` field from the first valid line.

    Returns ``None`` when the file is missing / empty / malformed; the
    caller should default to ``"manual"`` so Session asset frontmatter
    is always valid.
    """
    if not timeline_path.exists():
        return None
    with open(timeline_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            client = rec.get("client")
            if isinstance(client, str) and client:
                return client
    return None


def make_tier0_runner(
    *,
    base: Path | None = None,
) -> Callable[[PendingSession], None]:
    """Return a runner that appends Tier 0 facts for the pending session."""
    sessions_dir = timelines_dir(base=base)

    def _run(pending: PendingSession) -> None:
        compact_session(
            pending.session_id,
            queue_path=pending.queue_path,
            sessions_dir=sessions_dir,
        )

    return _run


def make_tier1_runner(
    *,
    base: Path | None = None,
    project_root: Path | None = None,
    provider: Provider | None = None,
    provider_loader: Callable[[], Provider] | None = None,
    config_path: Path | None = None,
) -> Callable[[PendingSession], None]:
    """Return a runner that produces Session assets via Tier 1.

    Provider resolution priority:

    1. Explicit ``provider`` argument (tests inject a fake here).
    2. Explicit ``provider_loader`` callable (lazy build).
    3. ``load_tier_provider(1, config_path=config_path)`` — reads
       ``~/.engram/config.toml`` and constructs the configured provider,
       falling back to mechanical if no config is present.

    The runner never lets a provider exception kill the daemon — Tier 1
    catches :class:`engram.observer.providers.ProviderError` internally
    and falls back to the Tier 0 mechanical narrative.
    """
    tdir = timelines_dir(base=base)

    def _resolve_provider() -> Provider:
        if provider is not None:
            return provider
        if provider_loader is not None:
            try:
                return provider_loader()
            except Exception:
                return mechanical_provider
        try:
            return load_tier_provider(1, config_path=config_path)
        except Exception:
            return mechanical_provider

    def _run(pending: PendingSession) -> None:
        timeline_path = tdir / f"{pending.session_id}.timeline.jsonl"
        client = read_client_from_timeline(timeline_path) or "manual"
        compact_to_session_asset(
            pending.session_id,
            timeline_path=timeline_path,
            client=client,
            project_root=project_root,
            provider=_resolve_provider(),
        )

    return _run
