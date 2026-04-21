"""T-35 end-to-end: v0.1 → v0.2 migration with zero data loss.

Drives the full migrate flow against the 20-asset fixture at
``tests/fixtures/v0.1_store/`` and asserts that:

1. Dry-run is byte-preserving (disk is unchanged after ``--dry-run``).
2. Live migration moves every asset into ``local/`` without corrupting
   any body or dropping any pre-existing frontmatter field.
3. The backup ``.memory.pre-v0.2.backup/`` mirrors the original store
   byte-for-byte (so rollback can restore exactly).
4. SPEC §13.4 defaults (``scope: project``; ``enforcement: default`` for
   feedback; zero-state ``confidence`` block for agent) land on every
   asset that lacked them.
5. ``engram validate`` reports zero errors on the migrated store.
6. The migration journal event records the correct asset count.
7. Rollback restores every original file byte-for-byte.

The "zero data loss" contract is the one line of M3 the project cannot
compromise on — existing users with real v0.1 stores must be able to
migrate without losing a single keystroke.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from engram.cli import cli
from engram.core.journal import read_events
from engram.migrate.v0_1 import BACKUP_DIRNAME, migration_journal_path

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "v0.1_store"
EXPECTED_ASSET_COUNT = 20


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot_dir(directory: Path) -> dict[str, tuple[int, str]]:
    """Return {relative_path: (size, sha256)} for every file under ``directory``."""
    out: dict[str, tuple[int, str]] = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        rel = str(path.relative_to(directory))
        out[rel] = (len(data), _hash_bytes(data))
    return out


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    assert text.startswith("---\n"), "fixture asset missing opening YAML fence"
    yaml_block, _, body = text[4:].partition("\n---\n")
    loaded = yaml.safe_load(yaml_block) or {}
    assert isinstance(loaded, dict)
    return loaded, body


@pytest.fixture
def v0_1_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A writable copy of the fixture store, plus a tmp HOME for the journal."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "v0_1_project"
    shutil.copytree(FIXTURE_DIR, project)
    # README.md is fixture metadata, not part of the v0.1 store.
    (project / "README.md").unlink(missing_ok=True)
    return project


# ------------------------------------------------------------------
# Fixture sanity — if this breaks, every test below is untrustworthy.
# ------------------------------------------------------------------


def test_fixture_has_expected_asset_count() -> None:
    memory = FIXTURE_DIR / ".memory"
    asset_files = [p for p in memory.glob("*.md") if p.name != "MEMORY.md"]
    assert len(asset_files) == EXPECTED_ASSET_COUNT, (
        f"fixture must have exactly {EXPECTED_ASSET_COUNT} assets; "
        f"found {len(asset_files)}: {[p.name for p in asset_files]}"
    )


def test_fixture_is_shaped_like_v0_1() -> None:
    """Guard against the fixture accidentally being upgraded to v0.2 shape."""
    memory = FIXTURE_DIR / ".memory"
    assert not (memory / "local").exists(), "v0.1 fixture must not contain local/"
    assert not (FIXTURE_DIR / ".engram").exists(), "v0.1 fixture must not have .engram/"
    for asset in memory.glob("*.md"):
        if asset.name == "MEMORY.md":
            continue
        fm, _ = _split_frontmatter(asset.read_text(encoding="utf-8"))
        assert "scope" not in fm, f"{asset.name} has scope — not a v0.1 asset"
        if fm.get("type") == "feedback":
            assert "enforcement" not in fm, (
                f"{asset.name} already has enforcement — not a v0.1 asset"
            )
        if fm.get("type") == "agent":
            assert "confidence" not in fm, (
                f"{asset.name} already has confidence — not a v0.1 asset"
            )


# ------------------------------------------------------------------
# Dry-run preserves disk
# ------------------------------------------------------------------


def test_dry_run_does_not_touch_disk(v0_1_project: Path) -> None:
    before = _snapshot_dir(v0_1_project)
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
    payload = json.loads(result.output)
    assert payload["mode"] == "dry-run"
    assert len(payload["moves"]) == EXPECTED_ASSET_COUNT

    after = _snapshot_dir(v0_1_project)
    assert before == after, "dry-run must not modify any file"
    assert not (v0_1_project / BACKUP_DIRNAME).exists()
    assert not (v0_1_project / ".engram").exists()


# ------------------------------------------------------------------
# Live migration — zero data loss on assets
# ------------------------------------------------------------------


def test_live_migration_preserves_every_body_verbatim(v0_1_project: Path) -> None:
    original_assets = {
        p.name: p.read_text(encoding="utf-8")
        for p in (v0_1_project / ".memory").glob("*.md")
        if p.name != "MEMORY.md"
    }
    assert len(original_assets) == EXPECTED_ASSET_COUNT

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"]
    )
    assert result.exit_code == 0, result.output

    local = v0_1_project / ".memory" / "local"
    migrated = {p.name: p.read_text(encoding="utf-8") for p in local.glob("*.md")}
    assert migrated.keys() == original_assets.keys(), (
        "every v0.1 asset must appear under local/ after migration"
    )

    for name, new_text in migrated.items():
        old_text = original_assets[name]
        old_fm, old_body = _split_frontmatter(old_text)
        new_fm, new_body = _split_frontmatter(new_text)

        assert new_body == old_body, (
            f"body changed for {name}:\nold:\n{old_body!r}\nnew:\n{new_body!r}"
        )

        for key, value in old_fm.items():
            assert key in new_fm, f"frontmatter key {key!r} lost in {name}"
            assert new_fm[key] == value, (
                f"frontmatter key {key!r} changed in {name}: "
                f"{value!r} → {new_fm[key]!r}"
            )


def test_live_migration_injects_scope_on_every_asset(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    local = v0_1_project / ".memory" / "local"
    for asset in local.glob("*.md"):
        fm, _ = _split_frontmatter(asset.read_text(encoding="utf-8"))
        assert fm.get("scope") == "project", f"{asset.name} missing scope=project"


def test_live_migration_injects_enforcement_on_every_feedback(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    local = v0_1_project / ".memory" / "local"
    feedback_assets = [
        p for p in local.glob("*.md")
        if _split_frontmatter(p.read_text(encoding="utf-8"))[0].get("type") == "feedback"
    ]
    assert len(feedback_assets) == 5, "fixture has 5 feedback assets"
    for asset in feedback_assets:
        fm, _ = _split_frontmatter(asset.read_text(encoding="utf-8"))
        assert fm.get("enforcement") == "default", (
            f"{asset.name} missing enforcement=default after migration"
        )


def test_live_migration_injects_zero_confidence_on_every_agent(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    local = v0_1_project / ".memory" / "local"
    agent_assets = [
        p for p in local.glob("*.md")
        if _split_frontmatter(p.read_text(encoding="utf-8"))[0].get("type") == "agent"
    ]
    assert len(agent_assets) == 3, "fixture has 3 agent assets"
    for asset in agent_assets:
        fm, _ = _split_frontmatter(asset.read_text(encoding="utf-8"))
        conf = fm.get("confidence")
        assert isinstance(conf, dict), f"{asset.name} missing confidence block"
        assert conf["validated_count"] == 0
        assert conf["contradicted_count"] == 0
        assert conf["usage_count"] == 0
        assert conf["last_validated"], f"{asset.name} confidence missing last_validated"


def test_live_migration_preserves_custom_frontmatter_fields(v0_1_project: Path) -> None:
    """The fixture carries two custom fields: ``priority`` on one feedback and
    ``origin_tool`` on one reference. SPEC §4.1 forward-compat: both survive."""
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    local = v0_1_project / ".memory" / "local"

    priority_asset = local / "feedback_respond_in_user_language.md"
    fm, _ = _split_frontmatter(priority_asset.read_text(encoding="utf-8"))
    assert fm["priority"] == "high"

    origin_asset = local / "reference_grafana_slo_board.md"
    fm, _ = _split_frontmatter(origin_asset.read_text(encoding="utf-8"))
    assert fm["origin_tool"] == "dashboard-inventory-scanner"


# ------------------------------------------------------------------
# Backup & journal
# ------------------------------------------------------------------


def test_backup_is_byte_identical_to_original(v0_1_project: Path) -> None:
    before = _snapshot_dir(v0_1_project / ".memory")

    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])

    backup = v0_1_project / BACKUP_DIRNAME
    assert backup.is_dir(), "backup directory must exist after migration"
    after_backup = _snapshot_dir(backup)
    assert before == after_backup, (
        "backup must mirror the pre-migration .memory/ byte-for-byte"
    )


def test_migration_journal_records_twenty_assets(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])

    events = list(read_events(migration_journal_path()))
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "migration"
    assert ev["from_version"] == "0.1"
    assert ev["to_version"] == "0.2"
    assert ev["assets_moved"] == EXPECTED_ASSET_COUNT


# ------------------------------------------------------------------
# Post-migration store passes validate
# ------------------------------------------------------------------


def test_migrated_store_validates_clean(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])

    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(v0_1_project), "validate"]
    )
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.output)
    assert payload["summary"]["errors"] == 0, (
        f"migrated store must have zero validate errors; got: {payload}"
    )


def test_version_file_written(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    version = v0_1_project / ".engram" / "version"
    assert version.read_text(encoding="utf-8").strip() == "0.2"


# ------------------------------------------------------------------
# Idempotency + rollback round-trip
# ------------------------------------------------------------------


def test_rerun_after_success_is_noop(v0_1_project: Path) -> None:
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    snapshot_after_first = _snapshot_dir(v0_1_project / ".memory" / "local")

    result = runner.invoke(
        cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"]
    )
    assert result.exit_code == 0
    snapshot_after_second = _snapshot_dir(v0_1_project / ".memory" / "local")
    assert snapshot_after_first == snapshot_after_second, (
        "a second migration run must be a no-op"
    )


def test_rollback_restores_every_byte(v0_1_project: Path) -> None:
    before = _snapshot_dir(v0_1_project / ".memory")

    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--from", "v0.1"])
    assert (v0_1_project / ".memory" / "local").is_dir()

    result = runner.invoke(cli, ["--dir", str(v0_1_project), "migrate", "--rollback"])
    assert result.exit_code == 0, result.output

    after = _snapshot_dir(v0_1_project / ".memory")
    assert before == after, (
        "rollback must produce a .memory/ that is byte-identical to the "
        "pre-migration state"
    )
    assert not (v0_1_project / BACKUP_DIRNAME).exists(), (
        "rollback must consume the backup"
    )
    assert not (v0_1_project / ".engram" / "version").exists(), (
        "rollback must remove the v0.2 version marker"
    )
