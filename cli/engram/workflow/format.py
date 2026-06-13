"""On-disk format contracts for Workflow assets (SPEC §5.2 / §5.4 / §5.5).

Three parsers/renderers:

- ``workflow.md`` frontmatter + body (:class:`WorkflowFrontmatter`)
- ``metrics.yaml`` (:class:`MetricsConfig`)
- ``fixtures/*.yaml`` (:class:`FixtureCase`)

All parsers raise :class:`WorkflowFormatError` on malformed input and
preserve unknown frontmatter fields on rewrite (SPEC §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "SPINE_LANGS",
    "FixtureAssertion",
    "FixtureCase",
    "MetricSpec",
    "MetricsConfig",
    "RatchetRule",
    "WorkflowFormatError",
    "WorkflowFrontmatter",
    "parse_fixture",
    "parse_metrics",
    "parse_workflow_file",
    "render_workflow_file",
]

SPINE_LANGS: frozenset[str] = frozenset({"python3", "bash", "toml"})
_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {"draft", "active", "stable", "deprecated", "archived", "tombstoned"}
)
_SCOPES: frozenset[str] = frozenset({"org", "team", "user", "project", "pool"})

# Hard cap on the workflow.md file: a healthy doc is a few KB. Anything
# above this is malformed/attacker bloat (mirrors session.py F12).
MAX_WORKFLOW_FILE_BYTES = 1 * 1024 * 1024

_FRONTMATTER_DELIM = "---"

_REQUIRED_FM = (
    "name",
    "description",
    "type",
    "scope",
    "spine_lang",
    "spine_entry",
    "metric_primary",
    "lifecycle_state",
)

# Frontmatter keys we model explicitly; everything else (including
# ``expires`` and any future field) falls through to ``extra`` and is
# preserved verbatim on rewrite (SPEC §4.1 / §5.2 MUST-preserve).
_KNOWN_FM = frozenset(
    {
        *_REQUIRED_FM,
        "inputs_schema",
        "outputs_schema",
        "created",
        "updated",
        "tags",
        "references",
        "side_effects",
        "needs_attention",
    }
)

# Aux files (metrics.yaml / fixtures / toml spine) are small by nature; a
# multi-MB sibling is corruption or planted bloat. Bounded reads keep a
# shared/pool workflow dir from OOM-ing the parser (security review).
MAX_AUX_FILE_BYTES = 1 * 1024 * 1024


def _read_text_capped(path: Path, *, cap: int = MAX_AUX_FILE_BYTES) -> str:
    """Read a workflow aux file with a hard byte cap + UTF-8 decode."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(cap + 1)
    except OSError as exc:
        raise WorkflowFormatError(f"cannot read {path}: {exc}") from exc
    if len(raw) > cap:
        raise WorkflowFormatError(f"{path} exceeds {cap}-byte cap")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowFormatError(f"{path} is not valid UTF-8: {exc}") from exc


class WorkflowFormatError(ValueError):
    """Raised when a Workflow on-disk file cannot be parsed/validated."""


@dataclass(frozen=True, slots=True)
class WorkflowFrontmatter:
    """Typed ``workflow.md`` frontmatter (SPEC §5.2)."""

    name: str
    description: str
    scope: str
    spine_lang: str
    spine_entry: str
    metric_primary: str
    lifecycle_state: str = "draft"
    type: str = "workflow"
    inputs_schema: str | None = None
    outputs_schema: str | None = None
    created: str | None = None
    updated: str | None = None
    tags: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    needs_attention: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_yaml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": "workflow",
            "scope": self.scope,
            "spine_lang": self.spine_lang,
            "spine_entry": self.spine_entry,
            "metric_primary": self.metric_primary,
            "lifecycle_state": self.lifecycle_state,
        }
        if self.inputs_schema is not None:
            out["inputs_schema"] = self.inputs_schema
        if self.outputs_schema is not None:
            out["outputs_schema"] = self.outputs_schema
        if self.created is not None:
            out["created"] = self.created
        if self.updated is not None:
            out["updated"] = self.updated
        if self.tags:
            out["tags"] = list(self.tags)
        if self.references:
            out["references"] = list(self.references)
        if self.side_effects:
            out["side_effects"] = list(self.side_effects)
        if self.needs_attention:
            out["needs_attention"] = True
        # Unknown fields preserved verbatim (SPEC §4.1), last so explicit
        # fields always win on a round-trip.
        for key, value in self.extra.items():
            out.setdefault(key, value)
        return out


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    raise WorkflowFormatError(f"expected a string list, got {type(value).__name__}")


