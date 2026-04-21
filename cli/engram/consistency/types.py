"""Data types for the Consistency Engine (SPEC §1.2 / §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "ConflictClass",
    "ConflictReport",
    "ConflictSeverity",
    "ConsistencyReport",
    "Resolution",
    "ResolutionKind",
]


class ConflictClass(str, Enum):
    """The seven conflict classes from SPEC §1.2 / §11."""

    FACTUAL = "factual-conflict"
    RULE = "rule-conflict"
    REFERENCE_ROT = "reference-rot"
    WORKFLOW_DECAY = "workflow-decay"
    TIME_EXPIRED = "time-expired"
    SILENT_OVERRIDE = "silent-override"
    TOPIC_DIVERGENCE = "topic-divergence"


class ConflictSeverity(str, Enum):
    """Severity for downstream rendering and ``engram review`` sorting."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ResolutionKind(str, Enum):
    """Action the engine *proposes*. Never executed automatically."""

    UPDATE = "update"        # edit an existing asset
    SUPERSEDE = "supersede"  # write a new asset that supersedes another
    MERGE = "merge"          # combine two assets into one
    ARCHIVE = "archive"      # move to ~/.engram/archive/ (human confirms)
    DISMISS = "dismiss"      # no action; record the decision and move on
    ESCALATE = "escalate"    # flag for scope owner (team / org)


@dataclass(frozen=True, slots=True)
class Resolution:
    """A proposed fix for a conflict. The engine never applies it itself.

    - ``target``: the asset id the action operates on.
    - ``related``: other asset ids referenced by the action (the
      superseded id, the merge source, etc.). Empty for single-asset
      actions.
    - ``detail``: a short, human-readable explanation rendered by
      ``engram review``.
    """

    kind: ResolutionKind
    target: str
    related: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ConflictReport:
    """One detected conflict. Emitted by a phase detector, graded by the
    evaluator, rendered by ``engram review``."""

    conflict_class: ConflictClass
    severity: ConflictSeverity
    primary_asset: str
    related_assets: tuple[str, ...]
    message: str
    phase: int                   # 1, 2, 3, or 4
    proposed: tuple[Resolution, ...] = ()
    evaluator_approved: bool = True
    evaluator_reason: str = ""


@dataclass(frozen=True, slots=True)
class ConsistencyReport:
    """Outcome of one full scan."""

    conflicts: tuple[ConflictReport, ...]
    phase_counts: dict[int, int] = field(default_factory=dict)
    evaluator_rejected: int = 0

    @property
    def total(self) -> int:
        return len(self.conflicts)

    @property
    def by_class(self) -> dict[ConflictClass, int]:
        out: dict[ConflictClass, int] = {}
        for c in self.conflicts:
            out[c.conflict_class] = out.get(c.conflict_class, 0) + 1
        return out
