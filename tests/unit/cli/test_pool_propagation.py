"""T-31 tests for auto-sync propagation + `engram pool sync`."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import tomli
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.core.journal import read_events


def _make_pool_with_rev(
    home: Path, name: str, rev_ids: tuple[str, ...] = ("r1",)
) -> Path:
    """Create a pool with a rev/ tree. `rev_ids[-1]` becomes rev/current."""
    pool_dir = home / ".engram" / "pools" / name
    pool_dir.mkdir(parents=True)
    rev_parent = pool_dir / "rev"
    rev_parent.mkdir()
    for rid in rev_ids:
        rev = rev_parent / rid
        rev.mkdir()
        (rev / "MEMORY.md").write_text(f"# {name} @ {rid}\n", encoding="utf-8")
    # Relative symlink is the spec-compliant way for portability.
    os.symlink(rev_ids[-1], rev_parent / "current")
    return pool_dir


@pytest.fixture
def project_and_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path]]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "proj"
    project.mkdir()
    init_project(project)
    yield project, home


def _read_toml(project: Path) -> dict[str, object]:
    return tomli.loads((project / ".memory" / "pools.toml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------
# Subscribe target resolution
# ------------------------------------------------------------------


def test_subscribe_auto_sync_targets_rev_current(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system"]
    )
    assert result.exit_code == 0, result.output

    link = project / ".memory" / "pools" / "design-system"
    # The link should point at the pool's rev/current symlink so future
    # `publish` operations become visible without re-subscribing.
    target = Path(os.readlink(link))
    assert target == (home / ".engram" / "pools" / "design-system" / "rev" / "current")


def test_subscribe_pinned_targets_specific_rev(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1", "r2"))
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
            "r1",
        ],
    )
    assert result.exit_code == 0, result.output

    link = project / ".memory" / "pools" / "design-system"
    target = Path(os.readlink(link))
    assert target == (home / ".engram" / "pools" / "design-system" / "rev" / "r1")


def test_subscribe_pinned_rejects_nonexistent_revision(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
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
            "r99",
        ],
    )
    assert result.exit_code != 0
    assert "r99" in result.output


def test_subscribe_records_last_synced_rev_for_auto_sync(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1", "r2", "r3"))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "design-system"]
    )
    assert result.exit_code == 0
    entry = _read_toml(project)["subscribe"]["design-system"]  # type: ignore[index]
    assert entry["last_synced_rev"] == "r3"


def test_subscribe_records_last_synced_rev_for_pinned(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1", "r2"))
    runner = CliRunner()
    runner.invoke(
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
            "r1",
        ],
    )
    entry = _read_toml(project)["subscribe"]["design-system"]  # type: ignore[index]
    assert entry["last_synced_rev"] == "r1"


def test_subscribe_without_rev_falls_back_to_pool_dir(
    project_and_home: tuple[Path, Path],
) -> None:
    """Backward-compat: a pool without rev/ can still be subscribed to (e.g.
    during pool bootstrap before any publish). Links to the pool root; no
    last_synced_rev recorded."""
    project, home = project_and_home
    pool_dir = home / ".engram" / "pools" / "bare-pool"
    pool_dir.mkdir(parents=True)
    (pool_dir / "MEMORY.md").write_text("# bare pool\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "subscribe", "bare-pool"]
    )
    assert result.exit_code == 0, result.output
    entry = _read_toml(project)["subscribe"]["bare-pool"]  # type: ignore[index]
    assert "last_synced_rev" not in entry


# ------------------------------------------------------------------
# pool sync
# ------------------------------------------------------------------


def _advance_pool(home: Path, name: str, new_rev: str) -> None:
    pool = home / ".engram" / "pools" / name
    (pool / "rev" / new_rev).mkdir()
    (pool / "rev" / new_rev / "MEMORY.md").write_text(
        f"# {name} @ {new_rev}\n", encoding="utf-8"
    )
    current = pool / "rev" / "current"
    current.unlink()
    os.symlink(new_rev, current)


def test_sync_updates_last_synced_rev_when_pool_advances(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])

    _advance_pool(home, "design-system", "r2")

    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "sync", "design-system"]
    )
    assert result.exit_code == 0, result.output
    entry = _read_toml(project)["subscribe"]["design-system"]  # type: ignore[index]
    assert entry["last_synced_rev"] == "r2"


def test_sync_writes_propagation_completed_event(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])
    _advance_pool(home, "design-system", "r2")

    runner.invoke(cli, ["--dir", str(project), "pool", "sync", "design-system"])

    journal = home / ".engram" / "journal" / "propagation.jsonl"
    assert journal.is_file()
    events = list(read_events(journal))
    completed = [e for e in events if e.get("event") == "propagation_completed"]
    assert len(completed) >= 1
    latest = completed[-1]
    assert latest["pool"] == "design-system"
    assert latest["from_rev"] == "r1"
    assert latest["to_rev"] == "r2"


def test_sync_all_touches_every_auto_sync_subscription(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "alpha", ("r1",))
    _make_pool_with_rev(home, "beta", ("r1",))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "alpha"])
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "beta"])

    _advance_pool(home, "alpha", "r2")
    _advance_pool(home, "beta", "r2")

    result = runner.invoke(cli, ["--dir", str(project), "pool", "sync", "--all"])
    assert result.exit_code == 0, result.output

    subs = _read_toml(project)["subscribe"]  # type: ignore[assignment]
    assert subs["alpha"]["last_synced_rev"] == "r2"  # type: ignore[index]
    assert subs["beta"]["last_synced_rev"] == "r2"  # type: ignore[index]


def test_sync_skips_pinned_subscriptions(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "pinme", ("r1", "r2"))
    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "pool",
            "subscribe",
            "pinme",
            "--mode",
            "pinned",
            "--revision",
            "r1",
        ],
    )
    _advance_pool(home, "pinme", "r3")

    result = runner.invoke(cli, ["--dir", str(project), "pool", "sync", "--all"])
    assert result.exit_code == 0
    entry = _read_toml(project)["subscribe"]["pinme"]  # type: ignore[index]
    # Pinned subscription's last_synced_rev stays at the pinned revision.
    assert entry["last_synced_rev"] == "r1"


def test_sync_no_change_reports_up_to_date(
    project_and_home: tuple[Path, Path],
) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])

    # No advance — sync is a no-op.
    result = runner.invoke(
        cli, ["--dir", str(project), "pool", "sync", "design-system"]
    )
    assert result.exit_code == 0
    assert "up to date" in result.output.lower() or "no change" in result.output.lower()


def test_sync_unknown_subscription_errors(project_and_home: tuple[Path, Path]) -> None:
    project, _ = project_and_home
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "pool", "sync", "phantom"])
    assert result.exit_code != 0


def test_sync_json_output(project_and_home: tuple[Path, Path]) -> None:
    project, home = project_and_home
    _make_pool_with_rev(home, "design-system", ("r1",))
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(project), "pool", "subscribe", "design-system"])
    _advance_pool(home, "design-system", "r2")

    result = runner.invoke(
        cli,
        ["--format", "json", "--dir", str(project), "pool", "sync", "design-system"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["pool"] == "design-system"
    assert payload["from_rev"] == "r1"
    assert payload["to_rev"] == "r2"
