"""``engram workflow`` — the Workflow asset class CLI (SPEC §5).

Subcommands:

- ``add``      scaffold a new runnable Workflow.
- ``list``     list workflows under the project with lifecycle state.
- ``read``     print a workflow's doc (text) or frontmatter (json).
- ``validate`` check the on-disk structure is well-formed.
- ``run``      invoke the spine with ``--inputs`` JSON; record the run.
- ``test``     run all fixtures; non-zero exit if any fail.
- ``history``  list revisions + which one ``current`` points at.
- ``revise``   snapshot the working copy into a new revision.
- ``rollback`` restore a prior revision to the working copy.
- ``deprecate`` flip lifecycle_state to deprecated.

Memory reads inside a spine MUST go through ``engram memory read`` (SPEC
§3.3 MUST 2); the runtime does not grant filesystem access to the store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from engram.config_types import GlobalConfig
from engram.core.fs import write_atomic
from engram.workflow.fixtures import run_fixtures
from engram.workflow.format import (
    WorkflowFormatError,
    parse_metrics,
    parse_workflow_file,
    render_workflow_file,
)
from engram.workflow.paths import (
    WORKFLOW_DOC_NAME,
    validate_workflow_name,
    workflow_dir,
    workflows_root,
)
from engram.workflow.rev import (
    WorkflowExistsError,
    WorkflowRevError,
    current_revision,
    list_revisions,
    rollback_to,
    scaffold_workflow,
    snapshot_revision,
)
from engram.workflow.runner import SpineError, record_run, run_spine

__all__ = ["workflow_group"]


def _wdir_or_fail(project: Path, name: str) -> Path:
    try:
        name = validate_workflow_name(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    wdir = workflow_dir(project, name)
    if not (wdir / WORKFLOW_DOC_NAME).is_file():
        raise click.ClickException(
            f"no workflow named {name!r} under {workflows_root(project)}; "
            "run `engram workflow list`."
        )
    return wdir


@click.group("workflow", help="Workflow asset class — executable procedures (SPEC §5).")
def workflow_group() -> None:
    pass


# ----------------------------------------------------------------------
# add
# ----------------------------------------------------------------------


@workflow_group.command("add", help="Scaffold a new runnable Workflow.")
@click.argument("name")
@click.option(
    "--lang",
    "spine_lang",
    type=click.Choice(["python3", "bash", "toml"]),
    default="python3",
    show_default=True,
)
@click.option(
    "--scope",
    type=click.Choice(["project", "user"]),
    default="project",
    show_default=True,
    help="team/org/pool need a scope name; create those under their root directly.",
)
@click.option("--description", default="Describe what this workflow does (<=150 chars).")
@click.pass_obj
def add_cmd(cfg: GlobalConfig, name: str, spine_lang: str, scope: str, description: str) -> None:
    project = cfg.resolve_project_root()
    try:
        wdir = scaffold_workflow(
            project, name, spine_lang=spine_lang, scope=scope, description=description
        )
    except WorkflowExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    except (WorkflowRevError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"created workflow {name} ({spine_lang}) at {wdir}")
    click.echo(f"  edit {wdir / 'workflow.md'} and {wdir / 'fixtures'}, then:")
    click.echo(f"  engram workflow test {name}")


# ----------------------------------------------------------------------
# list
# ----------------------------------------------------------------------


@workflow_group.command("list", help="List workflows with lifecycle state.")
@click.pass_obj
def list_cmd(cfg: GlobalConfig) -> None:
    project = cfg.resolve_project_root()
    root = workflows_root(project)
    rows: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            doc = child / WORKFLOW_DOC_NAME
            if not doc.is_file() or child.is_symlink():
                continue
            try:
                fm, _ = parse_workflow_file(doc)
            except WorkflowFormatError:
                continue
            rows.append(
                {
                    "name": child.name,
                    "lifecycle_state": fm.lifecycle_state,
                    "spine_lang": fm.spine_lang,
                    "description": fm.description,
                    "current_rev": current_revision(child),
                }
            )
    if cfg.output_format == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        click.echo("(no workflows; create one with `engram workflow add <name>`)")
        return
    for row in rows:
        click.echo(f"  {row['name']}  [{row['lifecycle_state']}/{row['spine_lang']}]")
        click.echo(f"    {row['description']}")


# ----------------------------------------------------------------------
# read
# ----------------------------------------------------------------------


@workflow_group.command("read", help="Print a workflow doc (text) or frontmatter (json).")
@click.argument("name")
@click.pass_obj
def read_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    fm, _ = parse_workflow_file(wdir / WORKFLOW_DOC_NAME)
    if cfg.output_format == "json":
        click.echo(json.dumps(fm.to_yaml_dict(), indent=2, ensure_ascii=False))
        return
    click.echo((wdir / WORKFLOW_DOC_NAME).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# validate
# ----------------------------------------------------------------------


@workflow_group.command("validate", help="Check the workflow's on-disk structure.")
@click.argument("name")
@click.pass_obj
def validate_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        fm, _ = parse_workflow_file(wdir / WORKFLOW_DOC_NAME)
    except WorkflowFormatError as exc:
        raise click.ClickException(f"workflow.md invalid: {exc}") from exc

    if not (wdir / fm.spine_entry).is_file():
        errors.append(f"spine_entry {fm.spine_entry} not found")
    try:
        metrics = parse_metrics(wdir / "metrics.yaml")
        if metrics.primary != fm.metric_primary:
            errors.append(
                f"metric_primary {fm.metric_primary!r} != metrics.yaml primary {metrics.primary!r}"
            )
    except WorkflowFormatError as exc:
        errors.append(f"metrics.yaml: {exc}")

    fdir = wdir / "fixtures"
    fixtures = sorted(fdir.glob("*.yaml")) if fdir.is_dir() else []
    if not any("success" in p.name for p in fixtures):
        warnings.append("no success-case fixture (SPEC §5.4 requires >=1)")
    if not any("failure" in p.name for p in fixtures):
        warnings.append("no failure-case fixture (SPEC §5.4 requires >=1)")
    if fm.inputs_schema and not (wdir / fm.inputs_schema).is_file():
        warnings.append(f"inputs_schema {fm.inputs_schema} declared but missing")

    payload = {"name": name, "errors": errors, "warnings": warnings, "valid": not errors}
    if cfg.output_format == "json":
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for e in errors:
            click.echo(f"ERROR   {e}")
        for w in warnings:
            click.echo(f"WARN    {w}")
        if not errors:
            click.echo(f"{name}: structure valid" + (" (with warnings)" if warnings else ""))
    if errors:
        raise SystemExit(2)


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------


@workflow_group.command("run", help="Invoke the spine with --inputs JSON.")
@click.argument("name")
@click.option("--inputs", "inputs_json", default="{}", help="JSON object of spine inputs.")
@click.option("--yes", is_flag=True, default=False, help="Skip the side-effects prompt.")
@click.option("--dry-run", is_flag=True, default=False, help="Validate inputs without running.")
@click.pass_obj
def run_cmd(
    cfg: GlobalConfig, name: str, inputs_json: str, yes: bool, dry_run: bool
) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    fm, _ = parse_workflow_file(wdir / WORKFLOW_DOC_NAME)
    try:
        inputs = json.loads(inputs_json)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"--inputs is not valid JSON: {exc}") from exc
    if not isinstance(inputs, dict):
        raise click.ClickException("--inputs must be a JSON object")

    # Minimal required-keys check against inputs_schema (dep-free subset).
    missing = _missing_required(inputs, wdir / fm.inputs_schema if fm.inputs_schema else None)
    if missing:
        raise click.ClickException(f"inputs missing required key(s): {missing}")

    if dry_run:
        click.echo(f"dry-run: inputs valid for {name}; not invoking spine")
        return

    # Side-effects prompt (SPEC §5.2): confirm before running a spine that
    # declares fs_write / network / git_commit etc.
    if fm.side_effects and not yes:
        confirm = click.confirm(
            f"workflow {name} declares side effects {list(fm.side_effects)}; run anyway?",
            default=False,
        )
        if not confirm:
            raise click.ClickException("aborted (side effects not confirmed)")

    try:
        outcome = run_spine(wdir, fm, inputs)
    except SpineError as exc:
        raise click.ClickException(str(exc)) from exc
    record_run(wdir, inputs, outcome)

    payload = {
        "status": outcome.status,
        "metrics": outcome.metrics,
        "failure_mode": outcome.failure_mode,
        "exception": outcome.exception,
        "trace": list(outcome.trace),
    }
    if cfg.output_format == "json":
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(f"status: {outcome.status}")
        if outcome.metrics:
            click.echo(f"metrics: {outcome.metrics}")
        if outcome.exception:
            click.echo(f"error: {outcome.exception}")
    if outcome.status != "success":
        raise SystemExit(1)


def _missing_required(inputs: dict[str, Any], schema_path: Path | None) -> list[str]:
    """Return required keys (per a minimal JSON-Schema subset) absent from inputs."""
    if schema_path is None or not schema_path.is_file() or schema_path.is_symlink():
        return []
    from engram.workflow.format import MAX_AUX_FILE_BYTES, WorkflowFormatError, _read_text_capped

    try:
        schema = json.loads(_read_text_capped(schema_path, cap=MAX_AUX_FILE_BYTES))
    except (WorkflowFormatError, json.JSONDecodeError):
        return []
    required = schema.get("required") if isinstance(schema, dict) else None
    if not isinstance(required, list):
        return []
    return [k for k in required if k not in inputs]


# ----------------------------------------------------------------------
# test
# ----------------------------------------------------------------------


@workflow_group.command("test", help="Run all fixtures; non-zero exit if any fail.")
@click.argument("name")
@click.pass_obj
def test_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    fm, _ = parse_workflow_file(wdir / WORKFLOW_DOC_NAME)
    try:
        results = run_fixtures(wdir, fm)
    except (WorkflowFormatError, SpineError) as exc:
        raise click.ClickException(str(exc)) from exc

    passed = sum(1 for r in results if r.passed)
    payload = {
        "name": name,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "fixtures": [
            {
                "name": r.fixture_name,
                "passed": r.passed,
                "spine_status": r.spine_status,
                "assertions": [
                    {"type": a.type, "passed": a.passed, "detail": a.detail}
                    for a in r.assertions
                ],
            }
            for r in results
        ],
    }
    if cfg.output_format == "json":
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            click.echo(f"  [{mark}] {r.fixture_name}  (status={r.spine_status})")
            for a in r.assertions:
                if not a.passed:
                    click.echo(f"          - {a.type}: {a.detail}")
        click.echo(f"{passed}/{len(results)} fixtures passed")
    if passed != len(results):
        raise SystemExit(1)


# ----------------------------------------------------------------------
# history / revise / rollback
# ----------------------------------------------------------------------


@workflow_group.command("history", help="List revisions and the active one.")
@click.argument("name")
@click.pass_obj
def history_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    revs = list_revisions(wdir)
    current = current_revision(wdir)
    if cfg.output_format == "json":
        click.echo(json.dumps({"revisions": revs, "current": current}, indent=2))
        return
    if not revs:
        click.echo("(no revisions)")
        return
    for rev in revs:
        marker = " <- current" if rev == current else ""
        click.echo(f"  {rev}{marker}")


@workflow_group.command("revise", help="Snapshot the working copy into a new revision.")
@click.argument("name")
@click.pass_obj
def revise_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    try:
        rev_id = snapshot_revision(wdir)
    except WorkflowRevError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"snapshotted working copy -> rev/{rev_id} (current now {rev_id})")


@workflow_group.command("rollback", help="Restore a prior revision to the working copy.")
@click.argument("name")
@click.option("--to", "rev_id", required=True, metavar="rN")
@click.pass_obj
def rollback_cmd(cfg: GlobalConfig, name: str, rev_id: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    try:
        rollback_to(wdir, rev_id)
    except WorkflowRevError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"rolled back {name} working copy to {rev_id} (current now {rev_id})")


@workflow_group.command("deprecate", help="Flip lifecycle_state to deprecated.")
@click.argument("name")
@click.pass_obj
def deprecate_cmd(cfg: GlobalConfig, name: str) -> None:
    project = cfg.resolve_project_root()
    wdir = _wdir_or_fail(project, name)
    doc = wdir / WORKFLOW_DOC_NAME
    fm, body = parse_workflow_file(doc)
    from dataclasses import replace

    updated = replace(fm, lifecycle_state="deprecated")
    write_atomic(doc, render_workflow_file(updated, body))
    click.echo(f"{name}: lifecycle_state -> deprecated")
