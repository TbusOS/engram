"""``engram observer ...`` CLI subgroup.

Hosts every operational observer command behind one namespace:

- ``engram observer install --target=...`` — wire client hooks (T-205).
- ``engram observer daemon [--foreground] [--once]`` — run the
  Tier 0/1 processing loop (Q2 in production-readiness audit).
- ``engram observer status`` — quick health snapshot.

The hot path ``engram observe`` (queue append) stays at the top level
because hook scripts shell out to it. Everything else lives here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from engram.observer.install import (
    INSTALL_TARGETS,
    InstallTargetUnknown,
    apply_install_plan,
    build_install_plan,
    list_install_targets,
)

__all__ = ["observer_group"]


@click.group("observer", help="Operational commands for the observer pipeline.")
def observer_group() -> None:
    pass


@observer_group.command("install", help="Install observer hooks into a host client.")
@click.option(
    "--target",
    type=click.Choice(sorted(INSTALL_TARGETS.keys())),
    required=False,
    default=None,
    help="Which client to install for. Use --list to see all targets.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    default=False,
    help="List all install targets and exit.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned action without writing anything.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def install_cmd(
    target: str | None,
    list_only: bool,
    dry_run: bool,
    fmt: str,
) -> None:
    if list_only:
        _emit_list(fmt)
        return

    if target is None:
        click.echo(
            "error: provide --target or --list. See 'engram observer install --help'.",
            err=True,
        )
        sys.exit(2)

    try:
        plan = build_install_plan(target)
    except InstallTargetUnknown as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(
            json.dumps(
                {
                    "target": plan.target,
                    "action": plan.action,
                    "hook_path": str(plan.hook_path),
                    "config_path": (
                        str(plan.config_path) if plan.config_path is not None else None
                    ),
                    "note": plan.note,
                    "dry_run": dry_run,
                    "snippet": plan.snippet,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"target:      {plan.target}")
        click.echo(f"action:      {plan.action}")
        click.echo(f"hook script: {plan.hook_path}")
        if plan.config_path is not None:
            click.echo(f"config:      {plan.config_path}")
        if plan.note:
            click.echo(f"note:        {plan.note}")
        click.echo("--- snippet ---")
        click.echo(plan.snippet.rstrip("\n"))
        click.echo("--- end ---")

    if plan.action == "write":
        apply_install_plan(plan, dry_run=dry_run)
        if not dry_run:
            click.echo(f"wrote: {plan.config_path}")
        else:
            click.echo("(dry-run; nothing written)")


def _emit_list(fmt: str) -> None:
    rows = [
        {"name": t.name, "action": t.action, "describe": t.describe}
        for t in list_install_targets()
    ]
    if fmt == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            click.echo(f"  {row['name']:<14} [{row['action']}]  {row['describe']}")


# ----------------------------------------------------------------------
# engram observer daemon (Q2)
# ----------------------------------------------------------------------


@observer_group.command(
    "daemon",
    help="Run the observer processing loop (Tier 0 + Tier 1).",
)
@click.option(
    "--foreground",
    is_flag=True,
    default=False,
    help=(
        "Run in the current terminal instead of returning. Default behaviour "
        "matches --foreground today; the flag is reserved so detach mode "
        "(double-fork) can be added later without breaking scripts."
    ),
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Run a single tick and exit. Useful for cron / smoke tests.",
)
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="Stop after N iterations (testing aid). Mutually exclusive with --once.",
)
@click.option(
    "--poll-interval",
    type=float,
    default=None,
    help="Seconds between ticks (default: DaemonConfig.poll_interval_seconds).",
)
@click.option(
    "--idle-threshold",
    type=float,
    default=None,
    help=(
        "Seconds a session must be quiet before Tier 1 fires "
        "(default: DaemonConfig.session_idle_threshold_seconds)."
    ),
)
@click.option(
    "--project-root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help=(
        "Write Session assets under <project>/.memory/sessions/ instead of "
        "the user-global ~/.engram/sessions/."
    ),
)
@click.option(
    "--no-pid-lock",
    is_flag=True,
    default=False,
    hidden=True,
    help="Skip the singleton PID lock — for tests and unsupervised wrappers.",
)
@click.option(
    "--base",
    "base_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    hidden=True,
    help="Override ~/.engram for tests.",
)
def daemon_cmd(
    foreground: bool,
    once: bool,
    max_iterations: int | None,
    poll_interval: float | None,
    idle_threshold: float | None,
    project_root: Path | None,
    no_pid_lock: bool,
    base_dir: Path | None,
) -> None:
    """``engram observer daemon`` — run the processing loop.

    Q2 in the 2026-04-29 production-readiness audit: previously
    ``ObserverDaemon`` existed but had no CLI, so users could not
    actually start it. This command resolves that gap.
    """
    from engram.observer.daemon import (
        DaemonConfig,
        ObserverDaemon,
        SingletonLock,
        SingletonLockError,
    )
    from engram.observer.runners import make_tier0_runner, make_tier1_runner

    config_kwargs: dict[str, float | int | None] = {}
    if poll_interval is not None:
        config_kwargs["poll_interval_seconds"] = poll_interval
    if idle_threshold is not None:
        config_kwargs["session_idle_threshold_seconds"] = idle_threshold
    if once:
        if max_iterations not in (None, 1):
            raise click.UsageError(
                "--once and --max-iterations are mutually exclusive"
            )
        config_kwargs["max_iterations"] = 1
    elif max_iterations is not None:
        config_kwargs["max_iterations"] = max_iterations
    config = DaemonConfig(**config_kwargs)  # type: ignore[arg-type]

    tier0 = make_tier0_runner(base=base_dir)
    tier1 = make_tier1_runner(
        base=base_dir,
        project_root=project_root,
    )
    daemon = ObserverDaemon(
        config=config,
        base=base_dir,
        tier0_runner=tier0,
        tier1_runner=tier1,
    )

    install_signals = not once and foreground

    if no_pid_lock:
        click.echo("observer daemon: starting (no PID lock)")
        stats = daemon.run_forever(install_signals=install_signals)
    else:
        try:
            with SingletonLock(base=base_dir):
                click.echo("observer daemon: started")
                stats = daemon.run_forever(install_signals=install_signals)
        except SingletonLockError as exc:
            click.echo(f"error: {exc}", err=True)
            sys.exit(75)  # EX_TEMPFAIL — try again later

    click.echo(
        f"observer daemon: stopped after {stats.iterations} iteration(s); "
        f"tier0={stats.tier0_invocations}, tier1={stats.tier1_invocations}, "
        f"sessions_seen={stats.pending_sessions_seen}"
    )


# ----------------------------------------------------------------------
# engram observer status (read-only health snapshot)
# ----------------------------------------------------------------------


@observer_group.command(
    "status", help="Show observer queue + daemon health snapshot."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option(
    "--base",
    "base_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    hidden=True,
)
def status_cmd(fmt: str, base_dir: Path | None) -> None:
    from engram.core.paths import user_root
    from engram.observer.daemon import scan_pending_sessions
    from engram.observer.paths import OBSERVER_PID_FILE

    base = base_dir if base_dir is not None else user_root()
    pid_path = base / OBSERVER_PID_FILE
    pid_alive = False
    pid_value: int | None = None
    if pid_path.exists():
        try:
            pid_value = int(pid_path.read_text().split()[0])
            try:
                import os as _os

                _os.kill(pid_value, 0)
                pid_alive = True
            except ProcessLookupError:
                pid_alive = False
            except PermissionError:
                pid_alive = True
        except (OSError, ValueError):
            pid_value = None

    pending = list(scan_pending_sessions(base=base_dir))
    pending_rows = [
        {
            "session_id": p.session_id,
            "queue_size_bytes": p.queue_size_bytes,
        }
        for p in pending
    ]

    # Code reviewer C1 — surface tier errors in status so operators
    # know when something is silently degrading to mechanical mode.
    last_error = _read_last_journal_error(base / "journal" / "observer.jsonl")

    payload = {
        "observer_pid_file": str(pid_path),
        "observer_pid": pid_value,
        "observer_alive": pid_alive,
        "pending_sessions": pending_rows,
        "pending_count": len(pending_rows),
        "last_error": last_error,
    }
    if fmt == "json":
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    click.echo(f"observer pid file:  {pid_path}")
    click.echo(f"observer pid:       {pid_value if pid_value else '(none)'}")
    click.echo(f"observer alive:     {pid_alive}")
    click.echo(f"pending sessions:   {len(pending_rows)}")
    if last_error is not None:
        click.echo(
            f"last error:         {last_error['t']} {last_error['tier']} "
            f"{last_error['session_id']} {last_error['error_type']}"
        )
    for row in pending_rows[:10]:
        click.echo(f"  - {row['session_id']}  ({row['queue_size_bytes']} bytes)")


def _read_last_journal_error(path: Path) -> dict[str, Any] | None:
    """Return the most-recent line from the observer error journal."""
    if not path.is_file():
        return None
    try:
        # Cheap "tail -1" without reading the whole file: jump near EOF.
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="replace")
        last_line = next(
            (ln for ln in reversed(tail.splitlines()) if ln.strip()),
            None,
        )
        if last_line is None:
            return None
        parsed = json.loads(last_line)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, ValueError):
        return None
