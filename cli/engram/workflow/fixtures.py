"""Fixture harness (SPEC §5.4).

Runs every ``fixtures/*.yaml`` case through the spine and evaluates its
assertions. ``engram workflow test`` drives this; a workflow with no
passing fixture cannot leave ``draft`` (SPEC §5.7).
"""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram.core.fs import write_atomic
from engram.workflow.format import (
    FixtureAssertion,
    FixtureCase,
    WorkflowFormatError,
    WorkflowFrontmatter,
    parse_fixture,
)
from engram.workflow.runner import SpineError, SpineOutcome, run_spine

__all__ = [
    "AssertionResult",
    "FixtureResult",
    "evaluate_assertions",
    "load_fixtures",
    "run_fixtures",
]

_OPS = {
    "le": operator.le,
    "ge": operator.ge,
    "eq": operator.eq,
    "lt": operator.lt,
    "gt": operator.gt,
}


@dataclass(frozen=True, slots=True)
class AssertionResult:
    type: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class FixtureResult:
    fixture_name: str
    passed: bool
    spine_status: str
    assertions: tuple[AssertionResult, ...]
    metrics: dict[str, Any]


def _eval_metric_threshold(a: FixtureAssertion, outcome: SpineOutcome) -> AssertionResult:
    if a.metric is None or a.op is None:
        return AssertionResult("metric_threshold", False, "missing metric/op")
    if a.metric not in outcome.metrics:
        return AssertionResult(
            "metric_threshold", False, f"metric {a.metric!r} not emitted by spine"
        )
    actual = outcome.metrics[a.metric]
    try:
        ok = _OPS[a.op](actual, a.value)
    except (TypeError, KeyError) as exc:
        return AssertionResult("metric_threshold", False, f"comparison error: {exc}")
    return AssertionResult(
        "metric_threshold",
        bool(ok),
        f"{a.metric}={actual} {a.op} {a.value}",
    )


def evaluate_assertions(
    outcome: SpineOutcome, assertions: tuple[FixtureAssertion, ...]
) -> list[AssertionResult]:
    """Evaluate every assertion against a spine outcome (SPEC §5.4)."""
    results: list[AssertionResult] = []
    for a in assertions:
        if a.type == "metric_threshold":
            results.append(_eval_metric_threshold(a, outcome))
        elif a.type == "no_exception":
            results.append(
                AssertionResult(
                    "no_exception",
                    outcome.exception is None,
                    outcome.exception or "no exception",
                )
            )
        elif a.type == "status_equals":
            results.append(
                AssertionResult(
                    "status_equals",
                    outcome.status == a.value,
                    f"status={outcome.status} expected={a.value}",
                )
            )
        elif a.type == "no_dirty_state":
            # Workflow-defined: the spine signals dirtiness via a truthy
            # ``dirty_state`` field in its output; absent => clean.
            dirty = bool(outcome.raw.get("dirty_state", False))
            results.append(
                AssertionResult("no_dirty_state", not dirty, a.description or "clean post-run")
            )
        else:  # pragma: no cover — parser already rejects unknown types
            results.append(AssertionResult(a.type, False, "unknown assertion type"))
    return results


def load_fixtures(workflow_dir: Path) -> list[FixtureCase]:
    """Load and parse every ``fixtures/*.yaml`` case, sorted by filename."""
    fdir = workflow_dir / "fixtures"
    if not fdir.is_dir():
        return []
    cases: list[FixtureCase] = []
    for path in sorted(fdir.glob("*.yaml")):
        if not path.is_file() or path.is_symlink():
            continue
        cases.append(parse_fixture(path))
    return cases


def _outcome_tsv_path(workflow_dir: Path) -> Path:
    current = workflow_dir / "rev" / "current"
    base = current if current.exists() else workflow_dir
    return base / "outcome.tsv"


def run_fixtures(
    workflow_dir: Path,
    fm: WorkflowFrontmatter,
    *,
    record: bool = True,
    now: datetime | None = None,
) -> list[FixtureResult]:
    """Run all fixtures through the spine; optionally append outcome.tsv.

    Raises :class:`WorkflowFormatError` if a fixture is malformed (so the
    caller can surface it), but a spine that merely fails its assertions
    yields a ``FixtureResult`` with ``passed=False``.
    """
    cases = load_fixtures(workflow_dir)
    if not cases:
        raise WorkflowFormatError(f"no fixtures under {workflow_dir / 'fixtures'}")
    results: list[FixtureResult] = []
    tsv_rows: list[str] = []
    stamp = (now or datetime.now(tz=timezone.utc)).isoformat(timespec="seconds")
    for case in cases:
        try:
            outcome = run_spine(workflow_dir, fm, case.inputs)
        except SpineError as exc:
            outcome = SpineOutcome(status="failure", exception=str(exc))
        ass_results = evaluate_assertions(outcome, case.assertions)
        # A fixture passes when every assertion passes AND, if it declared
        # an expected status, the spine matched it.
        status_ok = case.expected_status is None or outcome.status == case.expected_status
        passed = status_ok and all(r.passed for r in ass_results)
        results.append(
            FixtureResult(
                fixture_name=case.name,
                passed=passed,
                spine_status=outcome.status,
                assertions=tuple(ass_results),
                metrics=outcome.metrics,
            )
        )
        tsv_rows.append(
            "\t".join(
                [
                    stamp,
                    _tsv_cell(case.name),
                    "pass" if passed else "fail",
                    # JSON-encode the spine-controlled metrics so a metric
                    # key/value containing a tab or newline cannot inject
                    # extra columns/rows into the append-only log.
                    _tsv_cell(json.dumps(outcome.metrics, sort_keys=True, default=str)),
                ]
            )
        )
    if record:
        _append_outcome_tsv(_outcome_tsv_path(workflow_dir), tsv_rows)
    return results


def _tsv_cell(value: str) -> str:
    """Neutralize tab/newline so a value stays in one TSV column."""
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _append_outcome_tsv(path: Path, rows: list[str]) -> None:
    """Append rows to ``outcome.tsv`` (append-only within a revision)."""
    existing = ""
    if path.exists() and not path.is_symlink():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
    write_atomic(path, existing + "\n".join(rows) + "\n")
