"""``engram context pack`` — Relevance-Gate-driven context assembly (T-56).

Builds a token-budgeted context pack for a given task description by
driving the Relevance Gate over the project's memory assets. Output
goes to stdout in one of three formats:

- ``prompt`` (default) — a compact system-prompt ready to pipe into an
  LLM. Mandatory assets first, ranked tail follows.
- ``json`` — structured for programmatic consumption (MCP server /
  SDKs); carries ``included`` / ``excluded`` / ``mandatory`` with
  scores.
- ``markdown`` — human-readable preview; what ``engram review --simulate``
  would show if we had a simulate flag.

This is the user-facing demo of the Relevance Gate. Without it, the
Gate is library-only; with it, a user can ``engram context pack ... |
ollama run ...`` on day one.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import click

from engram.cli import GlobalConfig
from engram.commands.memory import graph_db_path
from engram.core.frontmatter import FrontmatterError, parse_file
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.relevance.gate import (
    Asset,
    RelevanceRequest,
    RelevanceResult,
    run_relevance_gate,
)

__all__ = ["context_cmd"]


_DEFAULT_BUDGET = 4000
_VALID_FORMATS = ("prompt", "json", "markdown")


def _load_assets(project_root: Path) -> list[Asset]:
    mem = memory_dir(project_root)
    with open_graph_db(graph_db_path(project_root)) as conn:
        rows = conn.execute(
            "SELECT id, path FROM assets WHERE kind = 'memory'"
        ).fetchall()

    assets: list[Asset] = []
    for r in rows:
        path = mem / r["path"]
        if not path.exists():
            continue
        try:
            fm, body = parse_file(path)
        except FrontmatterError:
            continue
        size = path.stat().st_size
        assets.append(
            Asset(
                id=r["id"],
                scope=fm.scope.value,
                enforcement=fm.enforcement.value,
                subscribed_at=fm.subscribed_at,
                body=body,
                updated=fm.updated or date.today(),
                size_bytes=size,
            )
        )
    return assets


def _render_prompt(result: RelevanceResult, task: str) -> str:
    lines: list[str] = [
        "# Context pack",
        "",
        f"Task: {task}",
        "",
    ]
    if result.mandatory:
        lines.append("## Mandatory rules")
        lines.append("")
        for a in result.mandatory:
            lines.append(f"### {a.id}")
            lines.append("")
            lines.append(a.body.strip())
            lines.append("")
    if result.included:
        lines.append("## Ranked memories")
        lines.append("")
        for c in result.included:
            lines.append(f"### {c.asset.id}  (score={c.final_score:.2f})")
            lines.append("")
            lines.append(c.asset.body.strip())
            lines.append("")
    if not result.mandatory and not result.included:
        lines.append("_(no memories matched the query within the budget)_")
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown(result: RelevanceResult, task: str, budget: int) -> str:
    lines: list[str] = [
        f"# `engram context pack` preview — task: {task!r}",
        "",
        f"- budget: {budget} tokens",
        f"- used: {result.total_tokens} tokens",
        f"- mandatory: {len(result.mandatory)}",
        f"- ranked included: {len(result.included)}",
        f"- excluded due to budget: {len(result.excluded_due_to_budget)}",
        "",
        "## Mandatory (Stage 1 bypass)",
        "",
    ]
    if result.mandatory:
        for a in result.mandatory:
            lines.append(f"- `{a.id}` · scope={a.scope} · enforcement=mandatory")
    else:
        lines.append("_(none)_")
    lines.extend(["", "## Ranked included", ""])
    if result.included:
        for c in result.included:
            lines.append(
                f"- `{c.asset.id}` · score={c.final_score:.3f} "
                f"(bm25={c.bm25:.2f} · scope x{c.scope_weight} · "
                f"enf x{c.enforcement_weight}) · ~{c.tokens_est} tokens"
            )
    else:
        lines.append("_(none)_")
    if result.excluded_due_to_budget:
        lines.extend(["", "## Excluded — budget tail", ""])
        for c in result.excluded_due_to_budget:
            lines.append(
                f"- `{c.asset.id}` · score={c.final_score:.3f} · "
                f"~{c.tokens_est} tokens"
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_json(result: RelevanceResult, task: str, budget: int) -> str:
    payload: dict[str, Any] = {
        "task": task,
        "budget": budget,
        "total_tokens": result.total_tokens,
        "mandatory": [
            {"id": a.id, "scope": a.scope, "enforcement": a.enforcement}
            for a in result.mandatory
        ],
        "included": [
            {
                "id": c.asset.id,
                "score": round(c.final_score, 4),
                "bm25": round(c.bm25, 4),
                "scope": c.asset.scope,
                "enforcement": c.asset.enforcement,
                "tokens_est": c.tokens_est,
            }
            for c in result.included
        ],
        "excluded_due_to_budget": [
            {"id": c.asset.id, "tokens_est": c.tokens_est}
            for c in result.excluded_due_to_budget
        ],
    }
    return json.dumps(payload)


@click.group("context")
def context_cmd() -> None:
    """Assemble and preview context packs (DESIGN §5.1, §6.3)."""


@context_cmd.command("pack")
@click.option(
    "--task",
    required=True,
    metavar="TEXT",
    help="Task description — used as the Relevance Gate query.",
)
@click.option(
    "--budget",
    default=_DEFAULT_BUDGET,
    show_default=True,
    type=int,
    help="Token budget for the pack (DESIGN §5.1 Stage 6).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_VALID_FORMATS),
    default="prompt",
    show_default=True,
    help="Output format: prompt (default), json, markdown.",
)
@click.pass_obj
def pack_cmd(
    cfg: GlobalConfig,
    task: str,
    budget: int,
    output_format: str,
) -> None:
    """Run the Relevance Gate against ``task`` and emit the pack to stdout."""
    root = cfg.resolve_project_root()
    assets = _load_assets(root)
    req = RelevanceRequest(
        query=task,
        assets=tuple(assets),
        budget_tokens=budget,
        now=date.today(),
    )
    result = run_relevance_gate(req)

    # Global --format overrides the per-command --format when user asked
    # for global JSON (stay consistent with other subcommands).
    if cfg.output_format == "json":
        output_format = "json"

    if output_format == "json":
        click.echo(_render_json(result, task, budget))
    elif output_format == "markdown":
        click.echo(_render_markdown(result, task, budget))
    else:  # prompt
        click.echo(_render_prompt(result, task))
