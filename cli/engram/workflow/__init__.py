"""Workflow asset class — executable procedures (SPEC §5).

The second of engram's three asset classes (Memory / Workflow / KB). A
Workflow is a directory under ``<scope-root>/workflows/<name>/`` holding
a human-readable ``workflow.md``, a runnable ``spine.*`` (python3 / bash
/ toml), validation ``fixtures/``, a ``metrics.yaml`` outcome tracker,
copy-on-write ``rev/`` history, and append-only ``journal/`` logs.

This package implements the on-disk format contract and the runtime
(scaffold / validate / run / test / history / rollback). The Autolearn
Engine that evolves a spine round-by-round (DESIGN §5.3) is a separate
subsystem; this package provides the data contracts it builds on.
"""

from __future__ import annotations

from engram.workflow.fixtures import (
    AssertionResult,
    FixtureResult,
    run_fixtures,
)
from engram.workflow.format import (
    FixtureCase,
    MetricsConfig,
    MetricSpec,
    WorkflowFormatError,
    WorkflowFrontmatter,
    parse_fixture,
    parse_metrics,
    parse_workflow_file,
    render_workflow_file,
)
from engram.workflow.paths import (
    WORKFLOW_DOC_NAME,
    workflow_dir,
    workflows_root,
)
from engram.workflow.rev import (
    WorkflowRevError,
    list_revisions,
    rollback_to,
    scaffold_workflow,
)
from engram.workflow.runner import (
    SpineError,
    SpineOutcome,
    run_spine,
)

__all__ = [
    "WORKFLOW_DOC_NAME",
    "AssertionResult",
    "FixtureCase",
    "FixtureResult",
    "MetricSpec",
    "MetricsConfig",
    "SpineError",
    "SpineOutcome",
    "WorkflowFormatError",
    "WorkflowFrontmatter",
    "WorkflowRevError",
    "list_revisions",
    "parse_fixture",
    "parse_metrics",
    "parse_workflow_file",
    "render_workflow_file",
    "rollback_to",
    "run_fixtures",
    "run_spine",
    "scaffold_workflow",
    "workflow_dir",
    "workflows_root",
]
