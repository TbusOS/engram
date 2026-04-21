"""T-30 tests for engram.commands.pool — subscribe / unsubscribe / list."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import tomli
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project


def _make_pool(home: Path, name: str) -> Path:
    pool_dir = home / ".engram" / "pools" / name
    pool_dir.mkdir(parents=True)
    # Minimal pool structure: a MEMORY.md so the dir looks plausible.
    (pool_dir / "MEMORY.md").write_text("# pool memory\n", encoding="utf-8")
    return pool_dir


@pytest.fixture
def project_and_pools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path]]:
    """Init an engram project + two fake pools under a fake HOME."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    project = tmp_path / "proj"
    project.mkdir()
    init_project(project)

    _make_pool(fake_home, "design-system")
    _make_pool(fake_home, "kernel-work")
    yield project, fake_home


def _read_pools_toml(project: Path) -> dict[str, object]:
    return tomli.loads(
        (project / ".memory" / "pools.toml").read_text(encoding="utf-8")
    )


# ------------------------------------------------------------------
# subscribe
# ------------------------------------------------------------------


def test_subscribe_writes_toml_entry(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "team"],
    )
    assert result.exit_code == 0, result.output
    data = _read_pools_toml(project)
    subs = data["subscribe"]  # type: ignore[index]
    assert "design-system" in subs  # type: ignore[operator]
    assert subs["design-system"]["subscribed_at"] == "team"  # type: ignore[index]
    assert subs["design-system"]["propagation_mode"] == "auto-sync"  # type: ignore[index]


def test_subscribe_creates_symlink(project_and_pools: tuple[Path, Path]) -> None:
    project, home = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "team"]
    )
    assert result.exit_code == 0, result.output
    link = project / ".memory" / "pools" / "design-system"
    assert link.is_symlink()
    assert link.resolve() == (home / ".engram" / "pools" / "design-system").resolve()


def test_subscribe_rejects_missing_pool(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "phantom", "--at", "user"]
    )
    assert result.exit_code != 0
    assert "phantom" in result.output.lower() or "not found" in result.output.lower()


def test_subscribe_defaults_at_to_project(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system"]
    )
    assert result.exit_code == 0, result.output
    data = _read_pools_toml(project)
    assert data["subscribe"]["design-system"]["subscribed_at"] == "project"  # type: ignore[index]


def test_subscribe_rejects_invalid_at_value(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "galaxy"],
    )
    assert result.exit_code != 0


def test_subscribe_pinned_requires_revision(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "pool",
            "subscribe",
            "design-system",
            "--mode",
            "pinned",
        ],
    )
    assert result.exit_code != 0
    assert "pinned" in result.output.lower() and "revision" in result.output.lower()


def test_subscribe_pinned_with_revision(project_and_pools: tuple[Path, Path]) -> None:
    project, home = project_and_pools
    # Pinned mode now requires the rev/<N>/ directory to exist (T-31 tightening).
    pool_rev = home / ".engram" / "pools" / "design-system" / "rev" / "r3"
    pool_rev.mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "pool",
            "subscribe",
            "design-system",
            "--mode",
            "pinned",
            "--revision",
            "r3",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _read_pools_toml(project)
    entry = data["subscribe"]["design-system"]  # type: ignore[index]
    assert entry["propagation_mode"] == "pinned"
    assert entry["pinned_revision"] == "r3"


def test_subscribe_twice_errors_without_force(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system"]
    )
    assert result.exit_code != 0


def test_subscribe_force_overwrites(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    runner.invoke(
        cli,
        ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "project"],
    )
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "pool",
            "subscribe",
            "design-system",
            "--at",
            "team",
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    data = _read_pools_toml(project)
    assert data["subscribe"]["design-system"]["subscribed_at"] == "team"  # type: ignore[index]


# ------------------------------------------------------------------
# unsubscribe
# ------------------------------------------------------------------


def test_unsubscribe_removes_entry_and_symlink(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])
    link = project / ".memory" / "pools" / "design-system"
    assert link.is_symlink()

    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "unsubscribe", "design-system"]
    )
    assert result.exit_code == 0, result.output
    assert not link.exists() and not link.is_symlink()
    data = _read_pools_toml(project)
    subs = data.get("subscribe", {})
    assert "design-system" not in subs  # type: ignore[operator]


def test_unsubscribe_unknown_pool_errors(
    project_and_pools: tuple[Path, Path],
) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "unsubscribe", "phantom"]
    )
    assert result.exit_code != 0


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


def test_list_empty(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "list"])
    assert result.exit_code == 0


def test_list_shows_subscriptions(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "team"]
    )
    runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "kernel-work", "--at", "user"]
    )
    result = runner.invoke(cli, ["--dir", str(project), "pool", "list"])
    assert result.exit_code == 0
    assert "design-system" in result.output
    assert "kernel-work" in result.output


def test_list_json_structure(project_and_pools: tuple[Path, Path]) -> None:
    project, _ = project_and_pools
    runner = CliRunner()
    runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system", "--at", "team"]
    )
    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "pool", "list"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert isinstance(payload, list)
    assert any(entry["pool"] == "design-system" for entry in payload)


def test_pool_group_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "pool" in result.output
