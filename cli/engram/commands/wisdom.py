"""``engram wisdom`` — read-only views into the 6 wisdom curves."""

from __future__ import annotations

import json
from pathlib import Path

import click

from engram.config_types import GlobalConfig
from engram.wisdom import compute_wisdom_report
from engram.wisdom.ascii_render import render_text


__all__ = ["wisdom_cmd"]


@click.group("wisdom")
def wisdom_cmd() -> None:
    """6 wisdom curves rendered from the usage event bus.

    Today: ASCII / Unicode-block sparklines (pre-M7 web UI). Run after
    accumulating a few days of activity to see the trends move.
    """


@wisdom_cmd.command("report")
@click.option(
    "--days",
    type=int,
    default=7,
    show_default=True,
    help="Time window for the curves (days).",
)
@click.pass_obj
def report_cmd(cfg: GlobalConfig, days: int) -> None:
    """Print a wisdom report for the current store."""
    target = (
        cfg.dir_override.expanduser().resolve() if cfg.dir_override else Path.cwd()
    )
    report = compute_wisdom_report(target, days=days)

    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "store_root": report.store_root,
                    "period_days": report.period_days,
                    "generated_at": report.generated_at,
                    "curves": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "unit": c.unit,
                            "summary": c.summary,
                            "insufficient": c.insufficient,
                            "samples": [
                                {"day": s.day, "value": s.value}
                                for s in c.samples
                            ],
                        }
                        for c in report.curves
                    ],
                }
            )
        )
        return

    click.echo(render_text(report))
