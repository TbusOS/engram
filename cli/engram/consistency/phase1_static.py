"""Phase 1 — static conflict detection (SPEC §12 error codes).

Wraps :func:`engram.commands.validate.run_validate` and converts each
relevant issue into a :class:`ConflictReport`. M4 scope covers the
errors that map naturally to conflict classes; the fuller mapping
lands with T-47.

Mapping (M4 subset):

- ``E-IDX-001`` (dangling link in MEMORY.md)    → ``REFERENCE_ROT``
- ``E-REF-001`` / ``E-REF-003`` (missing references /
  supersedes target) → ``REFERENCE_ROT``
- ``E-ENF-001`` (lower-scope override of mandatory) — not yet emitted
  by validate; reserved for T-47.
"""

from __future__ import annotations

from pathlib import Path

from engram.commands.validate import Issue, run_validate
from engram.consistency.types import (
    ConflictClass,
    ConflictReport,
    ConflictSeverity,
    Resolution,
    ResolutionKind,
)

__all__ = ["detect_phase1"]


_CODE_TO_CLASS: dict[str, ConflictClass] = {
    "E-IDX-001": ConflictClass.REFERENCE_ROT,
    "E-REF-001": ConflictClass.REFERENCE_ROT,
    "E-REF-003": ConflictClass.REFERENCE_ROT,
}


def _severity(issue: Issue) -> ConflictSeverity:
    return {
        "error": ConflictSeverity.ERROR,
        "warning": ConflictSeverity.WARNING,
        "info": ConflictSeverity.INFO,
    }.get(issue.severity, ConflictSeverity.INFO)


def detect_phase1(store_root: Path) -> list[ConflictReport]:
    reports: list[ConflictReport] = []
    for issue in run_validate(store_root):
        cls = _CODE_TO_CLASS.get(issue.code)
        if cls is None:
            continue  # not a conflict class we track in phase 1
        resolution = Resolution(
            kind=ResolutionKind.UPDATE,
            target=issue.file,
            detail=f"fix the broken link/reference flagged by {issue.code}",
        )
        reports.append(
            ConflictReport(
                conflict_class=cls,
                severity=_severity(issue),
                primary_asset=issue.file,
                related_assets=(),
                message=f"[{issue.code}] {issue.message}",
                phase=1,
                proposed=(resolution,),
            )
        )
    return reports
