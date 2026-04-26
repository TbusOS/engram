"""Session asset type — Episodic memory layer.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §3.2.

A Session asset captures one continuous LLM-driven work span: from the
client's first ``session_start`` event through ``session_end``. It is
**not** a Memory — it lives at ``.memory/sessions/<YYYY-MM-DD>/sess_<id>.md``
and never participates in mandatory bypass. Sessions feed Stage 0 of
the Relevance Gate (T-206) and may be promoted to Memory only via
explicit ``engram distill promote`` (T-209).

This module provides:

- :data:`CLIENT_VALUES` — the closed enum of legal ``client`` values
  (matches :mod:`engram.observer.cli`'s ``--client`` choices).
- :class:`SessionFrontmatter` — typed view of the YAML frontmatter.
- :func:`parse_session_file` / :func:`render_session_file` — round-trip
  IO with byte-fidelity guarantee on the body.
- :func:`session_path` — picks the date-bucketed location.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engram.observer.paths import validate_session_id

__all__ = [
    "CLIENT_VALUES",
    "DEFAULT_ENFORCEMENT",
    "DEFAULT_SCOPE",
    "OUTCOME_VALUES",
    "SESSION_FILENAME_RE",
    "SessionConfidence",
    "SessionFrontmatter",
    "SessionParseError",
    "parse_session_file",
    "parse_session_frontmatter",
    "render_session_file",
    "session_path",
    "sessions_root",
]

# Mirrors observer.cli ``--client`` choices. Kept duplicated rather than
# imported so the data layer does not import the CLI layer (DESIGN §4.2
# layering). Drift is caught by ``test_client_values_match_cli``.
CLIENT_VALUES: frozenset[str] = frozenset(
    {
        "claude-code",
        "codex",
        "cursor",
        "gemini-cli",
        "opencode",
        "manual",
        "raw-api",
    }
)

OUTCOME_VALUES: frozenset[str] = frozenset(
    {"completed", "abandoned", "error", "unknown"}
)

# Sessions live under .memory/sessions/<YYYY-MM-DD>/ — the per-day
# directory keeps `ls` results scannable even after years of usage.
SESSION_FILENAME_RE = re.compile(r"^sess_[a-z0-9][a-z0-9_-]{0,95}\.md$")

DEFAULT_SCOPE = "project"
DEFAULT_ENFORCEMENT = "hint"


class SessionParseError(ValueError):
    """Raised when a session asset's frontmatter cannot be parsed/validated."""


@dataclass(frozen=True, slots=True)
class SessionConfidence:
    """Mirror of ``Memory`` confidence block, scoped to sessions.

    The same five fields as the v0.2.1 confidence cache (T-185), so
    sessions ride the same usage bus path.
    """

    validated_score: float = 0.0
    contradicted_score: float = 0.0
    exposure_count: int = 0
    last_validated: date | None = None
    evidence_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "validated_score": self.validated_score,
            "contradicted_score": self.contradicted_score,
            "exposure_count": self.exposure_count,
            "last_validated": self.last_validated.isoformat() if self.last_validated else None,
            "evidence_version": self.evidence_version,
        }


@dataclass(frozen=True, slots=True)
class SessionFrontmatter:
    """Validated frontmatter for a Session asset."""

    type: str  # always "session" — kept as a field so the YAML round-trips cleanly
    session_id: str
    client: str
    started_at: datetime
    ended_at: datetime | None
    task_hash: str | None = None
    tool_calls: int = 0
    files_touched: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    outcome: str = "unknown"
    error_summary: str | None = None
    prev_session: str | None = None
    next_session: str | None = None
    distilled_into: tuple[str, ...] = ()
    scope: str = DEFAULT_SCOPE
    enforcement: str = DEFAULT_ENFORCEMENT
    confidence: SessionConfidence = field(default_factory=SessionConfidence)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> int | None:
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds())

    def to_yaml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": "session",
            "session_id": self.session_id,
            "client": self.client,
            "started_at": _iso(self.started_at),
            "ended_at": _iso(self.ended_at) if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "task_hash": self.task_hash,
            "tool_calls": self.tool_calls,
            "files_touched": list(self.files_touched),
            "files_modified": list(self.files_modified),
            "outcome": self.outcome,
            "error_summary": self.error_summary,
            "prev_session": self.prev_session,
            "next_session": self.next_session,
            "distilled_into": list(self.distilled_into),
            "scope": self.scope,
            "enforcement": self.enforcement,
            "confidence": self.confidence.to_dict(),
        }
        # Preserve unknown fields (SPEC §4.1 invariant).
        for key, value in self.extra.items():
            if key not in out:
                out[key] = value
        return out


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


_KNOWN_FIELDS = {
    "type",
    "session_id",
    "client",
    "started_at",
    "ended_at",
    "duration_seconds",
    "task_hash",
    "tool_calls",
    "files_touched",
    "files_modified",
    "outcome",
    "error_summary",
    "prev_session",
    "next_session",
    "distilled_into",
    "scope",
    "enforcement",
    "confidence",
}


