"""``engram review`` — project health summary aggregated from validate + graph.db.

Unlike ``engram validate`` (which is binary pass/fail with CI-friendly exit
codes), ``review`` is an informational dashboard: asset inventory + validation
issues grouped by severity and category. Always exits 0 so ``review`` can run
in CI jobs that only want a health snapshot without failing on warnings.

M2 scope: counts from the graph.db assets table + pass-through of
:func:`engram.commands.validate.run_validate`. M4.5 adds benchmark signals;
M5 adds workflow metrics; M6 adds KB staleness + inbox unread. Those
consumers slot into the ``Review`` dataclass as additional fields.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import click

from engram.commands.memory import graph_db_path
from engram.commands.validate import Issue, run_validate
from engram.config_types import GlobalConfig
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir

__all__ = ["Review", "render_json", "render_text", "review_cmd", "run_review"]


@dataclass(frozen=True, slots=True)
class Review:
    issues: list[Issue]
    total_assets: int
    by_subtype: dict[str, int]
    by_lifecycle: dict[str, int]
    by_severity: dict[str, int]
    by_category: dict[str, int] = field(default_factory=dict)


def _category_of(code: str) -> str:
    # `E-FM-001` → `FM`; `W-STR-002` → `STR`.
    parts = code.split("-")
    return parts[1] if len(parts) >= 3 else "UNKNOWN"


def run_review(project_root: Path) -> Review:
    issues = run_validate(project_root)

    by_subtype: dict[str, int] = {}
    by_lifecycle: dict[str, int] = {}
    total = 0

    db_path = graph_db_path(project_root)
    # graph.db may not exist on an un-inited project; run_validate will surface
    # the structural error separately. Only count when memory_dir exists AND the
    # db file is present.
    if memory_dir(project_root).is_dir() and db_path.exists():
        with open_graph_db(db_path) as conn:
            rows = conn.execute(
                "SELECT subtype, lifecycle_state FROM assets WHERE kind='memory'"
            ).fetchall()
        by_subtype = dict(Counter(r["subtype"] for r in rows))
        by_lifecycle = dict(Counter(r["lifecycle_state"] for r in rows))
        total = len(rows)

    by_severity = dict(Counter(i.severity for i in issues))
    by_category = dict(Counter(_category_of(i.code) for i in issues))

    return Review(
        issues=issues,
        total_assets=total,
        by_subtype=by_subtype,
        by_lifecycle=by_lifecycle,
        by_severity=by_severity,
        by_category=by_category,
    )


def render_text(report: Review) -> str:
    lines: list[str] = []
    lines.append("engram review — health summary")
    lines.append("=" * 32)
    lines.append("")

    lines.append("Assets")
    lines.append(f"  Total: {report.total_assets}")
    if report.by_subtype:
        subtypes = ", ".join(f"{k}={v}" for k, v in sorted(report.by_subtype.items()))
        lines.append(f"  By subtype:   {subtypes}")
    if report.by_lifecycle:
        lifecycles = ", ".join(f"{k}={v}" for k, v in sorted(report.by_lifecycle.items()))
        lines.append(f"  By lifecycle: {lifecycles}")
    lines.append("")

    lines.append(
        f"Validation issues ({report.by_severity.get('error', 0)} errors, "
        f"{report.by_severity.get('warning', 0)} warnings, "
        f"{report.by_severity.get('info', 0)} info)"
    )
    if report.by_category:
        lines.append(
            "  By category: " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_category.items()))
        )

    for severity in ("error", "warning", "info"):
        sev_issues = [i for i in report.issues if i.severity == severity]
        if not sev_issues:
            continue
        lines.append(f"  {severity.upper()}:")
        for i in sev_issues:
            lines.append(f"    {i.code:<12s} {i.file}")
            lines.append(f"      {i.message}")

    return "\n".join(lines)


def render_json(report: Review) -> str:
    payload = {
        "assets": {
            "total": report.total_assets,
            "by_subtype": report.by_subtype,
            "by_lifecycle": report.by_lifecycle,
        },
        "validation": {
            "by_severity": report.by_severity,
            "by_category": report.by_category,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "file": i.file,
                    "line": i.line,
                    "message": i.message,
                    "reference": i.reference,
                }
                for i in report.issues
            ],
        },
    }
    return json.dumps(payload)


@click.command("review")
@click.pass_obj
def review_cmd(cfg: GlobalConfig) -> None:
    """Print an aggregated project health summary. Always exits 0."""
    root = cfg.resolve_project_root()
    report = run_review(root)
    if cfg.output_format == "json":
        click.echo(render_json(report))
    else:
        click.echo(render_text(report))
