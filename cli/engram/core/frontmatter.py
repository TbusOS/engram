"""Memory asset frontmatter parsing and validation.

Implements the SPEC §4.1 schema: six subtypes, five scopes, three enforcement
levels, required + scope-conditional + subtype-specific fields, the nested
``confidence`` block from §4.8, and the SPEC invariant that unknown fields are
**preserved** rather than rejected (so a v0.2 tool can round-trip frontmatter
written by a future version without data loss).

The parser returns typed, immutable dataclasses. Validation is strict on the
hard SPEC requirements (missing required fields, invalid enum values, wrong
value types); soft recommendations (e.g. `confidence` strongly encouraged on
`agent`) are left to :mod:`engram.review` in T-20/T-21.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import yaml

__all__ = [
    "Confidence",
    "Enforcement",
    "FrontmatterError",
    "InvalidEnumValueError",
    "MemoryFrontmatter",
    "MemoryType",
    "MissingFieldError",
    "Scope",
    "parse_file",
    "parse_frontmatter",
]


class MemoryType(str, Enum):
    """The six Memory subtypes from SPEC §4.2-§4.7."""

    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"
    WORKFLOW_PTR = "workflow_ptr"
    AGENT = "agent"


class Scope(str, Enum):
    """The five scope levels from SPEC §8 (2-axis model)."""

    ORG = "org"
    TEAM = "team"
    USER = "user"
    PROJECT = "project"
    POOL = "pool"


class Enforcement(str, Enum):
    """Enforcement levels per glossary §5."""

    MANDATORY = "mandatory"
    DEFAULT = "default"
    HINT = "hint"


_SUBSCRIBED_AT_VALID: tuple[Scope, ...] = (
    Scope.ORG,
    Scope.TEAM,
    Scope.USER,
    Scope.PROJECT,
)


class FrontmatterError(ValueError):
    """Base class for frontmatter parse / validation failures."""


class MissingFieldError(FrontmatterError):
    """A required field (common, scope-conditional, or subtype-specific) is absent."""


class InvalidEnumValueError(FrontmatterError):
    """A field's value is not one of the allowed enum options."""


@dataclass(frozen=True, slots=True)
class Confidence:
    """The nested confidence block from SPEC §4.8."""

    validated_count: int
    contradicted_count: int
    last_validated: date
    usage_count: int


@dataclass(frozen=True, slots=True)
class MemoryFrontmatter:
    """Validated, typed view of a Memory asset's frontmatter."""

    # Required (SPEC §4.1 common required)
    name: str
    description: str
    type: MemoryType
    scope: Scope
    enforcement: Enforcement

    # Scope-conditional
    org: str | None = None
    team: str | None = None
    pool: str | None = None
    subscribed_at: Scope | None = None

    # Common optional
    created: date | None = None
    updated: date | None = None
    tags: tuple[str, ...] = ()
    expires: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    source: str | None = None
    references: tuple[str, ...] = ()
    overrides: str | None = None
    supersedes: str | None = None
    limitations: tuple[str, ...] = ()
    confidence: Confidence | None = None

    # Subtype-specific
    workflow_ref: str | None = None

    # Unknown fields preserved per SPEC §4.1 ("tools MUST NOT delete a key they
    # do not recognize"). Forward-compatible with future SPEC versions.
    extra: dict[str, Any] = field(default_factory=dict)


# Leading YAML frontmatter block delimited by --- lines. DOTALL so `.` spans
# newlines in the YAML body; [ \t]* (not \s*) on the delimiter lines so we
# don't accidentally swallow a content newline into the delimiter.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n(.*))?\Z",
    re.DOTALL,
)

_KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "type",
        "scope",
        "enforcement",
        "org",
        "team",
        "pool",
        "subscribed_at",
        "created",
        "updated",
        "tags",
        "expires",
        "valid_from",
        "valid_to",
        "source",
        "references",
        "overrides",
        "supersedes",
        "limitations",
        "confidence",
        "workflow_ref",
    }
)


def parse_frontmatter(text: str) -> MemoryFrontmatter:
    """Parse and validate a full Memory asset file; return only the frontmatter.

    Use :func:`parse_file` when you also need the body text.
    """
    data, _ = _split(text)
    return _from_dict(data)


def parse_file(path: Path) -> tuple[MemoryFrontmatter, str]:
    """Read ``path`` as UTF-8 and return ``(frontmatter, body)``."""
    text = path.read_text(encoding="utf-8")
    data, body = _split(text)
    return _from_dict(data), body


