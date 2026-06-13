"""Revision lifecycle + scaffolding (SPEC §5.1 / §5.6).

- :func:`scaffold_workflow` creates a complete, immediately-runnable
  Workflow directory (workflow.md + spine + 2 fixtures + metrics.yaml +
  rev/r1 + current symlink + journal).
- :func:`snapshot_revision` copies the working copy into a new
  ``rev/rN/`` (used by ``workflow revise`` and, later, autolearn).
- :func:`rollback_to` restores a prior revision's files to the working
  copy and re-points ``current``. No revision is ever deleted (SPEC §5.6).
"""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

from engram.core.fs import atomic_symlink, write_atomic
from engram.workflow.format import SPINE_LANGS
from engram.workflow.paths import validate_workflow_name, workflow_dir

__all__ = [
    "WorkflowExistsError",
    "WorkflowRevError",
    "current_revision",
    "list_revisions",
    "rollback_to",
    "scaffold_workflow",
    "snapshot_revision",
]

_REV_RE = re.compile(r"^r(\d+)$")
_SPINE_EXT = {"python3": "spine.py", "bash": "spine.sh", "toml": "spine.toml"}

# Files/dirs that make up the working copy + a revision snapshot.
_SNAPSHOT_MEMBERS = ("workflow.md", "fixtures", "metrics.yaml", "outcome.tsv")


class WorkflowRevError(RuntimeError):
    """Raised for revision-management failures (bad rev id, etc.)."""


class WorkflowExistsError(WorkflowRevError):
    """Raised when scaffolding a workflow whose directory already exists."""


# ----------------------------------------------------------------------
# Scaffolding templates
# ----------------------------------------------------------------------

_PY_SPINE = '''\
"""Spine for the {name} workflow (SPEC §5.3).

Replace the body with real logic. Inputs are validated against
inputs_schema (if declared) before this call; the return value is
validated against outputs_schema afterward.
"""


def main(inputs: dict) -> dict:
    steps = int(inputs.get("steps", 1))
    return {{
        "status": "success",
        "metrics": {{"steps_run": steps}},
        "trace": [f"ran {{steps}} step(s)"],
    }}
'''

_BASH_SPINE = '''\
#!/usr/bin/env bash
# Spine for the {name} workflow (SPEC §5.3).
# Reads JSON inputs from stdin, emits JSON to stdout.
# exit 0 = success, 1 = failure, 2 = blocked.
set -euo pipefail
inputs=$(cat)
echo '{{"status":"success","metrics":{{"steps_run":1}}}}'
'''

_TOML_SPINE = '''\
# Declarative spine for the {name} workflow (SPEC §5.3).
# Each [[step]] runs in order. Use `bash` for commands, `note` to document.

[[step]]
id = "step-1"
note = "Describe the first step, then add a bash field to make it run."
'''

_METRICS = """\
metrics:
  - name: steps_run
    aggregation: sum
    unit: count
    source: outcome_field
    field: metrics.steps_run

primary: steps_run

ratchet_rule:
  direction: maximize
  tolerance: 0.02

complexity_budget:
  max_lines_factor: 1.5
"""

_SUCCESS_FIXTURE = """\
name: baseline success
inputs:
  steps: 1
expected:
  status: success
assertions:
  - type: status_equals
    value: success
  - type: no_exception
"""

_FAILURE_FIXTURE = """\
name: baseline failure expectation
inputs:
  steps: 0
expected:
  status: success
assertions:
  - type: metric_threshold
    metric: steps_run
    op: ge
    value: 0
"""


def _workflow_md(name: str, *, scope: str, spine_lang: str, description: str) -> str:
    today = date.today().isoformat()
    spine_entry = _SPINE_EXT[spine_lang]
    return f"""\
---
name: {name}
description: {description}
type: workflow
scope: {scope}
spine_lang: {spine_lang}
spine_entry: {spine_entry}
metric_primary: steps_run
lifecycle_state: draft
created: {today}
updated: {today}
---

## Purpose

What problem this workflow solves, and why it is a Workflow rather than a
Memory (it has steps that execute with a measurable outcome).

## When to use

Specific trigger conditions — what context signals indicate this
workflow is relevant.

## Expected outcome

Success criteria expressed in terms of `steps_run`; what the caller
observes when the spine returns `status: success`.

## Failure modes

Known failure patterns and their escape hatches; what to do when the
spine returns `status: failure`.

## Why this approach

Design rationale — what the spine encodes and why. This section is
load-bearing for the autolearn engine: it records what must not be
mutated away.
"""


def scaffold_workflow(
    project_root: Path,
    name: str,
    *,
    spine_lang: str = "python3",
    scope: str = "project",
    description: str = "Describe what this workflow does (<=150 chars).",
) -> Path:
    """Create a complete, runnable Workflow directory; return its path."""
    name = validate_workflow_name(name)
    if spine_lang not in SPINE_LANGS:
        raise WorkflowRevError(
            f"invalid spine_lang {spine_lang!r}; expected one of {SPINE_LANGS}"
        )
    wdir = workflow_dir(project_root, name, scope=scope)
    if wdir.exists():
        raise WorkflowExistsError(f"workflow {name!r} already exists at {wdir}")

    (wdir / "fixtures").mkdir(parents=True, exist_ok=True)
    (wdir / "journal").mkdir(parents=True, exist_ok=True)

    write_atomic(wdir / "workflow.md", _workflow_md(
        name, scope=scope, spine_lang=spine_lang, description=description
    ))
    spine_tmpl = {"python3": _PY_SPINE, "bash": _BASH_SPINE, "toml": _TOML_SPINE}[spine_lang]
    write_atomic(wdir / _SPINE_EXT[spine_lang], spine_tmpl.format(name=name))
    write_atomic(wdir / "metrics.yaml", _METRICS)
    write_atomic(wdir / "fixtures" / "success-case.yaml", _SUCCESS_FIXTURE)
    write_atomic(wdir / "fixtures" / "failure-case.yaml", _FAILURE_FIXTURE)

    snapshot_revision(wdir, spine_lang=spine_lang)
    return wdir


