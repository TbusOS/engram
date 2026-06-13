"""CLI tests for ``engram workflow`` (SPEC §5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    proj = tmp_path / "proj"
    runner = CliRunner()
    res = runner.invoke(cli, ["--dir", str(proj), "init"])
    assert res.exit_code == 0, res.output
    return proj


def _run(project: Path, *args: str):
    return CliRunner().invoke(cli, ["--dir", str(project), *args])


def test_add_list_read(project: Path) -> None:
    res = _run(project, "workflow", "add", "deploy", "--lang", "python3")
    assert res.exit_code == 0, res.output
    assert (project / ".memory" / "workflows" / "deploy" / "workflow.md").is_file()

    listed = _run(project, "--format", "json", "workflow", "list")
    assert listed.exit_code == 0
    rows = json.loads(listed.output)
    assert any(r["name"] == "deploy" and r["current_rev"] == "r1" for r in rows)

    read = _run(project, "--format", "json", "workflow", "read", "deploy")
    assert read.exit_code == 0
    assert json.loads(read.output)["type"] == "workflow"


def test_add_rejects_duplicate(project: Path) -> None:
    assert _run(project, "workflow", "add", "dup").exit_code == 0
    dup = _run(project, "workflow", "add", "dup")
    assert dup.exit_code != 0
    assert "already exists" in dup.output


def test_validate_clean(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    res = _run(project, "--format", "json", "workflow", "validate", "wf")
    assert res.exit_code == 0
    assert json.loads(res.output)["valid"] is True


def test_validate_detects_broken_spine(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    (project / ".memory" / "workflows" / "wf" / "spine.py").unlink()
    res = _run(project, "workflow", "validate", "wf")
    assert res.exit_code == 2
    assert "spine_entry" in res.output


def test_test_all_pass(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    res = _run(project, "workflow", "test", "wf")
    assert res.exit_code == 0
    assert "2/2 fixtures passed" in res.output


def test_test_reports_failure_nonzero(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    # Make the spine always fail.
    (project / ".memory" / "workflows" / "wf" / "spine.py").write_text(
        "def main(inputs):\n    return {'status':'failure','metrics':{}}\n"
    )
    res = _run(project, "workflow", "test", "wf")
    assert res.exit_code == 1


def test_run_records_journal(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    res = _run(project, "--format", "json", "workflow", "run", "wf", "--inputs", '{"steps":7}')
    assert res.exit_code == 0
    assert json.loads(res.output)["metrics"]["steps_run"] == 7
    runs = (project / ".memory" / "workflows" / "wf" / "journal" / "runs.jsonl").read_text()
    assert runs.strip()


def test_run_bad_json_inputs(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    res = _run(project, "workflow", "run", "wf", "--inputs", "{not json}")
    assert res.exit_code != 0
    assert "not valid JSON" in res.output


def test_run_missing_required_input(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    wdir = project / ".memory" / "workflows" / "wf"
    (wdir / "schemas").mkdir()
    (wdir / "schemas" / "inputs.json").write_text(
        json.dumps({"type": "object", "required": ["repo_url"]})
    )
    # Declare the schema in frontmatter.
    doc = wdir / "workflow.md"
    text = doc.read_text().replace(
        "spine_entry: spine.py", "spine_entry: spine.py\ninputs_schema: schemas/inputs.json"
    )
    doc.write_text(text)
    res = _run(project, "workflow", "run", "wf", "--inputs", "{}")
    assert res.exit_code != 0
    assert "missing required" in res.output


def test_run_side_effects_prompt_aborts(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    doc = project / ".memory" / "workflows" / "wf" / "workflow.md"
    doc.write_text(
        doc.read_text().replace("lifecycle_state: draft", "lifecycle_state: draft\nside_effects: [fs_write]")
    )
    # Decline the prompt.
    res = CliRunner().invoke(
        cli, ["--dir", str(project), "workflow", "run", "wf"], input="n\n"
    )
    assert res.exit_code != 0
    assert "side effects" in res.output
    # --yes bypasses the prompt.
    res2 = _run(project, "workflow", "run", "wf", "--yes")
    assert res2.exit_code == 0


def test_history_revise_rollback(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    spine = project / ".memory" / "workflows" / "wf" / "spine.py"
    spine.write_text("def main(inputs):\n    return {'status':'success','metrics':{'steps_run':42}}\n")
    assert _run(project, "workflow", "revise", "wf").exit_code == 0

    hist = _run(project, "--format", "json", "workflow", "history", "wf")
    payload = json.loads(hist.output)
    assert payload["revisions"] == ["r1", "r2"]
    assert payload["current"] == "r2"

    assert _run(project, "workflow", "rollback", "wf", "--to", "r1").exit_code == 0
    assert "42" not in spine.read_text()


def test_rollback_bad_rev(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    res = _run(project, "workflow", "rollback", "wf", "--to", "r99")
    assert res.exit_code != 0


def test_deprecate(project: Path) -> None:
    _run(project, "workflow", "add", "wf")
    assert _run(project, "workflow", "deprecate", "wf").exit_code == 0
    read = _run(project, "--format", "json", "workflow", "read", "wf")
    assert json.loads(read.output)["lifecycle_state"] == "deprecated"


def test_unknown_workflow_clean_error(project: Path) -> None:
    res = _run(project, "workflow", "read", "ghost")
    assert res.exit_code != 0
    assert "no workflow named" in res.output


def test_workflow_honors_dir_no_project_clean_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli, ["workflow", "list"])
    assert res.exit_code != 0
    assert "engram init" in res.output
