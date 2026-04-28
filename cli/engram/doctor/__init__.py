"""``engram doctor`` — store health check + executable repair hints.

Module layout follows DESIGN §4.2: each check category lives in its own
file, the ``__init__`` only wires them together. doctor is intentionally
distinct from ``validate`` (SPEC §12 contract enforcement) and ``review``
(SPEC §16 percentile signals): doctor answers **"what is wrong with my
store right now, and what command fixes it?"** with every issue carrying
an ``fix_command`` field.
"""

from __future__ import annotations

from pathlib import Path

from engram.doctor.checks_graph_db import check_graph_db_drift
from engram.doctor.checks_index import check_index_reachability
from engram.doctor.checks_layout import check_layout
from engram.doctor.checks_mandatory_budget import (
    DEFAULT_MANDATORY_BUDGET_BYTES,
    check_mandatory_budget,
)
from engram.doctor.checks_pools import check_pool_sync
from engram.doctor.types import CheckIssue, DoctorReport, Severity

__all__ = [
    "DEFAULT_MANDATORY_BUDGET_BYTES",
    "CheckIssue",
    "DoctorReport",
    "Severity",
    "run_doctor",
]


def run_doctor(
    project_root: Path,
    *,
    mandatory_budget_bytes: int = DEFAULT_MANDATORY_BUDGET_BYTES,
) -> DoctorReport:
    """Run all five check categories and return an aggregated report.

    Layout checks short-circuit downstream checks: if `.memory/` itself
    does not exist, drift / index / pool / budget checks have nothing to
    inspect, so we surface only the layout issue and let the operator fix
    that first.
    """
    layout_issues = check_layout(project_root)
    issues: list[CheckIssue] = list(layout_issues)

    # If `.memory/` is missing entirely, downstream checks would either
    # crash or produce noise. Bail early.
    if any(i.code == "DOC-LAYOUT-001" for i in layout_issues):
        return DoctorReport(issues=issues)

    issues.extend(check_graph_db_drift(project_root))
    issues.extend(check_index_reachability(project_root))
    issues.extend(check_pool_sync(project_root))
    issues.extend(check_mandatory_budget(project_root, mandatory_budget_bytes))
    return DoctorReport(issues=issues)