def parse_workflow_frontmatter(data: dict[str, Any]) -> WorkflowFrontmatter:
    """Validate a parsed frontmatter mapping into a typed object."""
    if not isinstance(data, dict):
        raise WorkflowFormatError("workflow frontmatter must be a mapping")
    missing = [k for k in _REQUIRED_FM if k not in data]
    if missing:
        raise WorkflowFormatError(f"workflow.md missing required field(s): {missing}")
    if data["type"] != "workflow":
        raise WorkflowFormatError(f"type must be 'workflow', got {data['type']!r}")
    scope = str(data["scope"])
    if scope not in _SCOPES:
        raise WorkflowFormatError(f"invalid scope {scope!r}; expected one of {_SCOPES}")
    spine_lang = str(data["spine_lang"])
    if spine_lang not in SPINE_LANGS:
        raise WorkflowFormatError(
            f"invalid spine_lang {spine_lang!r}; expected one of {SPINE_LANGS}"
        )
    lifecycle = str(data["lifecycle_state"])
    if lifecycle not in _LIFECYCLE_STATES:
        raise WorkflowFormatError(
            f"invalid lifecycle_state {lifecycle!r}; expected one of {_LIFECYCLE_STATES}"
        )
    extra = {k: v for k, v in data.items() if k not in _KNOWN_FM}
    return WorkflowFrontmatter(
        name=str(data["name"]),
        description=str(data["description"]),
        scope=scope,
        spine_lang=spine_lang,
        spine_entry=str(data["spine_entry"]),
        metric_primary=str(data["metric_primary"]),
        lifecycle_state=lifecycle,
        inputs_schema=(None if data.get("inputs_schema") is None else str(data["inputs_schema"])),
        outputs_schema=(
            None if data.get("outputs_schema") is None else str(data["outputs_schema"])
        ),
        created=(None if data.get("created") is None else str(data["created"])),
        updated=(None if data.get("updated") is None else str(data["updated"])),
        tags=_as_str_tuple(data.get("tags")),
        references=_as_str_tuple(data.get("references")),
        side_effects=_as_str_tuple(data.get("side_effects")),
        needs_attention=bool(data.get("needs_attention", False)),
        extra=extra,
    )