def _split(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise FrontmatterError("missing YAML frontmatter block (file must start with --- ... ---)")

    yaml_body = match.group(1)
    content_after = match.group(2) or ""

    try:
        parsed = yaml.safe_load(yaml_body)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter YAML is malformed: {exc}") from exc

    if not isinstance(parsed, dict):
        raise FrontmatterError(f"frontmatter must be a YAML mapping, got {type(parsed).__name__}")

    return parsed, content_after


def _from_dict(data: dict[str, Any]) -> MemoryFrontmatter:
    for required in ("name", "description", "type", "scope"):
        if required not in data:
            raise MissingFieldError(f"required field missing: `{required}`")

    mtype = _enum_value(data["type"], MemoryType, "type")
    scope = _enum_value(data["scope"], Scope, "scope")
    enforcement = _enforcement_with_default(data, mtype)

    org = data.get("org")
    team = data.get("team")
    pool = data.get("pool")
    subscribed_at = _subscribed_at(data)

    _validate_scope_conditional(scope, org=org, team=team, pool=pool, subscribed_at=subscribed_at)

    workflow_ref = data.get("workflow_ref")
    source = data.get("source")
    _validate_subtype_specific(mtype, workflow_ref=workflow_ref, source=source)

    confidence = _parse_confidence(data["confidence"]) if "confidence" in data else None

    extra = {k: v for k, v in data.items() if k not in _KNOWN_FIELDS}

    return MemoryFrontmatter(
        name=_require_str(data["name"], "name"),
        description=_require_str(data["description"], "description"),
        type=mtype,
        scope=scope,
        enforcement=enforcement,
        org=_opt_str(org, "org"),
        team=_opt_str(team, "team"),
        pool=_opt_str(pool, "pool"),
        subscribed_at=subscribed_at,
        created=_opt_date(data.get("created"), "created"),
        updated=_opt_date(data.get("updated"), "updated"),
        tags=_list_of_str(data.get("tags"), "tags"),
        expires=_opt_date(data.get("expires"), "expires"),
        valid_from=_opt_date(data.get("valid_from"), "valid_from"),
        valid_to=_opt_date(data.get("valid_to"), "valid_to"),
        source=_opt_str(source, "source"),
        references=_list_of_str(data.get("references"), "references"),
        overrides=_opt_str(data.get("overrides"), "overrides"),
        supersedes=_opt_str(data.get("supersedes"), "supersedes"),
        limitations=_list_of_str(data.get("limitations"), "limitations"),
        confidence=confidence,
        workflow_ref=_opt_str(workflow_ref, "workflow_ref"),
        extra=extra,
    )


_EnumT = TypeVar("_EnumT", bound=Enum)


def _enum_value(raw: Any, enum_cls: type[_EnumT], field_name: str) -> _EnumT:
    try:
        return enum_cls(raw)
    except ValueError:
        allowed = [m.value for m in enum_cls]
        raise InvalidEnumValueError(
            f"invalid {field_name} {raw!r}; expected one of {allowed}"
        ) from None


def _enforcement_with_default(data: dict[str, Any], mtype: MemoryType) -> Enforcement:
    if "enforcement" in data:
        return _enum_value(data["enforcement"], Enforcement, "enforcement")
    if mtype is MemoryType.FEEDBACK:
        raise MissingFieldError("`enforcement` is required for type=feedback (SPEC §4.3)")
    return Enforcement.HINT


def _subscribed_at(data: dict[str, Any]) -> Scope | None:
    raw = data.get("subscribed_at")
    if raw is None:
        return None
    value = _enum_value(raw, Scope, "subscribed_at")
    if value not in _SUBSCRIBED_AT_VALID:
        allowed = [s.value for s in _SUBSCRIBED_AT_VALID]
        raise InvalidEnumValueError(
            f"invalid subscribed_at {raw!r}; expected one of {allowed} "
            "(pool itself is not a valid hierarchy level)"
        )
    return value


def _validate_scope_conditional(
    scope: Scope,
    *,
    org: Any,
    team: Any,
    pool: Any,
    subscribed_at: Scope | None,
) -> None:
    if scope is Scope.ORG and not org:
        raise MissingFieldError("`org` is required when scope=org (SPEC §4.1)")
    if scope is Scope.TEAM and not team:
        raise MissingFieldError("`team` is required when scope=team (SPEC §4.1)")
    if scope is Scope.POOL:
        if not pool:
            raise MissingFieldError("`pool` is required when scope=pool (SPEC §4.1)")
        if subscribed_at is None:
            raise MissingFieldError("`subscribed_at` is required when scope=pool (SPEC §4.1)")


def _validate_subtype_specific(
    mtype: MemoryType,
    *,
    workflow_ref: Any,
    source: Any,
) -> None:
    if mtype is MemoryType.WORKFLOW_PTR and not workflow_ref:
        raise MissingFieldError("`workflow_ref` is required for type=workflow_ptr (SPEC §4.6)")
    if mtype is MemoryType.AGENT and not source:
        raise MissingFieldError("`source` is required for type=agent (SPEC §4.7)")


def _parse_confidence(raw: Any) -> Confidence:
    if not isinstance(raw, dict):
        raise FrontmatterError(f"`confidence` must be a mapping, got {type(raw).__name__}")
    for key in ("validated_count", "contradicted_count", "last_validated", "usage_count"):
        if key not in raw:
            raise MissingFieldError(f"`confidence.{key}` is required (SPEC §4.8)")

    for count_key in ("validated_count", "contradicted_count", "usage_count"):
        value = raw[count_key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FrontmatterError(
                f"`confidence.{count_key}` must be a non-negative integer, got {value!r}"
            )

    return Confidence(
        validated_count=raw["validated_count"],
        contradicted_count=raw["contradicted_count"],
        last_validated=_require_date(raw["last_validated"], "confidence.last_validated"),
        usage_count=raw["usage_count"],
    )


def _require_str(raw: Any, field_name: str) -> str:
    if not isinstance(raw, str):
        raise FrontmatterError(f"`{field_name}` must be a string, got {type(raw).__name__}")
    return raw


def _opt_str(raw: Any, field_name: str) -> str | None:
    if raw is None:
        return None
    return _require_str(raw, field_name)


def _require_date(raw: Any, field_name: str) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise FrontmatterError(
                f"`{field_name}` must be an ISO 8601 date (YYYY-MM-DD), got {raw!r}"
            ) from exc
    raise FrontmatterError(f"`{field_name}` must be an ISO 8601 date, got {type(raw).__name__}")


def _opt_date(raw: Any, field_name: str) -> date | None:
    if raw is None:
        return None
    return _require_date(raw, field_name)


def _list_of_str(raw: Any, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise FrontmatterError(
            f"`{field_name}` must be a list of strings, got {type(raw).__name__}"
        )
    out: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise FrontmatterError(
                f"`{field_name}[{i}]` must be a string, got {type(item).__name__}"
            )
        out.append(item)
    return tuple(out)
