"""Schemas for the usage event bus.

The on-disk format is **one event per line** in
``~/.engram/journal/usage.jsonl``. The schema is the SPEC §11.4 contract
(landing as part of T-172 SPEC-AMEND v0.2.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from engram.core.paths import user_root


def usage_jsonl_path() -> Path:
    """Resolve ``~/.engram/journal/usage.jsonl`` honoring ``ENGRAM_DIR``."""
    return user_root() / "journal" / "usage.jsonl"


class EventType(str, Enum):
    LOADED = "loaded"
    VALIDATED = "validated"
    CONTRADICTED = "contradicted"


class ActorType(str, Enum):
    HUMAN = "human"
    LLM = "llm"
    WORKFLOW = "workflow"
    CONSISTENCY_ENGINE = "consistency_engine"


class EvidenceKind(str, Enum):
    """Eight kinds of evidence, ranked by trust per issue #9.

    The default ``trust_weight`` for each kind is in
    ``engram.usage.trust_weights.DEFAULT_TRUST_WEIGHTS``. Evidence with
    weight 0.0 (``LOADED_ONLY``) only contributes to ``exposure_count``.
    """

    EXPLICIT_USER_CONFIRMATION = "explicit_user_confirmation"
    EXPLICIT_USER_CORRECTION = "explicit_user_correction"
    WORKFLOW_FIXTURE_PASS = "workflow_fixture_pass"
    WORKFLOW_FIXTURE_FAIL = "workflow_fixture_fail"
    TASK_SUCCESS_HEURISTIC = "task_success_heuristic"
    TASK_FAILURE_HEURISTIC = "task_failure_heuristic"
    FALSE_POSITIVE_DISMISSED = "false_positive_dismissed"
    LOADED_ONLY = "loaded_only"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


@dataclass
class UsageEvent:
    asset_uri: str
    task_hash: str
    event_type: EventType
    actor_type: ActorType
    evidence_kind: EvidenceKind
    trust_weight: float | None = None  # None → defaults from evidence_kind
    co_assets: tuple[str, ...] = ()
    timestamp: str = field(default_factory=_utc_now_iso)
    session_id: str | None = None
    model_id: str | None = None

    def __post_init__(self) -> None:
        if self.trust_weight is None:
            # Local import to avoid circulars with trust_weights → types.
            from engram.usage.trust_weights import DEFAULT_TRUST_WEIGHTS

            self.trust_weight = DEFAULT_TRUST_WEIGHTS[self.evidence_kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_uri": self.asset_uri,
            "task_hash": self.task_hash,
            "event_type": self.event_type.value,
            "actor_type": self.actor_type.value,
            "evidence_kind": self.evidence_kind.value,
            "trust_weight": float(self.trust_weight or 0.0),
            "co_assets": list(self.co_assets),
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "model_id": self.model_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageEvent:
        return cls(
            asset_uri=data["asset_uri"],
            task_hash=data["task_hash"],
            event_type=EventType(data["event_type"]),
            actor_type=ActorType(data["actor_type"]),
            evidence_kind=EvidenceKind(data["evidence_kind"]),
            trust_weight=float(data.get("trust_weight", 0.0)),
            co_assets=tuple(data.get("co_assets") or ()),
            timestamp=data.get("timestamp") or _utc_now_iso(),
            session_id=data.get("session_id"),
            model_id=data.get("model_id"),
        )
