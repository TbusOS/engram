"""Tests for the observer persistent-service install (launchd / systemd)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.observer.service import (
    LAUNCHD_LABEL,
    SYSTEMD_UNIT_NAME,
    ServiceUnsupportedError,
    build_service_plan,
    render_launchd_plist,
    render_systemd_unit,
    resolve_engram_command,
)


def test_resolve_engram_command_is_absolute() -> None:
    cmd = resolve_engram_command()
    assert cmd  # non-empty
    # Either an absolute engram binary or `<python> -m engram`.
    assert cmd[0].startswith("/") or cmd[0] == __import__("sys").executable


def test_launchd_plist_runs_daemon_foreground() -> None:
    plist = render_launchd_plist(["/usr/local/bin/engram"])
    assert f"<string>{LAUNCHD_LABEL}</string>" in plist
    assert "<string>observer</string>" in plist
    assert "<string>daemon</string>" in plist
    assert "<string>--foreground</string>" in plist
    assert "<key>RunAtLoad</key>" in plist
    assert "<key>KeepAlive</key>" in plist


def test_launchd_plist_includes_base_when_given(tmp_path: Path) -> None:
    plist = render_launchd_plist(["/x/engram"], base=tmp_path)
    assert "<string>--base</string>" in plist
    assert f"<string>{tmp_path}</string>" in plist


def test_systemd_unit_has_execstart_and_restart() -> None:
    unit = render_systemd_unit(["/usr/bin/engram"])
    assert "ExecStart=/usr/bin/engram observer daemon --foreground" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_build_service_plan_darwin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("engram.observer.service.sys.platform", "darwin")
    plan = build_service_plan(home=tmp_path)
    assert plan.platform == "launchd"
    assert plan.target_path == tmp_path / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    assert plan.load_command[0] == "launchctl"


def test_build_service_plan_linux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("engram.observer.service.sys.platform", "linux")
    plan = build_service_plan(home=tmp_path)
    assert plan.platform == "systemd"
    assert plan.target_path == tmp_path / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME
    assert plan.load_command[:2] == ["systemctl", "--user"]


def test_build_service_plan_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engram.observer.service.sys.platform", "sunos5")
    with pytest.raises(ServiceUnsupportedError):
        build_service_plan()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def test_cli_install_service_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    res = CliRunner().invoke(cli, ["observer", "install-service", "--dry-run"])
    assert res.exit_code == 0
    assert "would write" in res.output
    # Nothing created under the fake HOME.
    agents = tmp_path / "home" / "Library" / "LaunchAgents"
    sysd = tmp_path / "home" / ".config" / "systemd" / "user"
    assert not agents.exists() and not sysd.exists()


def test_cli_install_service_writes_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    res = CliRunner().invoke(cli, ["observer", "install-service"])
    assert res.exit_code == 0, res.output
    assert "wrote" in res.output
    # The unit landed at the platform path under the fake HOME.
    plan = build_service_plan(home=home)
    assert plan.target_path.is_file()
    assert "observer" in plan.target_path.read_text()
