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
    """Return the ``workflows/`` directory for ``scope``.

    SPEC §5.1 scope-root table:

    - ``project`` -> ``<project>/.memory/workflows/``
    - ``user``    -> ``~/.engram/user/workflows/``
    - ``team``/``org``/``pool`` -> ``~/.engram/<kind>/<name>/workflows/``
      cannot be resolved from name alone, so for those the caller passes
      the already-resolved scope root via ``project_root`` and
      ``scope='project'`` semantics. We keep the common cases first-class
      and fall back to project-local for anything else.
    """
    if scope == "user":
        return user_root() / "user" / "workflows"
    return memory_dir(project_root) / "workflows"


def workflow_dir(project_root: Path, name: str, *, scope: str = "project") -> Path:
    """Return ``<workflows-root>/<name>/`` for a validated ``name``."""
    return workflows_root(project_root, scope=scope) / validate_workflow_name(name)
