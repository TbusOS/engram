"""Mandatory body-size budget check.

Issue #8 / T-184 will introduce a `directive` field for mandatory assets
so Stage 1 bypass loads only the directive, not the full body. Until
that lands, doctor warns when the cumulative mandatory body size exceeds
a recommended budget — the operator can split long mandatory rules into
short directive + KB reference manually.
"""

from __future__ import annotations

from pathlib import Path

from engram.commands.memory import graph_db_path
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.doctor.types import CheckIssue, Severity

# Default budget chosen so a full Claude / Opus 4 context can absorb the
# entire mandatory set without crowding out task-specific assets. The
# operator can override via ``run_doctor(..., mandatory_budget_bytes=N)``.
DEFAULT_MANDATORY_BUDGET_BYTES = 16_000


def check_mandatory_budget(
    project_root: Path, budget_bytes: int = DEFAULT_MANDATORY_BUDGET_BYTES
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    db_path = graph_db_path(project_root)
    if not db_path.parent.is_dir():
        return issues
    memory_dir(project_root)

    total_bytes = 0
    overweight: list[tuple[str, int]] = []
    with open_graph_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, path, size_bytes FROM assets "
            "WHERE kind='memory' AND enforcement='mandatory'"
        ).fetchall()

    for row in rows:
        size = int(row["size_bytes"] or 0)
        total_bytes += size
        if size > budget_bytes // 4:  # any single mandatory > 25% of budget is loud
            overweight.append((row["id"], size))

    if total_bytes > budget_bytes:
        issues.append(
            CheckIssue(
                code="DOC-MAND-001",
                severity=Severity.WARNING,
                message=(
                    f"mandatory assets total {total_bytes} bytes "
                    f"(budget {budget_bytes}); consider splitting long rules "
                    f"into a short `directive` field + KB reference (T-184)"
                ),
                fix_command=(
                    "engram review (look for `mandatory` rows ranked by size); "
                    "edit each oversized asset to add a `directive:` field"
                ),
            )
        )

    for asset_id, size in overweight:
        issues.append(
            CheckIssue(
                code="DOC-MAND-002",
                severity=Severity.INFO,
                message=(
                    f"mandatory asset {asset_id} is {size} bytes — single rule "
                    "occupies a large share of the mandatory budget"
                ),
                fix_command=f"engram memory read {asset_id}",
            )
        )

    return issues
