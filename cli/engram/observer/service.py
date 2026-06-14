"""Persistent service install for the observer daemon (usability).

``engram observer daemon`` runs the auto-continuation pipeline, but a
user has to start it by hand. This module generates a platform service
definition — a launchd LaunchAgent on macOS, a systemd *user* unit on
Linux — so the daemon comes up at login and restarts on failure, and
auto-continuation "just works" without a babysitter.

Generation is pure + testable; actually loading the service (``launchctl
load`` / ``systemctl --user enable --now``) is an explicit ``--start``
opt-in, since it is a state change on the user's machine.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from engram.core.paths import user_root

__all__ = [
    "LAUNCHD_LABEL",
    "SYSTEMD_UNIT_NAME",
    "ServicePlan",
    "build_service_plan",
    "render_launchd_plist",
    "render_systemd_unit",
    "resolve_engram_command",
]

LAUNCHD_LABEL = "com.engram.observer"
SYSTEMD_UNIT_NAME = "engram-observer.service"


class ServiceUnsupportedError(RuntimeError):
    """Raised when the host platform has no supported service manager."""


def resolve_engram_command() -> list[str]:
    """Return the argv that runs the engram CLI, preferring an absolute path.

    A service definition must be self-contained — it cannot rely on the
    interactive shell's PATH. Prefer the resolved ``engram`` binary; fall
    back to ``<python> -m engram`` with an absolute interpreter path.
    """
    found = shutil.which("engram")
    if found:
        return [found]
    return [sys.executable, "-m", "engram"]


@dataclass(frozen=True, slots=True)
class ServicePlan:
    """What an install would write, where, and how to load it."""

    platform: str  # "launchd" | "systemd"
    target_path: Path
    content: str
    load_command: list[str]
    unload_command: list[str]


def render_launchd_plist(command: list[str], *, base: Path | None = None) -> str:
    """Render a macOS LaunchAgent plist running the observer daemon."""
    args = [*command, "observer", "daemon", "--foreground"]
    if base is not None:
        args += ["--base", str(base)]
    log_dir = (base if base is not None else user_root()) / "journal"
    arg_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{arg_xml}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>{log_dir / "observer.service.out.log"}</string>
  <key>StandardErrorPath</key>
  <string>{log_dir / "observer.service.err.log"}</string>
</dict>
</plist>
"""


def render_systemd_unit(command: list[str], *, base: Path | None = None) -> str:
    """Render a Linux systemd *user* unit running the observer daemon."""
    args = [*command, "observer", "daemon", "--foreground"]
    if base is not None:
        args += ["--base", str(base)]
    exec_start = " ".join(args)
    return f"""\
[Unit]
Description=engram observer daemon (auto-continuation pipeline)
After=default.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def build_service_plan(*, base: Path | None = None, home: Path | None = None) -> ServicePlan:
    """Compute the service plan for the current platform.

    ``home`` overrides the home directory for target-path resolution
    (tests pass a tmp dir); production uses ``Path.home()``.
    """
    h = home if home is not None else Path.home()
    command = resolve_engram_command()
    if sys.platform == "darwin":
        target = h / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        return ServicePlan(
            platform="launchd",
            target_path=target,
            content=render_launchd_plist(command, base=base),
            load_command=["launchctl", "load", "-w", str(target)],
            unload_command=["launchctl", "unload", "-w", str(target)],
        )
    if sys.platform.startswith("linux"):
        target = h / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME
        return ServicePlan(
            platform="systemd",
            target_path=target,
            content=render_systemd_unit(command, base=base),
            load_command=["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT_NAME],
            unload_command=["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT_NAME],
        )
    raise ServiceUnsupportedError(
        f"no supported service manager for platform {sys.platform!r}; "
        "run `engram observer daemon` under your own supervisor"
    )
