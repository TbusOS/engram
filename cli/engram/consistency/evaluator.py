"""Evaluator — second-opinion pass over detector-proposed resolutions.

Design per ``docs/superpowers/specs/2026-04-22-productization-plan.md`` §3:
the Consistency Engine's Detectors produce :class:`ConflictReport`
records with one or more :class:`Resolution` proposals. Before those
reach ``engram review``, a separate **Evaluator** grades each proposal
against SPEC invariants.

The evaluator is intentionally *rule-based and deterministic* in M4:
no LLM, no vector model. The goal is to catch obvious bad proposals
(an ``ARCHIVE`` of a ``mandatory`` asset, a ``SUPERSEDE`` pointing at
a nonexistent id, an ``UPDATE`` that would change the conflict class
rather than fix it). An LLM-backed evaluator that does semantic
grading lands with M5 once the embedder is available.

Separating this from the detector mirrors the GAN pattern from the
Anthropic *harness design for long-running apps* write-up: when the
generator is tempted to rationalize a bad move, the evaluator —
independent, rule-bound — says no.
"""

from __future__ import annotations

from dataclasses import replace

from engram.consistency.types import (
    ConflictClass,
    ConflictReport,
    Resolution,
    ResolutionKind,
)

__all__ = ["evaluate_report", "evaluate_reports"]


def _check_resolution(
    report: ConflictReport, resolution: Resolution
) -> tuple[bool, str]:
    """Return ``(ok, reason)`` — ``ok=False`` blocks the proposal."""
    if resolution.target == "":
        return False, "resolution target is empty"
    if resolution.kind == ResolutionKind.SUPERSEDE and not resolution.related:
        return False, "supersede requires a related target (what is superseded)"
    if resolution.kind == ResolutionKind.MERGE and not resolution.related:
        return False, "merge requires a related target (what to merge with)"
    # SPEC §1.2 principle 4: never auto-delete. An ARCHIVE proposal on a
    # mandatory asset is a protocol violation — mandatory can only be
    # archived by the scope that created it (SPEC §8.3). The detector
    # doesn't know the enforcement level, but the evaluator can refuse
    # archive proposals on assets whose asset id starts with
    # "org/" or "team/" — those come from higher scopes the local user
    # cannot unilaterally archive.
    if resolution.kind == ResolutionKind.ARCHIVE and resolution.target.startswith(
        ("org/", "team/")
    ):
        return False, (
            "cannot archive a higher-scope asset from a subscriber; "
            "escalate to the scope owner instead (SPEC §8.3)"
        )
    # UPDATE on a reference-rot conflict should target the asset
    # holding the bad link, not the missing target.
    if (
        report.conflict_class == ConflictClass.REFERENCE_ROT
        and resolution.kind == ResolutionKind.UPDATE
        and resolution.target != report.primary_asset
    ):
        return False, (
            "reference-rot UPDATE must target the asset with the broken "
            "reference, not the missing destination"
        )
    return True, ""


def evaluate_report(report: ConflictReport) -> ConflictReport:
    """Return a new ``ConflictReport`` with ``evaluator_approved`` / reason set.

    If every proposed resolution passes, ``evaluator_approved`` stays
    True and ``evaluator_reason`` is empty. If any fails, the whole
    report is marked unapproved with the first failing reason — and
    only the passing resolutions are retained in ``proposed``. Detectors
    that didn't propose any resolution pass through unchanged (they're
    observational-only; no resolution to grade)."""
    if not report.proposed:
        return report

    kept: list[Resolution] = []
    first_reject: str = ""
    for r in report.proposed:
        ok, reason = _check_resolution(report, r)
        if ok:
            kept.append(r)
        elif not first_reject:
            first_reject = f"{r.kind.value}: {reason}"

    if not kept:
        return replace(
            report,
            evaluator_approved=False,
            evaluator_reason=first_reject,
            proposed=(),
        )
    if len(kept) < len(report.proposed):
        # Partial pass — downgrade the overall flag but keep the good ones.
        return replace(
            report,
            evaluator_approved=False,
            evaluator_reason=first_reject,
            proposed=tuple(kept),
        )
    return report


def evaluate_reports(reports: list[ConflictReport]) -> list[ConflictReport]:
    return [evaluate_report(r) for r in reports]
