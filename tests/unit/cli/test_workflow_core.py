"""Unit tests for the Workflow asset class core (SPEC §5).

Covers format (workflow.md / metrics.yaml / fixtures), the spine runner
across all three languages, the fixture harness + assertion evaluation,
and the revision lifecycle (scaffold / snapshot / rollback).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engram.workflow.format import (
    WorkflowFormatError,
    parse_fixture,
    parse_metrics,
    parse_workflow_file,
    render_workflow_file,
)
from engram.workflow.fixtures import evaluate_assertions, run_fixtures
from engram.workflow.format import FixtureAssertion
from engram.workflow.paths import validate_workflow_name, workflow_dir
from engram.workflow.rev import (
    WorkflowExistsError,
    WorkflowRevError,
    current_revision,
    list_revisions,
    rollback_to,
    scaffold_workflow,
    snapshot_revision,
)
from engram.workflow.runner import SpineError, SpineOutcome, record_run, run_spine


# ----------------------------------------------------------------------
# paths
# ----------------------------------------------------------------------


def test_validate_workflow_name_accepts_slug() -> None:
    assert validate_workflow_name("git-merge_2") == "git-merge_2"


@pytest.mark.parametrize("bad", ["../escape", "Has Caps", "a/b", ".dot", "-leading"])
def test_validate_workflow_name_rejects_traversal(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_workflow_name(bad)


# ----------------------------------------------------------------------
# scaffold -> a complete, valid, runnable workflow
# ----------------------------------------------------------------------


@pytest.fixture
def scaffolded(tmp_path: Path) -> Path:
    return scaffold_workflow(tmp_path, "demo", spine_lang="python3")


def test_scaffold_creates_full_structure(scaffolded: Path) -> None:
    assert (scaffolded / "workflow.md").is_file()
    assert (scaffolded / "spine.py").is_file()
    assert (scaffolded / "metrics.yaml").is_file()
    assert (scaffolded / "fixtures" / "success-case.yaml").is_file()
    assert (scaffolded / "fixtures" / "failure-case.yaml").is_file()
    assert (scaffolded / "rev" / "r1").is_dir()
    assert (scaffolded / "rev" / "current").is_symlink()
    assert current_revision(scaffolded) == "r1"


def test_scaffold_rejects_duplicate(tmp_path: Path) -> None:
    scaffold_workflow(tmp_path, "demo")
    with pytest.raises(WorkflowExistsError):
        scaffold_workflow(tmp_path, "demo")


def test_scaffold_rejects_bad_lang(tmp_path: Path) -> None:
    with pytest.raises(WorkflowRevError):
        scaffold_workflow(tmp_path, "demo", spine_lang="ruby")


# ----------------------------------------------------------------------
# workflow.md format
# ----------------------------------------------------------------------


def test_workflow_md_round_trips(scaffolded: Path) -> None:
    fm, body = parse_workflow_file(scaffolded / "workflow.md")
    assert fm.type == "workflow"
    assert fm.spine_lang == "python3"
    assert fm.metric_primary == "steps_run"
    rendered = render_workflow_file(fm, body)
    fm2, body2 = parse_workflow_file_from_text(rendered, scaffolded / "workflow.md")
    assert fm2.name == fm.name
    assert body2 == body


def parse_workflow_file_from_text(text: str, path: Path) -> tuple[object, str]:
    path.write_text(text, encoding="utf-8")
    return parse_workflow_file(path)


def test_workflow_md_preserves_unknown_fields(tmp_path: Path) -> None:
    doc = tmp_path / "workflow.md"
    doc.write_text(
        "---\n"
        "name: x\ndescription: d\ntype: workflow\nscope: project\n"
        "spine_lang: bash\nspine_entry: spine.sh\nmetric_primary: m\n"
        "lifecycle_state: draft\ncustom_field: keepme\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    fm, _ = parse_workflow_file(doc)
    assert fm.extra == {"custom_field": "keepme"}
    assert "custom_field: keepme" in render_workflow_file(fm, "body\n")


def test_workflow_md_rejects_missing_required(tmp_path: Path) -> None:
    doc = tmp_path / "workflow.md"
    doc.write_text("---\nname: x\ntype: workflow\n---\nbody\n", encoding="utf-8")
    with pytest.raises(WorkflowFormatError):
        parse_workflow_file(doc)


def test_workflow_md_rejects_bad_spine_lang(tmp_path: Path) -> None:
    doc = tmp_path / "workflow.md"
    doc.write_text(
        "---\nname: x\ndescription: d\ntype: workflow\nscope: project\n"
        "spine_lang: cobol\nspine_entry: s\nmetric_primary: m\nlifecycle_state: draft\n"
        "---\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowFormatError):
        parse_workflow_file(doc)


# ----------------------------------------------------------------------
# metrics.yaml
# ----------------------------------------------------------------------


def test_parse_metrics(scaffolded: Path) -> None:
    mc = parse_metrics(scaffolded / "metrics.yaml")
    assert mc.primary == "steps_run"
    assert mc.ratchet.direction == "maximize"
    assert mc.metric("steps_run") is not None
    assert mc.max_lines_factor == 1.5


def test_parse_metrics_rejects_primary_mismatch(tmp_path: Path) -> None:
    m = tmp_path / "metrics.yaml"
    m.write_text(
        "metrics:\n  - name: a\n    aggregation: sum\nprimary: nonexistent\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowFormatError):
        parse_metrics(m)


def test_parse_metrics_rejects_bad_aggregation(tmp_path: Path) -> None:
    m = tmp_path / "metrics.yaml"
    m.write_text("metrics:\n  - name: a\n    aggregation: wat\nprimary: a\n", encoding="utf-8")
    with pytest.raises(WorkflowFormatError):
        parse_metrics(m)


# ----------------------------------------------------------------------
# fixtures format + assertion evaluation
# ----------------------------------------------------------------------


def test_parse_fixture(scaffolded: Path) -> None:
    fc = parse_fixture(scaffolded / "fixtures" / "success-case.yaml")
    assert fc.expected_status == "success"
    assert any(a.type == "status_equals" for a in fc.assertions)


def test_parse_fixture_rejects_unknown_assertion(tmp_path: Path) -> None:
    f = tmp_path / "f.yaml"
    f.write_text("name: x\ninputs: {}\nassertions:\n  - type: telepathy\n", encoding="utf-8")
    with pytest.raises(WorkflowFormatError):
        parse_fixture(f)


def test_parse_fixture_metric_threshold_requires_metric_op(tmp_path: Path) -> None:
    f = tmp_path / "f.yaml"
    f.write_text(
        "name: x\ninputs: {}\nassertions:\n  - type: metric_threshold\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowFormatError):
        parse_fixture(f)


def test_evaluate_assertions_all_types() -> None:
    outcome = SpineOutcome(status="success", metrics={"t": 5})
    asserts = (
        FixtureAssertion(type="no_exception"),
        FixtureAssertion(type="status_equals", value="success"),
        FixtureAssertion(type="metric_threshold", metric="t", op="le", value=10),
        FixtureAssertion(type="no_dirty_state"),
    )
    results = evaluate_assertions(outcome, asserts)
    assert all(r.passed for r in results)


def test_evaluate_metric_threshold_fails_when_metric_absent() -> None:
    outcome = SpineOutcome(status="success", metrics={})
    a = (FixtureAssertion(type="metric_threshold", metric="missing", op="le", value=1),)
    assert evaluate_assertions(outcome, a)[0].passed is False


def test_evaluate_no_dirty_state_detects_dirty() -> None:
    outcome = SpineOutcome(status="success", raw={"dirty_state": True})
    a = (FixtureAssertion(type="no_dirty_state"),)
    assert evaluate_assertions(outcome, a)[0].passed is False


# ----------------------------------------------------------------------
# spine runner — python / bash / toml
# ----------------------------------------------------------------------


def test_run_python_spine_success(scaffolded: Path) -> None:
    fm, _ = parse_workflow_file(scaffolded / "workflow.md")
    outcome = run_spine(scaffolded, fm, {"steps": 4})
    assert outcome.status == "success"
    assert outcome.metrics["steps_run"] == 4


def test_run_python_spine_exception_becomes_failure(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "boom", spine_lang="python3")
    (wdir / "spine.py").write_text(
        "def main(inputs):\n    raise RuntimeError('kaboom')\n", encoding="utf-8"
    )
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    outcome = run_spine(wdir, fm, {})
    assert outcome.status == "failure"
    assert "kaboom" in (outcome.exception or "")


def test_run_python_spine_bad_output_is_failure(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "badout", spine_lang="python3")
    (wdir / "spine.py").write_text("def main(inputs):\n    return 42\n", encoding="utf-8")
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    assert run_spine(wdir, fm, {}).status == "failure"


def test_run_bash_spine(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "bashwf", spine_lang="bash")
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    outcome = run_spine(wdir, fm, {})
    assert outcome.status == "success"
    assert outcome.metrics["steps_run"] == 1


def test_run_bash_spine_exit_code_failure(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "bashfail", spine_lang="bash")
    (wdir / "spine.sh").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    assert run_spine(wdir, fm, {}).status == "failure"


def test_run_toml_spine(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "tomlwf", spine_lang="toml")
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    outcome = run_spine(wdir, fm, {})
    assert outcome.status == "success"
    assert outcome.metrics["steps_run"] >= 1


def test_run_spine_missing_file_raises(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "gone", spine_lang="python3")
    (wdir / "spine.py").unlink()
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    with pytest.raises(SpineError):
        run_spine(wdir, fm, {})


def test_record_run_appends_journal(scaffolded: Path) -> None:
    fm, _ = parse_workflow_file(scaffolded / "workflow.md")
    outcome = run_spine(scaffolded, fm, {"steps": 2})
    record_run(scaffolded, {"steps": 2}, outcome)
    runs = (scaffolded / "journal" / "runs.jsonl").read_text(encoding="utf-8").strip()
    assert '"status":"success"' in runs.replace(" ", "")


# ----------------------------------------------------------------------
# fixture harness end-to-end
# ----------------------------------------------------------------------


def test_run_fixtures_all_pass(scaffolded: Path) -> None:
    fm, _ = parse_workflow_file(scaffolded / "workflow.md")
    results = run_fixtures(scaffolded, fm)
    assert len(results) == 2
    assert all(r.passed for r in results)
    # outcome.tsv written under rev/current
    assert (scaffolded / "rev" / "current" / "outcome.tsv").read_text(encoding="utf-8").strip()


def test_run_fixtures_no_fixtures_raises(tmp_path: Path) -> None:
    wdir = scaffold_workflow(tmp_path, "nofix", spine_lang="python3")
    for f in (wdir / "fixtures").glob("*.yaml"):
        f.unlink()
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    with pytest.raises(WorkflowFormatError):
        run_fixtures(wdir, fm)


# ----------------------------------------------------------------------
# revisions
# ----------------------------------------------------------------------


def test_snapshot_and_rollback(scaffolded: Path) -> None:
    # Mutate the working copy, snapshot -> r2.
    spine = scaffolded / "spine.py"
    spine.write_text("def main(inputs):\n    return {'status':'success','metrics':{'steps_run':99}}\n")
    r2 = snapshot_revision(scaffolded)
    assert r2 == "r2"
    assert list_revisions(scaffolded) == ["r1", "r2"]
    assert current_revision(scaffolded) == "r2"

    # Rollback to r1 restores the original spine.
    rollback_to(scaffolded, "r1")
    assert current_revision(scaffolded) == "r1"
    assert "99" not in spine.read_text(encoding="utf-8")
    # r2 is retained on disk (never deleted, SPEC §5.6).
    assert (scaffolded / "rev" / "r2").is_dir()


def test_rollback_to_missing_rev_raises(scaffolded: Path) -> None:
    with pytest.raises(WorkflowRevError):
        rollback_to(scaffolded, "r99")


def test_workflow_dir_resolution(tmp_path: Path) -> None:
    assert workflow_dir(tmp_path, "x") == tmp_path / ".memory" / "workflows" / "x"


# ----------------------------------------------------------------------
# Review fixes (2026-06-14): expires preservation, bash exit-code
# precedence, symlink-skip in rev ops, outcome.tsv injection
# ----------------------------------------------------------------------


def test_expires_field_preserved_on_rewrite(tmp_path: Path) -> None:
    """SPEC §4.1/§5.2: `expires` must survive a workflow.md rewrite."""
    doc = tmp_path / "workflow.md"
    doc.write_text(
        "---\nname: x\ndescription: d\ntype: workflow\nscope: project\n"
        "spine_lang: bash\nspine_entry: spine.sh\nmetric_primary: m\n"
        "lifecycle_state: draft\nexpires: 2027-01-01\n---\nbody\n",
        encoding="utf-8",
    )
    fm, body = parse_workflow_file(doc)
    assert "expires" in fm.extra
    assert "expires: 2027-01-01" in render_workflow_file(fm, body)


def test_bash_exit_code_overrides_body_status(tmp_path: Path) -> None:
    """A bash spine that exits 1 is a failure even if its body says success."""
    wdir = scaffold_workflow(tmp_path, "liar", spine_lang="bash")
    (wdir / "spine.sh").write_text(
        '#!/usr/bin/env bash\necho \'{"status":"success","metrics":{"x":1}}\'\nexit 1\n',
        encoding="utf-8",
    )
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    outcome = run_spine(wdir, fm, {})
    assert outcome.status == "failure"
    assert outcome.metrics == {"x": 1}  # metrics still read from the body


def test_current_revision_rejects_out_of_store_symlink(scaffolded: Path) -> None:
    """A current symlink pointing outside rev/ reads as no current rev."""
    link = scaffolded / "rev" / "current"
    link.unlink()
    link.symlink_to(scaffolded.parent)  # points outside rev/
    assert current_revision(scaffolded) is None


def test_snapshot_skips_symlinked_member(tmp_path: Path) -> None:
    """A symlinked working-copy member is not followed into the revision."""
    wdir = scaffold_workflow(tmp_path, "wf", spine_lang="python3")
    secret = tmp_path / "secret.txt"
    secret.write_text("SENSITIVE", encoding="utf-8")
    (wdir / "metrics.yaml").unlink()
    (wdir / "metrics.yaml").symlink_to(secret)
    r2 = snapshot_revision(wdir)
    snap = wdir / "rev" / r2 / "metrics.yaml"
    # The symlink was skipped — no copy of the secret made it in.
    assert not snap.exists() or snap.read_text() != "SENSITIVE"


def test_outcome_tsv_metric_injection_neutralized(tmp_path: Path) -> None:
    """A metric value with tabs/newlines cannot inject TSV columns/rows."""
    wdir = scaffold_workflow(tmp_path, "wf", spine_lang="python3")
    (wdir / "spine.py").write_text(
        "def main(inputs):\n"
        "    return {'status':'success','metrics':{'evil':'a\\tb\\nc'}}\n",
        encoding="utf-8",
    )
    fm, _ = parse_workflow_file(wdir / "workflow.md")
    run_fixtures(wdir, fm)
    tsv = (wdir / "rev" / "current" / "outcome.tsv").read_text(encoding="utf-8")
    # Each fixture produced exactly one row (no injected extra rows).
    assert len([ln for ln in tsv.splitlines() if ln.strip()]) == 2
