"""Index reachability check: every asset reachable from MEMORY.md.

Today's contract follows the existing conformance INV-I1 ("directly
listed"). When SPEC-AMEND v0.2.1 / T-181 (issue #5) lands, this check
relaxes to "reachable in 2 hops" via `index/<topic>.md` traversal — the
issue here will gain a parallel ``DOC-INDEX-002 unreachable-via-index``
code that supersedes the strict directly-listed rule.
"""

from __future__ import annotations

from pathlib import Path

from engram.commands.memory import graph_db_path
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.doctor.types import CheckIssue, Severity


def check_index_reachability(project_root: Path) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    db_path = graph_db_path(project_root)
    if not db_path.parent.is_dir():
        return issues

    memory_md = memory_dir(project_root) / "MEMORY.md"
    if not memory_md.is_file():
        return issues  # layout check covers this

    text = memory_md.read_text(encoding="utf-8")

    with open_graph_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, path FROM assets WHERE kind='memory'"
        ).fetchall()

    for row in rows:
        # Direct hits: the asset id, the path, or the path stem must
        # appear somewhere in MEMORY.md.
        candidates = (row["id"], row["path"], Path(row["path"]).stem)
        if not any(c in text for c in candidates):
            issues.append(
                CheckIssue(
                    code="DOC-INDEX-001",
                    severity=Severity.WARNING,
                    message=f"asset {row['id']} is not referenced from MEMORY.md",
                    fix_command=(
                        "edit .memory/MEMORY.md and add a link to "
                        f"{row['path']} (or wait for T-181 reachability semantics)"
                    ),
                    file=row["path"],
                )
            )

    return issues