def parse_workflow_file(path: Path) -> tuple[WorkflowFrontmatter, str]:
    """Parse ``workflow.md`` -> (frontmatter, body). Body returned verbatim."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_WORKFLOW_FILE_BYTES + 1)
    except OSError as exc:
        raise WorkflowFormatError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_WORKFLOW_FILE_BYTES:
        raise WorkflowFormatError(
            f"{path} exceeds {MAX_WORKFLOW_FILE_BYTES}-byte cap"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowFormatError(f"{path} is not valid UTF-8: {exc}") from exc
    if not text.startswith(_FRONTMATTER_DELIM):
        raise WorkflowFormatError(f"missing leading '---' frontmatter in {path}")
    rest = text[len(_FRONTMATTER_DELIM) :]
    end_idx = rest.find("\n" + _FRONTMATTER_DELIM)
    if end_idx < 0:
        raise WorkflowFormatError(f"missing closing '---' frontmatter in {path}")
    yaml_text = rest[:end_idx].lstrip("\n")
    body_after = rest[end_idx + len("\n" + _FRONTMATTER_DELIM) :]
    if body_after.startswith("\n"):
        body_after = body_after[1:]
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise WorkflowFormatError(f"YAML parse failed for {path}: {exc}") from exc
    return parse_workflow_frontmatter(data), body_after


def render_workflow_file(fm: WorkflowFrontmatter, body: str) -> str:
    """Render (frontmatter, body) back to ``workflow.md`` text."""
    yaml_text = yaml.safe_dump(
        fm.to_yaml_dict(), sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.endswith("\n"):
        body = body + "\n"
    return f"{_FRONTMATTER_DELIM}\n{yaml_text}{_FRONTMATTER_DELIM}\n{body}"


# ----------------------------------------------------------------------
# metrics.yaml (SPEC §5.5)
# ----------------------------------------------------------------------

_AGGREGATIONS: frozenset[str] = frozenset({"p50", "p95", "p99", "mean", "sum", "max", "min"})
_DIRECTIONS: frozenset[str] = frozenset({"minimize", "maximize"})


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    aggregation: str
    unit: str = ""
    source: str = "outcome_field"
    field: str = ""


@dataclass(frozen=True, slots=True)
class RatchetRule:
    direction: str = "minimize"
    tolerance: float = 0.02


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    metrics: tuple[MetricSpec, ...]
    primary: str
    ratchet: RatchetRule = field(default_factory=RatchetRule)
    max_lines_factor: float | None = None

    def metric(self, name: str) -> MetricSpec | None:
        for m in self.metrics:
            if m.name == name:
                return m
        return None


def parse_metrics(path: Path) -> MetricsConfig:
    """Parse ``metrics.yaml`` into a typed config (SPEC §5.5)."""
    try:
        data = yaml.safe_load(_read_text_capped(path)) or {}
    except yaml.YAMLError as exc:
        raise WorkflowFormatError(f"cannot parse metrics.yaml at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowFormatError("metrics.yaml must be a mapping")
    raw_metrics = data.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise WorkflowFormatError("metrics.yaml requires a non-empty 'metrics' list")
    metrics: list[MetricSpec] = []
    for entry in raw_metrics:
        if not isinstance(entry, dict) or "name" not in entry or "aggregation" not in entry:
            raise WorkflowFormatError(f"malformed metric entry: {entry!r}")
        agg = str(entry["aggregation"])
        if agg not in _AGGREGATIONS:
            raise WorkflowFormatError(
                f"invalid aggregation {agg!r}; expected one of {_AGGREGATIONS}"
            )
        metrics.append(
            MetricSpec(
                name=str(entry["name"]),
                aggregation=agg,
                unit=str(entry.get("unit", "")),
                source=str(entry.get("source", "outcome_field")),
                field=str(entry.get("field", "")),
            )
        )
    primary = str(data.get("primary", ""))
    if not primary or all(m.name != primary for m in metrics):
        raise WorkflowFormatError(
            f"metrics.yaml 'primary' {primary!r} must match a metric name"
        )
    ratchet = RatchetRule()
    raw_ratchet = data.get("ratchet_rule")
    if isinstance(raw_ratchet, dict):
        direction = str(raw_ratchet.get("direction", "minimize"))
        if direction not in _DIRECTIONS:
            raise WorkflowFormatError(
                f"invalid ratchet direction {direction!r}; expected one of {_DIRECTIONS}"
            )
        ratchet = RatchetRule(
            direction=direction, tolerance=float(raw_ratchet.get("tolerance", 0.02))
        )
    max_lines_factor: float | None = None
    raw_budget = data.get("complexity_budget")
    if isinstance(raw_budget, dict) and "max_lines_factor" in raw_budget:
        max_lines_factor = float(raw_budget["max_lines_factor"])
    return MetricsConfig(
        metrics=tuple(metrics),
        primary=primary,
        ratchet=ratchet,
        max_lines_factor=max_lines_factor,
    )


# ----------------------------------------------------------------------
# fixtures/*.yaml (SPEC §5.4)
# ----------------------------------------------------------------------

_ASSERTION_TYPES: frozenset[str] = frozenset(
    {"metric_threshold", "no_exception", "status_equals", "no_dirty_state"}
)
_THRESHOLD_OPS: frozenset[str] = frozenset({"le", "ge", "eq", "lt", "gt"})


@dataclass(frozen=True, slots=True)
class FixtureAssertion:
    type: str
    metric: str | None = None
    op: str | None = None
    value: Any = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class FixtureCase:
    name: str
    inputs: dict[str, Any]
    expected_status: str | None
    assertions: tuple[FixtureAssertion, ...]
    source_path: Path | None = None


def parse_fixture(path: Path) -> FixtureCase:
    """Parse a single ``fixtures/*.yaml`` case (SPEC §5.4)."""
    try:
        data = yaml.safe_load(_read_text_capped(path)) or {}
    except yaml.YAMLError as exc:
        raise WorkflowFormatError(f"cannot parse fixture at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowFormatError(f"fixture {path} must be a mapping")
    inputs = data.get("inputs", {})
    if not isinstance(inputs, dict):
        raise WorkflowFormatError(f"fixture {path} 'inputs' must be a mapping")
    expected = data.get("expected")
    expected_status: str | None = None
    if isinstance(expected, dict) and "status" in expected:
        expected_status = str(expected["status"])
    raw_assertions = data.get("assertions", [])
    if not isinstance(raw_assertions, list):
        raise WorkflowFormatError(f"fixture {path} 'assertions' must be a list")
    assertions: list[FixtureAssertion] = []
    for entry in raw_assertions:
        if not isinstance(entry, dict) or "type" not in entry:
            raise WorkflowFormatError(f"fixture {path}: malformed assertion {entry!r}")
        atype = str(entry["type"])
        if atype not in _ASSERTION_TYPES:
            raise WorkflowFormatError(
                f"fixture {path}: unknown assertion type {atype!r}; "
                f"expected one of {_ASSERTION_TYPES}"
            )
        op = entry.get("op")
        if atype == "metric_threshold":
            if entry.get("metric") is None or op is None:
                raise WorkflowFormatError(
                    f"fixture {path}: metric_threshold requires 'metric' and 'op'"
                )
            if str(op) not in _THRESHOLD_OPS:
                raise WorkflowFormatError(
                    f"fixture {path}: invalid op {op!r}; expected one of {_THRESHOLD_OPS}"
                )
        assertions.append(
            FixtureAssertion(
                type=atype,
                metric=(None if entry.get("metric") is None else str(entry["metric"])),
                op=(None if op is None else str(op)),
                value=entry.get("value"),
                description=str(entry.get("description", "")),
            )
        )
    return FixtureCase(
        name=str(data.get("name", path.stem)),
        inputs=inputs,
        expected_status=expected_status,
        assertions=tuple(assertions),
        source_path=path,
    )
