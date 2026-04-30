"""``engram observer install`` — wire observer hooks into a host client.

Modelled on T-163's :mod:`engram.mcp.install`. Two action modes:

- **paste** — print a snippet for the user to copy into their host's
  config (used when the host's config layout varies per machine).
- **write** — atomically merge an `engram` block into a known config
  file (used when the host's config has a stable, single location).

Each target's hook script ships under
``adapters/<client>/hooks/engram_observe_post_tool_use.sh``. The
installer never copies the script — it references it by absolute path
so updates flow automatically with ``git pull``.

Security hardening (security reviewer F7, 2026-04-30):

- The Claude Code merger writes the hook command as
  ``ENGRAM_BIN=/abs/path /abs/hook.sh`` so the hook runs the
  resolved engram binary even if a malicious project later prepends
  its own ``bin/engram`` to ``$PATH``.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "INSTALL_TARGETS",
    "InstallPlan",
    "InstallTarget",
    "build_install_plan",
    "hook_script_path",
    "list_install_targets",
]


def _adapters_root() -> Path:
    """Absolute path to the bundled ``adapters/`` tree.

    Walks up from this source file looking for an ``adapters/`` dir
    that contains the per-client ``hooks/`` layout. We anchor on the
    layout (``adapters/claude-code/hooks/``) rather than the bare name
    so the lookup ignores the unrelated ``cli/engram/adapters/`` Python
    module (which is the file-based adapter renderer, not the bundled
    hook tree).
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "adapters"
        if (candidate / "claude-code" / "hooks").is_dir():
            return candidate
    # Fallback so callers always get *some* path; tests override.
    return here.parents[3] / "adapters"


def hook_script_path(client: str, *, adapters_root: Path | None = None) -> Path:
    """Return the absolute path to a client's PostToolUse hook script."""
    root = adapters_root if adapters_root is not None else _adapters_root()
    return root / client / "hooks" / "engram_observe_post_tool_use.sh"


@dataclass(frozen=True)
class InstallTarget:
    name: str
    describe: str
    action: str  # "write" or "paste"
    snippet_builder: Callable[[Path], str]
    config_path_resolver: Callable[[], Path] | None = None


# ----------------------------------------------------------------------
# Snippet builders
# ----------------------------------------------------------------------


def _claude_code_settings_snippet(hook_path: Path) -> str:
    """Snippet for ~/.claude/settings.json hooks block."""
    block = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(hook_path),
                        }
                    ],
                }
            ]
        }
    }
    return json.dumps(block, indent=2)


def _generic_command_snippet(hook_path: Path) -> str:
    """Snippet for hosts that take a 'run this script after every tool' line."""
    return f"# Add this script to your client's post-tool-use hook list:\n{hook_path}\n"


def _opencode_snippet(hook_path: Path) -> str:
    return (
        "# Opencode hook config (varies by version). Reference the script:\n"
        f"#   command: {hook_path}\n"
        "# See https://opencode.app/docs/hooks for the current schema.\n"
    )


# ----------------------------------------------------------------------
# Config path resolvers (for action=write targets)
# ----------------------------------------------------------------------


def _claude_code_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


INSTALL_TARGETS: dict[str, InstallTarget] = {
    "claude-code": InstallTarget(
        name="claude-code",
        describe="Claude Code CLI — merge PostToolUse hook into ~/.claude/settings.json",
        action="write",
        snippet_builder=_claude_code_settings_snippet,
        config_path_resolver=_claude_code_settings_path,
    ),
    "codex": InstallTarget(
        name="codex",
        describe="OpenAI Codex CLI — paste hook command into your Codex hook config",
        action="paste",
        snippet_builder=_generic_command_snippet,
    ),
    "cursor": InstallTarget(
        name="cursor",
        describe="Cursor IDE — paste advisory; first-class hook surface pending",
        action="paste",
        snippet_builder=_generic_command_snippet,
    ),
    "gemini-cli": InstallTarget(
        name="gemini-cli",
        describe="Gemini CLI — paste advisory; first-class hook surface pending",
        action="paste",
        snippet_builder=_generic_command_snippet,
    ),
    "opencode": InstallTarget(
        name="opencode",
        describe="Opencode — paste hook script reference into Opencode hook config",
        action="paste",
        snippet_builder=_opencode_snippet,
    ),
}


def list_install_targets() -> list[InstallTarget]:
    """Return all known targets sorted by name."""
    return sorted(INSTALL_TARGETS.values(), key=lambda t: t.name)


# ----------------------------------------------------------------------
# Plan construction
# ----------------------------------------------------------------------


@dataclass
class InstallPlan:
    target: str
    action: str  # "write" or "paste"
    hook_path: Path
    snippet: str
    config_path: Path | None
    note: str | None = None


class InstallTargetUnknown(KeyError):
    """Raised when an unknown ``--target=...`` value is supplied."""


