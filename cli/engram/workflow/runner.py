"""Spine execution runtime (SPEC §5.3).

Runs a workflow's spine for one of the three declared languages and
returns a normalized :class:`SpineOutcome`. The minimum valid spine
output is ``{"status": "success"|"failure", "metrics": {...}}``.

- ``python3``: imported via importlib and called as ``main(inputs)`` —
  not exec'd as a subprocess (SPEC §5.3).
- ``bash``: ``inputs`` JSON piped to stdin; output JSON read from
  stdout; exit 0=success / 1=failure / 2=blocked.
- ``toml``: declarative ``[[step]]`` list executed in order (bash steps
  run via subprocess; note steps are logged).

Spine code is user-authored and trusted by definition (the user wrote
the workflow). Side effects must be declared in frontmatter; the CLI
prompts before running a spine that declares any.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram.core.journal import append_event
from engram.workflow.format import WorkflowFrontmatter

__all__ = [
    "DEFAULT_SPINE_TIMEOUT_SECONDS",
    "SpineError",
    "SpineOutcome",
    "record_run",
    "run_spine",
]

DEFAULT_SPINE_TIMEOUT_SECONDS = 120.0


class SpineError(RuntimeError):
    """Raised when a spine cannot be invoked (missing file, bad lang)."""


@dataclass(frozen=True, slots=True)
class SpineOutcome:
    """Normalized result of one spine invocation."""

    status: str  # "success" | "failure" | "blocked"
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    trace: tuple[str, ...] = ()
    failure_mode: str | None = None
    exception: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "success"


def _normalize_output(obj: Any) -> SpineOutcome:
    """Coerce a spine's raw return/stdout into a SpineOutcome."""
    if not isinstance(obj, dict):
        return SpineOutcome(
            status="failure",
            exception=f"spine output is not a JSON object: {type(obj).__name__}",
        )
    status = obj.get("status")
    if status not in {"success", "failure", "blocked"}:
        return SpineOutcome(
            status="failure",
            exception=f"spine output 'status' must be success/failure/blocked, got {status!r}",
            raw=obj,
        )
    metrics = obj.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    artifacts = obj.get("artifacts", [])
    trace = obj.get("trace", [])
    return SpineOutcome(
        status=str(status),
        metrics=dict(metrics),
        artifacts=tuple(str(a) for a in artifacts) if isinstance(artifacts, list) else (),
        trace=tuple(str(t) for t in trace) if isinstance(trace, list) else (),
        failure_mode=(None if obj.get("failure_mode") is None else str(obj["failure_mode"])),
        raw=obj,
    )