def parse_session_frontmatter(data: dict[str, Any]) -> SessionFrontmatter:
    """Validate ``data`` (a parsed YAML mapping) into a SessionFrontmatter."""
    if not isinstance(data, dict):
        raise SessionParseError(f"frontmatter must be a mapping, got {type(data).__name__}")

    type_field = data.get("type")
    if type_field != "session":
        raise SessionParseError(f"type must equal 'session', got {type_field!r}")

    session_id = data.get("session_id")
    if not isinstance(session_id, str):
        raise SessionParseError("session_id required (string)")
    validate_session_id(session_id)  # raises InvalidSessionIdError

    client = data.get("client")
    if client not in CLIENT_VALUES:
        raise SessionParseError(
            f"client {client!r} not in allowed set: {sorted(CLIENT_VALUES)}"
        )

    started_at_raw = data.get("started_at")
    if started_at_raw is None:
        raise SessionParseError("started_at required (ISO-8601 datetime)")
    started_at = _parse_dt(started_at_raw, field_name="started_at")

    ended_at_raw = data.get("ended_at")
    ended_at = _parse_dt(ended_at_raw, field_name="ended_at") if ended_at_raw else None

    outcome = data.get("outcome", "unknown")
    if outcome not in OUTCOME_VALUES:
        raise SessionParseError(
            f"outcome {outcome!r} not in allowed set: {sorted(OUTCOME_VALUES)}"
        )

    confidence_raw = data.get("confidence", {})
    confidence = _parse_confidence(confidence_raw)

    extra: dict[str, Any] = {k: v for k, v in data.items() if k not in _KNOWN_FIELDS}

    return SessionFrontmatter(
        type="session",
        session_id=session_id,
        client=client,
        started_at=started_at,
        ended_at=ended_at,
        task_hash=_maybe_str(data.get("task_hash")),
        tool_calls=int(data.get("tool_calls", 0) or 0),
        files_touched=_str_tuple(data.get("files_touched")),
        files_modified=_str_tuple(data.get("files_modified")),
        outcome=outcome,
        error_summary=_maybe_str(data.get("error_summary")),
        prev_session=_maybe_str(data.get("prev_session")),
        next_session=_maybe_str(data.get("next_session")),
        distilled_into=_str_tuple(data.get("distilled_into")),
        scope=str(data.get("scope", DEFAULT_SCOPE)),
        enforcement=str(data.get("enforcement", DEFAULT_ENFORCEMENT)),
        confidence=confidence,
        extra=extra,
    )


def _parse_confidence(value: Any) -> SessionConfidence:
    if value is None or value == {}:
        return SessionConfidence()
    if not isinstance(value, dict):
        raise SessionParseError(
            f"confidence must be a mapping, got {type(value).__name__}"
        )
    last_raw = value.get("last_validated")
    last: date | None
    if last_raw is None:
        last = None
    elif isinstance(last_raw, date):
        last = last_raw
    elif isinstance(last_raw, str):
        try:
            last = date.fromisoformat(last_raw)
        except ValueError as exc:
            raise SessionParseError(f"confidence.last_validated invalid: {exc}") from exc
    else:
        raise SessionParseError(
            f"confidence.last_validated must be ISO date, got {type(last_raw).__name__}"
        )
    return SessionConfidence(
        validated_score=float(value.get("validated_score", 0.0) or 0.0),
        contradicted_score=float(value.get("contradicted_score", 0.0) or 0.0),
        exposure_count=int(value.get("exposure_count", 0) or 0),
        last_validated=last,
        evidence_version=int(value.get("evidence_version", 1) or 1),
    )


def _parse_dt(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SessionParseError(f"{field_name} invalid ISO-8601: {exc}") from exc
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    raise SessionParseError(
        f"{field_name} must be string or datetime, got {type(value).__name__}"
    )


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    raise SessionParseError(f"expected list of strings, got {type(value).__name__}")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------
# File IO
# ----------------------------------------------------------------------


_FRONTMATTER_DELIM = "---"


def parse_session_file(path: Path) -> tuple[SessionFrontmatter, str]:
    """Parse a session asset file → (frontmatter, body).

    Body is returned verbatim so daemon-driven appends and Tier 2
    distillation never lose user content (SPEC §4.1 preservation).
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_FRONTMATTER_DELIM):
        raise SessionParseError(f"missing leading '---' frontmatter in {path}")

    rest = text[len(_FRONTMATTER_DELIM) :]
    end_idx = rest.find("\n" + _FRONTMATTER_DELIM)
    if end_idx < 0:
        raise SessionParseError(f"missing closing '---' frontmatter in {path}")

    yaml_text = rest[:end_idx].lstrip("\n")
    body_after = rest[end_idx + len("\n" + _FRONTMATTER_DELIM) :]
    if body_after.startswith("\n"):
        body_after = body_after[1:]

    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise SessionParseError(f"YAML parse failed for {path}: {exc}") from exc

    fm = parse_session_frontmatter(data)
    return fm, body_after


def render_session_file(frontmatter: SessionFrontmatter, body: str) -> str:
    """Render a SessionFrontmatter + body to canonical session asset text.

    The output is always ``---\\n<yaml>\\n---\\n<body>``. Body is taken
    verbatim — callers MUST construct the body string themselves; this
    function does not re-flow whitespace.
    """
    yaml_dict = frontmatter.to_yaml_dict()
    yaml_text = yaml.safe_dump(
        yaml_dict, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.endswith("\n"):
        body = body + "\n"
    return f"{_FRONTMATTER_DELIM}\n{yaml_text}{_FRONTMATTER_DELIM}\n{body}"


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def sessions_root(memory_dir: Path) -> Path:
    """Path to ``<memory_dir>/sessions/`` — the per-store Session asset root."""
    return memory_dir / "sessions"


def session_path(
    session_id: str,
    *,
    started_at: datetime,
    memory_dir: Path,
) -> Path:
    """Path to the session asset file under ``.memory/sessions/<date>/sess_<id>.md``.

    The date bucket is the UTC calendar date of ``started_at`` so two
    machines in different timezones produce the same path.
    """
    sid = validate_session_id(session_id)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    bucket = started_at.astimezone(timezone.utc).date().isoformat()
    return sessions_root(memory_dir) / bucket / f"sess_{sid}.md"
