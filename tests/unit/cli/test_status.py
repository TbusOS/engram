"""T-22 tests for engram.commands.status — project + scope summary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.status import Status, run_status


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    init_project(tmp_path)
    yield tmp_path


def _add(project: Path, **overrides: str) -> None:
    runner = CliRunner()
    args = [
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        overrides.pop("type", "user"),
        "--name",
        overrides.pop("name", "thing"),
        "--description",
        overrides.pop("description", "desc"),
        "--body",
        overrides.pop("body", "body"),
    ]
    for k, v in overrides.items():
        args.extend([f"--{k.replace('_', '-')}", v])
    assert runner.invoke(cli, args).exit_code == 0


# ------------------------------------------------------------------
# run_status
# ------------------------------------------------------------------


def test_status_uninitialized_project(tmp_path: Path) -> None:
    status = run_status(tmp_path)
    assert isinstance(status, Status)
    assert status.initialized is False
    assert status.store_version is None
    assert status.total_assets == 0


def test_status_initialized_project(project: Path) -> None:
    status = run_status(project)
    assert status.initialized is True
    assert status.store_version == "0.2"
    assert status.project_root == project.resolve()
    assert status.total_assets == 0
    assert status.pool_subscriptions == ()


def test_status_with_memories(project: Path) -> None:
    _add(project, type="user", name="u1")
    _add(project, type="user", name="u2")
    _add(project, type="project", name="p1", body="fact.\n\n**Why:** r.\n\n**How to apply:** a.")

    status = run_status(project)
    assert status.total_assets == 3
    assert status.by_subtype == {"user": 2, "project": 1}
    assert status.by_lifecycle == {"active": 3}


def test_status_reads_pool_subscriptions(project: Path) -> None:
    pools_toml = project / ".memory" / "pools.toml"
    pools_toml.write_text(
        (
            "[subscribe.compliance-checklists]\n"
            'subscribed_at = "team"\n'
            'propagation_mode = "auto-sync"\n'
            "\n"
            "[subscribe.kernel-work]\n"
            'subscribed_at = "user"\n'
            'propagation_mode = "notify"\n'
        ),
        encoding="utf-8",
    )
    status = run_status(project)
    assert len(status.pool_subscriptions) == 2
    pools = {s["pool"] for s in status.pool_subscriptions}
    assert pools == {"compliance-checklists", "kernel-work"}


def test_status_ignores_malformed_pools_toml(project: Path) -> None:
    (project / ".memory" / "pools.toml").write_text("this is not valid toml [[[", encoding="utf-8")
    status = run_status(project)
    # Should not crash; empty subscriptions.
    assert status.pool_subscriptions == ()


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_cli_status_always_exits_zero(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "status"])
    assert result.exit_code == 0, result.output


def test_cli_status_uninitialized_prints_not_initialized(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(tmp_path), "status"])
    assert result.exit_code == 0
    assert "not" in result.output.lower() or "uninit" in result.output.lower()


def test_cli_status_text_output_mentions_project(project: Path) -> None:
    _add(project, name="alpha")
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "status"])
    assert result.exit_code == 0
    assert str(project) in result.output or project.name in result.output
    assert "0.2" in result.output  # store version


def test_cli_status_json_structure(project: Path) -> None:
    _add(project, name="alpha")
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["initialized"] is True
    assert payload["store_version"] == "0.2"
    assert payload["assets"]["total"] == 1
    assert payload["assets"]["by_subtype"] == {"user": 1}
    assert payload["pools"] == []


def test_cli_status_registered_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "status" in result.output