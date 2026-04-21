"""T-34 tests for `engram migrate --from=v0.1` (SPEC §13.4)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest
import yaml
from click.testing import CliRunner

from engram.cli import cli
from engram.core.journal import read_events
from engram.migrate.v0_1 import (
    BACKUP_DIRNAME,
    detect_v0_1,
    migration_journal_path,
    plan_migration,
    run_migration,
    run_rollback,
)


def _write_v0_1_asset(
    project: Path, filename: str, fm: dict[str, object], body: str
) -> Path:
    """Write a flat v0.1 asset (no local/ subdir)."""
    dst = project / ".memory" / filename
    dst.parent.mkdir(parents=True, exist_ok=True)
    yaml_block = yaml.dump(fm, sort_keys=False, allow_unicode=True)
    dst.write_text(f"---\n{yaml_block}---\n\n{body}\n", encoding="utf-8")
    return dst


@pytest.fixture
def v0_1_project(tmp_path: Path) -> Iterator[Path]:
    """A minimal v0.1 project: .memory/ with flat .md files, no subdirs, no version."""
    project = tmp_path / "v1proj"
    project.mkdir()
    _write_v0_1_asset(
        project,
        "user_role.md",
        {"name": "role", "description": "platform lead", "type": "user"},
        "The user leads platform work.",
    )
    _write_v0_1_asset(
        project,
        "feedback_push.md",
        {
            "name": "push confirm",
            "description": "confirm before push",
            "type": "feedback",
        },
        "Ask before pushing.\n\n**Why:** safety.\n\n**How to apply:** always.",
    )
    _write_v0_1_asset(
        project,
        "agent_squash.md",
        {
            "name": "squash before merge",
            "description": "local squash reduces CI retries",
            "type": "agent",
            "source": "autolearn/r5",
        },
        "Squash.\n\n**Why:** observed.\n\n**How to apply:** here.",
    )
    yield project


# ------------------------------------------------------------------
# Detection
# ------------------------------------------------------------------


def test_detect_v0_1_on_flat_layout(v0_1_project: Path) -> None:
    assert detect_v0_1(v0_1_project) is True


def test_detect_v0_1_false_when_local_exists(tmp_path: Path) -> None:
    project = tmp_path / "v2proj"
    (project / ".memory" / "local").mkdir(parents=True)
    (project / ".engram").mkdir()
    (project / ".engram" / "version").write_text("0.2\n", encoding="utf-8")
    assert detect_v0_1(project) is False


def test_detect_v0_1_false_when_no_memory(tmp_path: Path) -> None:
    assert detect_v0_1(tmp_path) is False


# ------------------------------------------------------------------
# plan_migration (dry-run)
# ------------------------------------------------------------------


def test_plan_lists_every_asset(v0_1_project: Path) -> None:
    plan = plan_migration(v0_1_project)
    moves = {entry["from"] for entry in plan["moves"]}
    assert moves == {
        ".memory/user_role.md",
        ".memory/feedback_push.md",
        ".memory/agent_squash.md",
    }


def test_plan_injects_scope_project(v0_1_project: Path) -> None:
    plan = plan_migration(v0_1_project)
    for entry in plan["moves"]:
        assert "scope" in entry["fields_added"]


def test_plan_injects_enforcement_for_feedback(v0_1_project: Path) -> None:
    plan = plan_migration(v0_1_project)
    fb = next(e for e in plan["moves"] if "feedback_push" in e["from"])
    assert "enforcement" in fb["fields_added"]


def test_plan_injects_confidence_for_agent(v0_1_project: Path) -> None:
    plan = plan_migration(v0_1_project)
    ag = next(e for e in plan["moves"] if "agent_squash" in e["from"])
    assert "confidence" in ag["fields_added"]


def test_plan_no_writes_to_disk(v0_1_project: Path) -> None:
    plan_migration(v0_1_project)
    assert not (v0_1_project / ".memory" / "local").exists()
    assert not (v0_1_project / ".engram").exists()
    assert not (v0_1_project / BACKUP_DIRNAME).exists()


# ------------------------------------------------------------------
# Live migration
# ------------------------------------------------------------------


def test_run_creates_backup(v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    assert (v0_1_project / BACKUP_DIRNAME / "user_role.md").is_file()


def test_run_moves_assets_into_local(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    local = v0_1_project / ".memory" / "local"
    for name in ("user_role.md", "feedback_push.md", "agent_squash.md"):
        assert (local / name).is_file()
    # Flat files should be gone from .memory/ root.
    assert not (v0_1_project / ".memory" / "user_role.md").exists()


def test_run_writes_version_file(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    version = v0_1_project / ".engram" / "version"
    assert version.read_text(encoding="utf-8").strip() == "0.2"


def test_run_creates_subdirs(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    for sub in ("local", "pools", "workflows", "kb"):
        assert (v0_1_project / ".memory" / sub).is_dir()


def test_run_adds_scope_project_to_assets(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    text = (v0_1_project / ".memory" / "local" / "user_role.md").read_text(
        encoding="utf-8"
    )
    assert "scope: project" in text


def test_run_adds_enforcement_default_for_feedback(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    text = (v0_1_project / ".memory" / "local" / "feedback_push.md").read_text(
        encoding="utf-8"
    )
    assert "enforcement: default" in text


def test_run_adds_zeroed_confidence_for_agent(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    text = (v0_1_project / ".memory" / "local" / "agent_squash.md").read_text(
        encoding="utf-8"
    )
    assert "confidence:" in text
    assert "validated_count: 0" in text
    assert "contradicted_count: 0" in text


def test_run_preserves_unknown_frontmatter_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    project.mkdir()
    _write_v0_1_asset(
        project,
        "user_legacy.md",
        {
            "name": "legacy",
            "description": "old fields",
            "type": "user",
            "custom_field_from_v01_tool": "keep me",
        },
        "body",
    )
    run_migration(project)
    text = (project / ".memory" / "local" / "user_legacy.md").read_text(encoding="utf-8")
    assert "custom_field_from_v01_tool" in text
    assert "keep me" in text


def test_run_regenerates_memory_md_with_spec_sections(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    text = (v0_1_project / ".memory" / "MEMORY.md").read_text(encoding="utf-8")
    for section in (
        "## Identity",
        "## Always-on rules",
        "## Topics",
        "## Subscribed pools",
        "## Recently added",
    ):
        assert section in text


def test_run_writes_migration_journal(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    run_migration(v0_1_project)
    events = list(read_events(migration_journal_path()))
    assert len(events) == 1
    entry = events[0]
    assert entry["event"] == "migration"
    assert entry["from_version"] == "0.1"
    assert entry["to_version"] == "0.2"
    assert entry["assets_moved"] == 3


def test_run_idempotent_on_already_migrated(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    # Second run must be a no-op per SPEC §13.4 idempotency.
    result = run_migration(v0_1_project)
    assert result["already_v0_2"] is True


# ------------------------------------------------------------------
# Rollback
# ------------------------------------------------------------------


def test_rollback_restores_v0_1_layout(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    run_migration(v0_1_project)
    assert (v0_1_project / ".memory" / "local" / "user_role.md").is_file()

    run_rollback(v0_1_project)
    assert (v0_1_project / ".memory" / "user_role.md").is_file()
    assert not (v0_1_project / ".memory" / "local").exists()
    assert not (v0_1_project / BACKUP_DIRNAME).exists()


def test_rollback_errors_without_backup(v0_1_project: Path) -> None:
    import click

    with pytest.raises(click.ClickException, match="backup"):
        run_rollback(v0_1_project)


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_migrate_dry_run_json(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(v0_1_project),
            "migrate",
            "--from",
            "v0.1",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["mode"] == "dry-run"
    assert len(payload["moves"]) == 3
    # Dry run doesn't touch disk.
    assert not (v0_1_project / ".memory" / "local").exists()


def test_cli_migrate_live_then_validate_clean(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"]
    )
    assert result.exit_code == 0, result.output
    # validate should find no errors on the migrated store.
    validate_result = runner.invoke(
        cli, ["--format", "json", "--dir", str(v0_1_project), "validate"]
    )
    payload = json.loads(validate_result.output.strip())
    assert payload["summary"]["errors"] == 0


def test_cli_migrate_rollback(
    v0_1_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    result = runner.invoke(
        cli, ["--dir", str(v0_1_project), "migrate", "--rollback"]
    )
    assert result.exit_code == 0, result.output
    assert (v0_1_project / ".memory" / "user_role.md").is_file()


def test_cli_migrate_requires_from_or_rollback(
    v0_1_project: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(v0_1_project), "migrate"])
    assert result.exit_code != 0


def test_cli_migrate_on_v0_2_store_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SPEC §13.4: already-migrated store prints ‘nothing to do’ and exits 0."""
    from engram.commands.init import init_project

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "v2proj"
    project.mkdir()
    init_project(project)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "migrate", "--from", "v0.1"]
    )
    assert result.exit_code == 0
    assert "0.2" in result.output or "nothing" in result.output.lower()


# ------------------------------------------------------------------
# Dedent helper (keep imports tidy)
# ------------------------------------------------------------------

_ = dedent  # touched so lint doesn't flag the import as unused
