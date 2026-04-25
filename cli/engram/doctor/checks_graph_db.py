"""graph.db drift checks: file-without-row + row-without-file."""

from __future__ import annotations

from pathlib import Path

from engram.commands.memory import graph_db_path
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.doctor.types import CheckIssue, Severity


_SCAN_SUBDIRS: tuple[str, ...] = ("local", "workflows", "kb")


def check_graph_db_drift(project_root: Path) -> list[CheckIssue]:
    """Find files on disk with no graph.db row, and rows pointing to
    files that have been deleted."""
    issues: list[CheckIssue] = []
    db_path = graph_db_path(project_root)
    mem_root = memory_dir(project_root)

    # graph.db is created lazily by open_graph_db; we only bail when the
    # parent .engram/ directory is missing (layout check already covered).
    if not db_path.parent.is_dir():
        return issues

    on_disk: set[str] = set()
    for sub in _SCAN_SUBDIRS:
        sub_dir = mem_root / sub
        if not sub_dir.is_dir():
            continue
        for md in sub_dir.rglob("*.md"):
            on_disk.add(str(md.relative_to(mem_root)))

    in_db: dict[str, str] = {}
    with open_graph_db(db_path) as conn:
        for row in conn.execute(
            "SELECT id, path FROM assets WHERE kind='memory'"
        ).fetchall():
            in_db[row["path"]] = row["id"]

    db_paths = set(in_db)

    for missing_row in sorted(on_disk - db_paths):
        issues.append(
            CheckIssue(
                code="DOC-GRAPH-001",
                severity=Severity.WARNING,
                message=f"asset file {missing_row} exists on disk but has no graph.db row",
                fix_command=f"engram init --dir {project_root} --adopt",
                file=missing_row,
            )
        )

    for orphan in sorted(db_paths - on_disk):
        issues.append(
            CheckIssue(
                code="DOC-GRAPH-002",
                severity=Severity.WARNING,
                message=(
                    f"graph.db references {in_db[orphan]} ({orphan}) but the "
                    "file has been deleted from disk"
                ),
                fix_command=f"engram memory archive {in_db[orphan]} --dir {project_root}",
                file=orphan,
            )
        )

    return issues
