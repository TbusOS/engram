"""Consistency Engine dispatcher (T-46) — SPEC §1.2 + DESIGN §5.2.

One-shot ``run_consistency_scan(store_root)`` runs all four phases in
order, routes every detector output through the evaluator, and returns
a single :class:`ConsistencyReport`. The engine is stateless; callers
(``engram review``, ``engram consistency scan``) can invoke it at any
cadence without tracking prior runs.

Phases:

1. **Static** (:mod:`phase1_static`) — converts SPEC §12 error codes
   into conflict reports. Implemented today.
2. **Semantic** (:mod:`phase2_semantic`) — body-hash duplicates,
   name-opposite rule detection. Minimal M4 subset; full DBSCAN
   clustering in T-48.
3. **References** (:mod:`phase3_references`) — transitive graph
   health. Stub in M4 (see module docstring for why).
4. **Staleness** (:mod:`phase4_staleness`) — time-expired class. Stub
   in M4 until Evolve Engine supplies usage telemetry.

Each phase is a pure function from ``store_root`` to a list of
:class:`ConflictReport`. Adding / replacing a phase is a one-line
edit at the call site below.
"""

from __future__ import annotations

from pathlib import Path

from engram.consistency.evaluator import evaluate_reports
from engram.consistency.phase1_static import detect_phase1
from engram.consistency.phase2_semantic import detect_phase2
from engram.consistency.phase3_references import detect_phase3
from engram.consistency.phase4_staleness import detect_phase4
from engram.consistency.types import ConflictReport, ConsistencyReport

__all__ = ["run_consistency_scan"]


_PHASES = (
    (1, detect_phase1),
    (2, detect_phase2),
    (3, detect_phase3),
    (4, detect_phase4),
)


def run_consistency_scan(store_root: Path) -> ConsistencyReport:
    all_reports: list[ConflictReport] = []
    phase_counts: dict[int, int] = {}
    for phase_num, detector in _PHASES:
        phase_reports = detector(store_root)
        phase_counts[phase_num] = len(phase_reports)
        all_reports.extend(phase_reports)

    # GAN pattern: run the evaluator over every detector output. A
    # proposal that fails grading is dropped or the whole report is
    # marked `evaluator_approved=False` with a reason the operator
    # can read in `engram review`.
    before = len(all_reports)
    graded = evaluate_reports(all_reports)
    rejected = sum(1 for r in graded if not r.evaluator_approved)
    _ = before  # kept for future telemetry; currently unused

    return ConsistencyReport(
        conflicts=tuple(graded),
        phase_counts=phase_counts,
        evaluator_rejected=rejected,
    )