def build_install_plan(
    target: str,
    *,
    adapters_root: Path | None = None,
) -> InstallPlan:
    """Compute the action engram would take for ``--target=<target>``."""
    if target not in INSTALL_TARGETS:
        raise InstallTargetUnknown(
            f"unknown observer install target {target!r}; "
            f"known: {sorted(INSTALL_TARGETS.keys())}"
        )
    spec = INSTALL_TARGETS[target]
    hook_path = hook_script_path(target, adapters_root=adapters_root)
    snippet = spec.snippet_builder(hook_path)
    config_path = (
        spec.config_path_resolver() if spec.config_path_resolver is not None else None
    )
    note: str | None = None
    if not hook_path.exists():
        note = (
            f"hook script not found at {hook_path}. The script ships with the "
            "engram repo under adapters/<client>/hooks/. Make sure your engram "
            "checkout includes adapters/."
        )
    return InstallPlan(
        target=target,
        action=spec.action,
        hook_path=hook_path,
        snippet=snippet,
        config_path=config_path,
        note=note,
    )


# ----------------------------------------------------------------------
# Apply (write mode only — paste mode is print-only)
# ----------------------------------------------------------------------


def apply_install_plan(
    plan: InstallPlan,
    *,
    dry_run: bool = False,
) -> None:
    """For action=write targets, atomically merge the snippet into the config.

    Idempotent: re-running over the same target leaves the config
    unchanged. Paste-mode targets are no-ops here; the CLI surfaces
    the snippet to stdout.

    First-write backup (code reviewer C5, 2026-04-30): on the first
    invocation that touches an existing config file we drop a
    ``<name>.engram-bak`` sibling so an operator can restore manually
    if the merge ever does the wrong thing. Backups never overwrite —
    the first one wins so we never overwrite the user's pristine copy.
    """
    if plan.action != "write":
        return
    if plan.config_path is None:
        raise ValueError(
            f"install target {plan.target!r} is action=write but has no config_path"
        )
    if dry_run:
        return

    from contextlib import suppress

    plan.config_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.config_path.exists():
        original_text = plan.config_path.read_text(encoding="utf-8")
        backup_path = plan.config_path.with_suffix(
            plan.config_path.suffix + ".engram-bak"
        )
        if not backup_path.exists():
            # Backup is best-effort: failure must not stop install.
            with suppress(OSError):
                backup_path.write_text(original_text, encoding="utf-8")
        existing = json.loads(original_text or "{}")
    else:
        existing = {}

    if plan.target == "claude-code":
        merged = _merge_claude_code_settings(dict(existing), plan.hook_path)
    else:  # pragma: no cover — defensive: future targets must have a merger
        raise NotImplementedError(
            f"no merger registered for write target {plan.target}"
        )

    serialised = json.dumps(merged, indent=2) + "\n"
    # Atomic write via tempfile + rename.
    from engram.core.fs import write_atomic

    write_atomic(plan.config_path, serialised)


class HooksMergeError(RuntimeError):
    """Existing settings.json has a structure incompatible with the merge."""


def _merge_claude_code_settings(
    existing: dict[str, Any], hook_path: Path
) -> dict[str, Any]:
    """Idempotent merge of an engram PostToolUse hook into Claude settings.

    Security reviewer F6 — refuse to merge into a non-dict ``hooks``
    block or a non-list ``hooks.PostToolUse``. Silently overwriting
    user customisation was a real config-loss risk.
    """
    hooks_obj = existing.get("hooks")
    if hooks_obj is None:
        hooks_obj = {}
        existing["hooks"] = hooks_obj
    elif not isinstance(hooks_obj, dict):
        raise HooksMergeError(
            f"settings.json 'hooks' is {type(hooks_obj).__name__}, expected object; "
            "refusing to overwrite. Move it manually or use --dry-run + paste."
        )

    post_list = hooks_obj.get("PostToolUse")
    if post_list is None:
        post_list = []
        hooks_obj["PostToolUse"] = post_list
    elif not isinstance(post_list, list):
        raise HooksMergeError(
            f"settings.json 'hooks.PostToolUse' is {type(post_list).__name__}, "
            "expected list; refusing to overwrite."
        )

    target_command = _build_claude_code_command(hook_path)
    # Already present? Bail. We compare both the new pinned form AND
    # the legacy bare-script form so re-installs upgrade cleanly.
    bare_command = str(hook_path)
    for entry in post_list:
        if not isinstance(entry, dict):
            continue
        for sub in entry.get("hooks", []):
            if not isinstance(sub, dict):
                continue
            cmd = sub.get("command")
            if cmd in (target_command, bare_command):
                # Upgrade legacy entries in place to the pinned form.
                if cmd == bare_command and cmd != target_command:
                    sub["command"] = target_command
                return existing

    post_list.append(
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": target_command}
            ],
        }
    )
    return existing


def _build_claude_code_command(hook_path: Path) -> str:
    """Produce a hook command line that pins the engram binary.

    Security reviewer F7 — ``command -v engram`` inside the hook script
    resolves against ``$PATH`` at fire time. A malicious project bin
    dir could shadow our binary; pinning the absolute path closes that
    window. Falls back to the bare script when ``shutil.which`` cannot
    locate engram (development checkouts).
    """
    engram_bin = shutil.which("engram")
    if engram_bin:
        return f"ENGRAM_BIN={engram_bin} {hook_path}"
    return str(hook_path)