# ----------------------------------------------------------------------
# Revision management
# ----------------------------------------------------------------------


def list_revisions(workflow_dir: Path) -> list[str]:
    """Return revision ids (``r1``, ``r2``, ...) sorted ascending by index."""
    rev_root = workflow_dir / "rev"
    if not rev_root.is_dir():
        return []
    revs: list[tuple[int, str]] = []
    for child in rev_root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        m = _REV_RE.match(child.name)
        if m:
            revs.append((int(m.group(1)), child.name))
    return [name for _, name in sorted(revs)]


def current_revision(workflow_dir: Path) -> str | None:
    """Return the revision id ``current`` points at, or None.

    Security: a shared/pool workflow dir could plant ``rev/current`` as a
    symlink pointing outside the store. We resolve it and only accept a
    target that lives directly under this workflow's ``rev/`` and matches
    the ``rN`` pattern; anything else reads as "no current revision".
    """
    rev_root = (workflow_dir / "rev").resolve()
    link = workflow_dir / "rev" / "current"
    if not link.is_symlink():
        return None
    target = link.resolve()
    if target.parent != rev_root or not _REV_RE.match(target.name):
        return None
    return target.name


def _next_rev_id(workflow_dir: Path) -> str:
    revs = list_revisions(workflow_dir)
    if not revs:
        return "r1"
    highest = max(int(_REV_RE.match(r).group(1)) for r in revs)  # type: ignore[union-attr]
    return f"r{highest + 1}"


def _spine_entry_for(workflow_dir: Path, spine_lang: str | None) -> str:
    if spine_lang is not None:
        return _SPINE_EXT[spine_lang]
    # Infer from whichever spine file is present in the working copy.
    for entry in _SPINE_EXT.values():
        if (workflow_dir / entry).is_file():
            return entry
    raise WorkflowRevError(f"no spine file found in {workflow_dir}")


def snapshot_revision(workflow_dir: Path, *, spine_lang: str | None = None) -> str:
    """Snapshot the working copy into a new ``rev/rN/``; re-point current."""
    rev_id = _next_rev_id(workflow_dir)
    rev_path = workflow_dir / "rev" / rev_id
    rev_path.mkdir(parents=True, exist_ok=True)

    # Security: never copy *through* a symlink — a planted symlinked
    # working-copy member could pull external content into a revision
    # (or be followed on a later rollback). Skip any symlinked source.
    spine_entry = _spine_entry_for(workflow_dir, spine_lang)
    src_spine = workflow_dir / spine_entry
    if src_spine.is_file() and not src_spine.is_symlink():
        shutil.copy2(src_spine, rev_path / spine_entry)
    for member in _SNAPSHOT_MEMBERS:
        src = workflow_dir / member
        if member == "outcome.tsv":
            continue  # outcome.tsv is created per-rev by the fixture harness
        if src.is_symlink():
            continue
        if src.is_dir():
            shutil.copytree(src, rev_path / member, dirs_exist_ok=True, symlinks=True)
        elif src.is_file():
            shutil.copy2(src, rev_path / member)
    # Fresh empty outcome.tsv for the new revision.
    if not (rev_path / "outcome.tsv").exists():
        write_atomic(rev_path / "outcome.tsv", "")
    atomic_symlink(rev_id, workflow_dir / "rev" / "current")
    return rev_id


def rollback_to(workflow_dir: Path, rev_id: str) -> None:
    """Restore ``rev/<rev_id>/`` to the working copy and re-point current.

    No revision directory is deleted (SPEC §5.6 rule 6). After rollback
    ``current`` points at ``rev_id`` again; a subsequent ``workflow test``
    appends to that revision's ``outcome.tsv`` (rows accumulate across
    passes, SPEC §5.6 rule 3).

    Security: symlinked members inside the revision are skipped, never
    followed — a planted ``rev/rN/metrics.yaml -> /etc/...`` cannot pull
    an out-of-store file into the working copy on a shared workflow dir.
    """
    if not _REV_RE.match(rev_id):
        raise WorkflowRevError(f"invalid revision id {rev_id!r}")
    rev_path = workflow_dir / "rev" / rev_id
    if not rev_path.is_dir():
        raise WorkflowRevError(f"revision {rev_id} does not exist in {workflow_dir}")
    # Restore snapshot members + the spine file to the working copy.
    for child in rev_path.iterdir():
        if child.name == "outcome.tsv" or child.is_symlink():
            continue
        dest = workflow_dir / child.name
        if child.is_dir():
            if dest.exists() and not dest.is_symlink():
                shutil.rmtree(dest)
            elif dest.is_symlink():
                dest.unlink()
            shutil.copytree(child, dest, symlinks=True)
        else:
            shutil.copy2(child, dest)
    atomic_symlink(rev_id, workflow_dir / "rev" / "current")
