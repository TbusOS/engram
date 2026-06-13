"""Path resolution for KB articles (SPEC §6.1)."""

from __future__ import annotations

import re
from pathlib import Path

from engram.core.paths import memory_dir, user_root

__all__ = [
    "KB_COMPILED_NAME",
    "KB_COMPILE_STATE_NAME",
    "KB_README_NAME",
    "TOPIC_NAME_RE",
    "kb_dir",
    "kb_root",
    "validate_topic_name",
]

KB_README_NAME = "README.md"
KB_COMPILED_NAME = "_compiled.md"
KB_COMPILE_STATE_NAME = "_compile_state.toml"

# ``<topic>`` is joined into filesystem paths; a slug regex forbids
# traversal (``/``, ``.``, ``..``).
TOPIC_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")


class _InvalidTopicName(ValueError):
    """Raised when a KB topic name fails the slug check."""


def validate_topic_name(topic: str) -> str:
    if not isinstance(topic, str) or not TOPIC_NAME_RE.match(topic):
        raise _InvalidTopicName(
            f"invalid kb topic {topic!r}; must match {TOPIC_NAME_RE.pattern}"
        )
    return topic


def kb_root(project_root: Path, *, scope: str = "project") -> Path:
    """Return the ``kb/`` directory for ``scope`` (SPEC §6.1).

    Only ``project`` and ``user`` resolve unambiguously from a project
    root. ``team`` / ``org`` / ``pool`` need a specific scope *name*
    (``~/.engram/team/<name>/kb/`` etc.) that the CLI does not yet thread
    through, so they raise rather than silently mis-filing under the
    project store.
    """
    if scope == "project":
        return memory_dir(project_root) / "kb"
    if scope == "user":
        return user_root() / "user" / "kb"
    raise ValueError(
        f"kb scope {scope!r} needs a scope name and is not yet creatable via the "
        "CLI; create the article under the team/org/pool root directly, or use "
        "scope=project / scope=user"
    )


def kb_dir(project_root: Path, topic: str, *, scope: str = "project") -> Path:
    """Return ``<kb-root>/<topic>/`` for a validated topic."""
    return kb_root(project_root, scope=scope) / validate_topic_name(topic)