def _run_python_spine(spine_path: Path, inputs: dict[str, Any]) -> SpineOutcome:
    module_name = f"_engram_spine_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, spine_path)
    if spec is None or spec.loader is None:
        raise SpineError(f"cannot load python spine at {spine_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            return SpineOutcome(status="failure", exception=f"spine import failed: {exc!r}")
        main = getattr(module, "main", None)
        if not callable(main):
            return SpineOutcome(
                status="failure", exception="python spine has no callable main(inputs)"
            )
        try:
            result = main(dict(inputs))
        except Exception as exc:
            return SpineOutcome(status="failure", exception=f"{type(exc).__name__}: {exc}")
        return _normalize_output(result)
    finally:
        sys.modules.pop(module_name, None)


def _run_bash_spine(
    spine_path: Path, inputs: dict[str, Any], *, timeout: float
) -> SpineOutcome:
    try:
        proc = subprocess.run(
            ["bash", str(spine_path)],
            input=json.dumps(inputs),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SpineError(f"bash not available to run {spine_path}: {exc}") from exc
    except subprocess.TimeoutExpired:
        return SpineOutcome(status="failure", exception=f"spine timed out after {timeout}s")
    # SPEC §5.3: the exit code determines the primary status; the JSON
    # body provides metric values only. The body's own ``status`` never
    # overrides a non-zero exit (a spine that exits 1 but prints
    # status=success is a failure).
    exit_status = {0: "success", 1: "failure", 2: "blocked"}.get(proc.returncode, "failure")
    parsed: dict[str, Any] = {}
    out = proc.stdout.strip()
    if out:
        try:
            loaded = json.loads(out)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = {}
    return _normalize_output({**parsed, "status": exit_status})


def _run_toml_spine(
    spine_path: Path, inputs: dict[str, Any], *, timeout: float
) -> SpineOutcome:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover — Py 3.11+ everywhere we ship
        import tomli as tomllib

    from engram.workflow.format import MAX_AUX_FILE_BYTES, WorkflowFormatError, _read_text_capped

    try:
        text = _read_text_capped(spine_path, cap=MAX_AUX_FILE_BYTES)
        spec = tomllib.loads(text)
    except (WorkflowFormatError, tomllib.TOMLDecodeError) as exc:
        return SpineOutcome(status="failure", exception=f"cannot parse toml spine: {exc}")
    steps = spec.get("step", [])
    if not isinstance(steps, list):
        return SpineOutcome(status="failure", exception="toml spine 'step' must be a list")
    trace: list[str] = []
    steps_run = 0
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id", f"step-{i + 1}"))
        steps_run += 1
        if "note" in step:
            trace.append(f"{sid}: {step['note']}")
            continue
        if "bash" in step:
            try:
                proc = subprocess.run(
                    ["bash", "-c", str(step["bash"])],
                    input=json.dumps(inputs),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                return SpineOutcome(
                    status="failure",
                    exception=f"toml step {sid} failed: {exc}",
                    trace=tuple(trace),
                    metrics={"steps_run": steps_run},
                )
            trace.append(f"{sid}: exit {proc.returncode}")
            if proc.returncode != 0:
                return SpineOutcome(
                    status="failure",
                    failure_mode=f"step_{sid}_failed",
                    trace=tuple(trace),
                    metrics={"steps_run": steps_run},
                )
    return SpineOutcome(status="success", trace=tuple(trace), metrics={"steps_run": steps_run})


def run_spine(
    workflow_dir: Path,
    fm: WorkflowFrontmatter,
    inputs: dict[str, Any],
    *,
    timeout: float = DEFAULT_SPINE_TIMEOUT_SECONDS,
) -> SpineOutcome:
    """Invoke the workflow's spine and return a normalized outcome.

    Raises :class:`SpineError` only for unrecoverable setup problems
    (missing spine file, unknown language). A spine that runs but fails
    returns ``status='failure'`` rather than raising.
    """
    spine_path = workflow_dir / fm.spine_entry
    if not spine_path.is_file():
        raise SpineError(f"spine entry {fm.spine_entry} not found in {workflow_dir}")
    if fm.spine_lang == "python3":
        return _run_python_spine(spine_path, inputs)
    if fm.spine_lang == "bash":
        return _run_bash_spine(spine_path, inputs, timeout=timeout)
    if fm.spine_lang == "toml":
        return _run_toml_spine(spine_path, inputs, timeout=timeout)
    raise SpineError(f"unknown spine_lang {fm.spine_lang!r}")


def record_run(
    workflow_dir: Path,
    inputs: dict[str, Any],
    outcome: SpineOutcome,
    *,
    now: datetime | None = None,
) -> None:
    """Append one run record to ``journal/runs.jsonl`` (SPEC §5.1)."""
    import hashlib

    stamp = (now or datetime.now(tz=timezone.utc)).isoformat(timespec="milliseconds")
    inputs_hash = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    append_event(
        workflow_dir / "journal" / "runs.jsonl",
        {
            "t": stamp,
            "inputs_hash": inputs_hash,
            "status": outcome.status,
            "metrics": outcome.metrics,
            "failure_mode": outcome.failure_mode,
        },
    )
