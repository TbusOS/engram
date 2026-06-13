"""Path resolution for Workflow assets (SPEC §5.1).

A Workflow lives at ``<scope-root>/workflows/<name>/``. For the common
project scope that is ``<project>/.memory/workflows/<name>/``. Other
scopes resolve under the user-global tree; the resolver mirrors the
table in SPEC §5.1.
"""

from __future__ import annotations

import re
from pathlib import Path

from engram.core.paths import memory_dir, user_root

__all__ = [
    "WORKFLOW_DOC_NAME",
    "WORKFLOW_NAME_RE",
    "validate_workflow_name",
    "workflow_dir",
    "workflows_root",
]

WORKFLOW_DOC_NAME = "workflow.md"

# Security: ``<name>`` arrives from the CLI / LLM hooks and is joined into
# filesystem paths. A slug regex forbids traversal (``/``, ``.``, ``..``).
WORKFLOW_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")


class _InvalidWorkflowName(ValueError):
    """Raised when a workflow name fails the slug check."""


def validate_workflow_name(name: str) -> str:
    """Return ``name`` unchanged if it is a safe slug, else raise."""
    if not isinstance(name, str) or not WORKFLOW_NAME_RE.match(name):
        raise _InvalidWorkflowName(
            f"invalid workflow name {name!r}; must match {WORKFLOW_NAME_RE.pattern}"
        )
    return name


def workflows_root(project_root: Path, *, scope: str = "project") -> Path:
    """Return the ``workflows/`` directory for ``scope`` (SPEC §5.1).

    Only ``project`` and ``user`` resolve unambiguously from a project
    root. ``team`` / ``org`` / ``pool`` need a specific scope *name*
    (``~/.engram/team/<name>/workflows/`` etc.) that the CLI does not yet
    thread through, so they raise rather than silently mis-filing the
    workflow under the project store.
    """
    if scope == "project":
        return memory_dir(project_root) / "workflows"
    if scope == "user":
        return user_root() / "user" / "workflows"
    raise ValueError(
        f"workflow scope {scope!r} needs a scope name and is not yet creatable via "
        "the CLI; create it under the team/org/pool root directly, or use "
        "scope=project / scope=user"
    )


def workflow_dir(project_root: Path, name: str, *, scope: str = "project") -> Path:
    """Return ``<workflows-root>/<name>/`` for a validated ``name``."""
    return workflows_root(project_root, scope=scope) / validate_workflow_name(name)
