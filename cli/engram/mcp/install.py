"""``engram mcp install --target=<client>`` — write MCP server config for
mainstream MCP-aware clients with one command.

Two action modes per target:

- **write** — the target's config-file format and location are stable
  enough to merge in a JSON entry safely. ``install_target`` reads any
  existing config, deep-merges the engram entry under ``mcpServers``,
  and writes back with ``write_atomic``.
- **paste** — the target's config location varies too much across
  platforms, versions, or extensions for blind writes (codex / opencode /
  vscode-*). ``install_target`` returns a paste-ready snippet for the
  operator to copy.

The registry intentionally does not invent file paths it cannot test on
all OSes. Anything where we are not confident about the canonical
location stays in ``paste`` mode.
"""

from __future__ import annotations

import json
import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from engram.core.fs import write_atomic

__all__ = [
    "INSTALL_TARGETS",
    "InstallPlan",
    "InstallTarget",
    "install_target",
    "plan_install",
]


# ------------------------------------------------------------------
# Common snippet
# ------------------------------------------------------------------


def _engram_command() -> str:
    """The command path operators should use to launch the engram MCP server.

    Prefers the absolute path to the installed `engram` binary so the
    config keeps working when the user's shell is launched from a GUI
    (Claude Desktop / Cursor / VS Code) without their venv on PATH.
    """
    found = shutil.which("engram")
    return found or "engram"


def _server_entry() -> dict[str, object]:
    return {
        "command": _engram_command(),
        "args": ["mcp", "serve"],
        "env": {},
    }


def _mcp_servers_snippet() -> dict[str, object]:
    return {"mcpServers": {"engram": _server_entry()}}


def _json_snippet() -> str:
    return json.dumps(_mcp_servers_snippet(), indent=2)


# ------------------------------------------------------------------
# Per-target writers
# ------------------------------------------------------------------


def _claude_desktop_config_path() -> Path:
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if platform.system() == "Windows":
        # AppData is typically the right location on Windows; we fall back
        # to a sensible default that the operator can move post-write.
        return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def _cursor_config_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _zed_settings_path() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / ".config" / "zed" / "settings.json"
    return Path.home() / ".config" / "zed" / "settings.json"


def _merge_into_json_config(path: Path) -> str:
    """Read existing JSON (if any), deep-merge engram into mcpServers, return
    serialized result."""
    existing: dict[str, object]
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            # Operator's config is broken; refuse to merge silently.
            raise RuntimeError(
                f"{path} is not valid JSON; refusing to merge. Fix the file and re-run."
            ) from exc
        if not isinstance(existing, dict):
            raise RuntimeError(f"{path} root is not a JSON object")
    else:
        existing = {}

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"{path}'s mcpServers is not an object")
    servers["engram"] = _server_entry()
    return json.dumps(existing, indent=2) + "\n"


# ------------------------------------------------------------------
# Target registry
# ------------------------------------------------------------------


@dataclass(frozen=True)
class InstallTarget:
    name: str
    describe: str
    snippet: str
    action: str  # "write" or "paste"
    config_path_resolver: Callable[[], Path] | None = None


INSTALL_TARGETS: dict[str, InstallTarget] = {
    "claude-desktop": InstallTarget(
        name="claude-desktop",
        describe="Anthropic Claude Desktop (macOS / Linux / Windows)",
        snippet=_json_snippet(),
        action="write",
        config_path_resolver=_claude_desktop_config_path,
    ),
    "claude-code": InstallTarget(
        name="claude-code",
        describe="Claude Code CLI — recommended `claude mcp add`",
        snippet="claude mcp add engram engram mcp serve",
        action="paste",
    ),
    "cursor": InstallTarget(
        name="cursor",
        describe="Cursor IDE (~/.cursor/mcp.json)",
        snippet=_json_snippet(),
        action="write",
        config_path_resolver=_cursor_config_path,
    ),
    "zed": InstallTarget(
        name="zed",
        describe="Zed editor (~/.config/zed/settings.json `context_servers`)",
        snippet=json.dumps(
            {"context_servers": {"engram": _server_entry()}}, indent=2
        ),
        action="write",
        config_path_resolver=_zed_settings_path,
    ),
    "codex": InstallTarget(
        name="codex",
        describe="OpenAI Codex CLI — paste snippet into your Codex MCP config",
        snippet=_json_snippet(),
        action="paste",
    ),
    "opencode": InstallTarget(
        name="opencode",
        describe="Opencode — paste snippet into your Opencode MCP config",
        snippet=_json_snippet(),
        action="paste",
    ),
    "vscode-continue": InstallTarget(
        name="vscode-continue",
        describe="VS Code Continue.dev extension — paste into ~/.continue/config.json",
        snippet=_json_snippet(),
        action="paste",
    ),
    "vscode-cline": InstallTarget(
        name="vscode-cline",
        describe="VS Code Cline extension — paste into Cline MCP settings",
        snippet=_json_snippet(),
        action="paste",
    ),
    "vscode-copilot": InstallTarget(
        name="vscode-copilot",
        describe="VS Code GitHub Copilot — paste into Copilot MCP settings",
        snippet=_json_snippet(),
        action="paste",
    ),
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


@dataclass
class InstallPlan:
    target: str
    action: str  # "write" or "paste"
    snippet: str
    config_path: Path | None = None


def plan_install(target: str) -> InstallPlan:
    if target not in INSTALL_TARGETS:
        raise KeyError(f"unknown MCP install target: {target!r}")
    spec = INSTALL_TARGETS[target]
    config_path = spec.config_path_resolver() if spec.config_path_resolver else None
    snippet = spec.snippet
    if spec.action == "write" and config_path is not None and target == "zed":
        # Zed merges into a settings.json that already has unrelated keys;
        # we still write the full snippet but point the operator at the
        # path so they can review.
        snippet = json.dumps(
            {"context_servers": {"engram": _server_entry()}}, indent=2
        )
    return InstallPlan(
        target=target, action=spec.action, snippet=snippet, config_path=config_path
    )


def install_target(target: str) -> InstallPlan:
    """Apply the install plan: writes the config file (write mode) or
    leaves disk untouched (paste mode). Returns the InstallPlan with
    ``config_path`` filled when applicable."""
    plan = plan_install(target)
    if plan.action != "write" or plan.config_path is None:
        return plan

    config_path = plan.config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if target in {"claude-desktop", "cursor", "zed"}:
        # All three use a JSON-with-mcpServers shape (zed uses the same key
        # nested under context_servers for its variant; we still merge
        # additively into existing JSON).
        if target == "zed":
            content = _merge_into_zed_settings(config_path)
        else:
            content = _merge_into_json_config(config_path)
        write_atomic(config_path, content)
    else:  # pragma: no cover — registry only assigns "write" to known targets
        raise RuntimeError(f"unhandled write target: {target}")

    return plan


def _merge_into_zed_settings(path: Path) -> str:
    existing: dict[str, object]
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{path} is not valid JSON; refusing to merge. Fix and re-run."
            ) from exc
        if not isinstance(existing, dict):
            raise RuntimeError(f"{path} root is not a JSON object")
    else:
        existing = {}

    servers = existing.setdefault("context_servers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"{path}'s context_servers is not an object")
    servers["engram"] = _server_entry()
    return json.dumps(existing, indent=2) + "\n"
