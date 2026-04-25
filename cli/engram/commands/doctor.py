"""``engram doctor`` CLI — thin wrapper around ``engram.doctor.run_doctor``."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from engram.cli import GlobalConfig
from engram.doctor import (
    DEFAULT_MANDATORY_BUDGET_BYTES,
    DoctorReport,
    run_doctor,
)


__all__ = ["doctor_cmd"]


@click.command("doctor")
@click.option(
    "--mandatory-budget",
    "mandatory_budget_bytes",
    type=int,
    default=DEFAULT_MANDATORY_BUDGET_BYTES,
    show_default=True,
    help="Cumulative mandatory body-size budget (bytes). Override for "
    "small-context models or tighter limits.",
)
@click.pass_obj
def doctor_cmd(cfg: GlobalConfig, mandatory_budget_bytes: int) -> None:
    """Health check + executable repair hints for the current store.

    Distinct from ``engram validate`` (SPEC §12 contract) and ``engram
    review`` (SPEC §16 percentile signals). Every issue line ends with a
    ``→ run: <command>`` so the operator does not have to look up the fix.
    """
    target = (
        cfg.dir_override.expanduser().resolve()
        if cfg.dir_override
        else Path.cwd()
    )
    report = run_doctor(target, mandatory_budget_bytes=mandatory_budget_bytes)

    if cfg.output_format == "json":
        click.echo(_render_json(report))
    else:
        click.echo(_render_text(report))

    if report.has_errors() or report.issues:
        raise SystemExit(1 if report.has_errors() else 2 if report.issues else 0)


def _render_text(report: DoctorReport) -> str:
    if not report.issues:
        return "store is healthy — no issues found"
    lines = []
    lines.append(f"found {len(report.issues)} issue(s):")
    lines.append("")
    for issue in report.issues:
        sev_label = issue.severity.value.upper().ljust(7)
        prefix = f"[{sev_label}] {issue.code}"
        lines.append(f"  {prefix}: {issue.message}")
        lines.append(f"    → run: {issue.fix_command}")
        lines.append("")
    return "\n".join(lines)


def _render_json(report: DoctorReport) -> str:
    return json.dumps(
        {
            "is_healthy": report.is_healthy(),
            "has_errors": report.has_errors(),
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity.value,
                    "message": i.message,
                    "fix_command": i.fix_command,
                    "file": i.file,
                }
                for i in report.issues
            ],
        }
    )
