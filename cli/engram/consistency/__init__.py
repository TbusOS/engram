"""Consistency Engine — detects the seven conflict classes from SPEC §1.2 / §11.

The engine is deliberately split along the detect-vs-evaluate boundary
motivated by Anthropic's *harness design for long-running apps* note
(see ``docs/superpowers/specs/2026-04-22-productization-plan.md`` §3):

- **Detectors** (:mod:`engram.consistency.phase1_static`,
  :mod:`engram.consistency.phase2_semantic`,
  :mod:`engram.consistency.phase3_references`,
  :mod:`engram.consistency.phase4_staleness`) produce structured
  :class:`ConflictReport` records with proposed :class:`Resolution` objects.
  They never see each other's reasoning.

- **Evaluator** (:mod:`engram.consistency.evaluator`) grades each
  proposed resolution against SPEC invariants (``never auto-delete``,
  ``mandatory cannot be overridden``, etc.). A detector-proposed
  resolution that fails the evaluator is downgraded — the engine never
  surfaces a known-bad proposal to the operator.

The engine is a library component. The ``engram review`` CLI subcommand
(M4) consumes the final reports and renders them for human decision.
"""

from engram.consistency.engine import run_consistency_scan
from engram.consistency.types import (
    ConflictClass,
    ConflictReport,
    ConflictSeverity,
    ConsistencyReport,
    Resolution,
    ResolutionKind,
)

__all__ = [
    "ConflictClass",
    "ConflictReport",
    "ConflictSeverity",
    "ConsistencyReport",
    "Resolution",
    "ResolutionKind",
    "run_consistency_scan",
]
