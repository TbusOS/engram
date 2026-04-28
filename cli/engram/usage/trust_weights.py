"""Authoritative trust-weight table per issue #9 / T-172.

These defaults will be lifted into SPEC §11.4 once SPEC-AMEND v0.2.1
lands. Changing a default here is a SPEC-affecting change — bump the
``evidence_version`` field in derived ``ConfidenceCache`` rows so stale
caches get recomputed automatically.
"""

from __future__ import annotations

from engram.usage.types import EvidenceKind

# Bump when the table below changes; ConfidenceCache stores this so
# stale caches can be detected + recomputed automatically.
EVIDENCE_VERSION = 1


DEFAULT_TRUST_WEIGHTS: dict[EvidenceKind, float] = {
    # Strong positive: a human said "this asset was right for this task"
    EvidenceKind.EXPLICIT_USER_CONFIRMATION: +1.0,
    # Strong negative: a human corrected behavior that came from the asset
    EvidenceKind.EXPLICIT_USER_CORRECTION: -1.0,
    # Mid-high positive: workflow fixtures passed against this asset
    EvidenceKind.WORKFLOW_FIXTURE_PASS: +0.6,
    # Mid-high negative: workflow fixtures failed
    EvidenceKind.WORKFLOW_FIXTURE_FAIL: -0.6,
    # Mid positive: user dismissed a Consistency Engine false-positive
    # warning about this asset → implicit confirmation it was correct
    EvidenceKind.FALSE_POSITIVE_DISMISSED: +0.4,
    # Weak positive: LLM self-reported a task succeeded; can be inflated
    # by co_assets (split applies in derive_confidence_cache)
    EvidenceKind.TASK_SUCCESS_HEURISTIC: +0.2,
    EvidenceKind.TASK_FAILURE_HEURISTIC: -0.2,
    # Zero — exposure but no correctness signal
    EvidenceKind.LOADED_ONLY: 0.0,
}
