"""Layout checks: `.memory/` / `.engram/` / version file."""

from __future__ import annotations

from pathlib import Path

from engram.doctor.types import CheckIssue, Severity


def check_layout(project_root: Path) -> list[CheckIssue]:
    # Lazy-import STORE_VERSION to break the import cycle:
    # engram.commands.init → (transitively) engram.consistency / cli →
    # engram.commands.review → engram.commands.validate → engram.cli →
    # _register_subcommands → engram.commands.doctor → engram.doctor →
    # engram.doctor.checks_layout (mid-init of engram.commands.init).
    from engram.commands.init import STORE_VERSION

    issues: list[CheckIssue] = []
    memory = project_root / ".memory"
    engram = project_root / ".engram"

    if not memory.is_dir():
        issues.append(
            CheckIssue(
                code="DOC-LAYOUT-001",
                severity=Severity.ERROR,
                message=f"{memory}/ does not exist; this is not an engram project",
                fix_command=f"engram init --dir {project_root}",
            )
        )
        return issues  # downstream checks would be noise

    if not (memory / "MEMORY.md").is_file():
        issues.append(
            CheckIssue(
                code="DOC-LAYOUT-003",
                severity=Severity.ERROR,
                message=f"{memory}/MEMORY.md is missing",
                fix_command=f"engram init --dir {project_root} --force",
            )
        )

    if not engram.is_dir():
        issues.append(
            CheckIssue(
                code="DOC-LAYOUT-004",
                severity=Severity.WARNING,
                message=f"{engram}/ does not exist; graph.db queries will fail",
                fix_command=f"engram init --dir {project_root} --adopt",
            )
        )
        return issues

    version_file = engram / "version"
    if not version_file.is_file():
        issues.append(
            CheckIssue(
                code="DOC-LAYOUT-002",
                severity=Severity.ERROR,
                message=f"{version_file} is missing; engram cannot determine store version",
                fix_command=f"engram init --dir {project_root} --adopt",
            )
        )
        return issues

    version = version_file.read_text(encoding="utf-8").strip()
    if version != STORE_VERSION:
        issues.append(
            CheckIssue(
                code="DOC-LAYOUT-005",
                severity=Severity.WARNING,
                message=(
                    f"store version is {version!r}, expected {STORE_VERSION!r}; "
                    "you may need to migrate"
                ),
                fix_command=f"engram migrate --from=v{version} --dir {project_root}",
            )
        )

    return issues
