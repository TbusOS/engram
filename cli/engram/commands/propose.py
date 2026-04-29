"""``engram propose`` — consent gate for Tier 3 procedural proposals.

T-210. Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §8.2.

Tier 3 (T-210) writes ``workflows/<slug>/proposal.md`` files. Those
files do NOT yet have spine, fixtures, metrics, or rev/. They are
**seeds** — the user (or LLM) reads the proposal, decides if the
procedure is worth codifying, and runs ``engram propose promote``,
which produces the minimum Workflow scaffold around the seed.

- ``engram propose review`` lists pending proposals.
- ``engram propose promote <name>`` keeps the proposal in place,
  renames it from ``proposal.md`` to ``README.md`` (the canonical
  Workflow document), and adds an empty ``spine.toml``,
  ``fixtures/`` directory, and ``metrics.yaml`` so the Workflow is
  spine-runnable as soon as the user fills the spine in.
- ``engram propose reject <name>`` archives the whole workflow
  directory under ``~/.engram/archive/workflows/<YYYY-MM>/<slug>.<ts>[-reason]/``.

LLMs can consent the same way they consent to ``engram distill
promote`` — running the command counts as a deliberate action.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

import click
import yaml

from engram.config_types import GlobalConfig
from engram.core.fs import write_atomic
from engram.core.paths import find_project_root, memory_dir, user_root

__all__ = ["propose_group"]


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def _workflows_dir(mem: Path) -> Path:
    return mem / "workflows"


def _archive_dir() -> Path:
    return user_root() / "archive" / "workflows"


def _read_proposal(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise click.ClickException(f"{path}: missing leading frontmatter")
    rest = text[4:]
    end = rest.find("\n---\n")
    if end < 0:
        raise click.ClickException(f"{path}: missing closing frontmatter")
    fm_text = rest[:end]
    body = rest[end + len("\n---\n") :]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        raise click.ClickException(f"{path}: YAML parse error: {exc}") from exc
    if not isinstance(fm, dict):
        raise click.ClickException(f"{path}: frontmatter must be a mapping")
    return fm, body


def _list_proposals(mem: Path) -> list[Path]:
    root = _workflows_dir(mem)
    if not root.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        candidate = child / "proposal.md"
        if candidate.exists():
            out.append(candidate)
    return out


# ----------------------------------------------------------------------
# review
# ----------------------------------------------------------------------


@click.group("propose", help="Consent gate for Tier 3 procedural proposals.")
def propose_group() -> None:
    pass


@propose_group.command("review", help="List pending Workflow proposals.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.pass_obj
def review_cmd(_cfg: GlobalConfig, fmt: str) -> None:
    project = find_project_root()
    mem = memory_dir(project)
    rows: list[dict[str, Any]] = []
    for path in _list_proposals(mem):
        try:
            fm, _ = _read_proposal(path)
        except click.ClickException:
            continue
        rows.append(
            {
                "name": fm.get("name") or path.parent.name,
                "type": fm.get("type", "workflow_proposal"),
                "source_sessions": list(fm.get("source_sessions", []) or []),
                "path": str(path),
                "directory": str(path.parent),
            }
        )

    if fmt == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    if not rows:
        click.echo("(no Workflow proposals pending review)")
        return

    click.echo(f"{len(rows)} proposal(s) under {_workflows_dir(mem)}:")
    for row in rows:
        sources = ", ".join(row["source_sessions"]) or "(none)"
        click.echo(f"  {row['name']}")
        click.echo(f"    sources: {sources}")
        click.echo(f"    file:    {row['path']}")


# ----------------------------------------------------------------------
# promote
# ----------------------------------------------------------------------


_SPINE_PLACEHOLDER = """\
# engram Workflow spine — fill in before running.
# Spec: SPEC.md §6.

[meta]
name = "{name}"
description = "Promoted from Tier 3 proposal — fill in steps before invoking."

# Each step is a [[step]] entry with `id` + one executor field
# (`bash`, `python`, or `note`). Sketch your procedure here, then run
# `engram workflow run {name} --dry-run` once T-71 lands.

# [[step]]
# id = "step-1"
# note = "Describe what this step does."
"""


_METRICS_PLACEHOLDER = """\
# Outcome metrics for this Workflow — wire to fixture results once
# you author the spine. SPEC §6.

attempts: 0
completions: 0
last_completion: null
"""


@propose_group.command(
    "promote",
    help="Promote a Workflow proposal to a real Workflow scaffold.",
)
@click.argument("name")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned action without writing any file.",
)
@click.pass_obj
def promote_cmd(_cfg: GlobalConfig, name: str, dry_run: bool) -> None:
    project = find_project_root()
    mem = memory_dir(project)
    wdir = _workflows_dir(mem) / name
    proposal = wdir / "proposal.md"
    if not proposal.exists():
        raise click.ClickException(
            f"no Workflow proposal named {name} under {_workflows_dir(mem)}; "
            "run 'engram propose review'."
        )

    readme = wdir / "README.md"
    spine = wdir / "spine.toml"
    fixtures = wdir / "fixtures"
    metrics = wdir / "metrics.yaml"

    click.echo(f"promote: {proposal} → {readme} (+ spine.toml + fixtures/ + metrics.yaml)")
    if dry_run:
        click.echo("(dry-run; nothing written)")
        return

    fm, body = _read_proposal(proposal)
    fm["type"] = "workflow"
    fm["updated"] = date.today().isoformat()
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.endswith("\n"):
        body = body + "\n"
    write_atomic(readme, f"---\n{yaml_text}---\n{body}")
    proposal.unlink()

    if not spine.exists():
        write_atomic(spine, _SPINE_PLACEHOLDER.format(name=name))
    if not metrics.exists():
        write_atomic(metrics, _METRICS_PLACEHOLDER)
    fixtures.mkdir(parents=True, exist_ok=True)
    fixtures_keep = fixtures / ".gitkeep"
    if not fixtures_keep.exists():
        fixtures_keep.write_text("")

    click.echo(f"wrote: {readme}")


# ----------------------------------------------------------------------
# reject
# ----------------------------------------------------------------------


_SLUG_BAD = re.compile(r"[^a-z0-9]+")


def _slug_reason(reason: str | None) -> str:
    if not reason:
        return "rejected"
    s = _SLUG_BAD.sub("-", reason.lower()).strip("-")
    return (s or "rejected")[:48]


@propose_group.command(
    "reject",
    help="Archive a Workflow proposal directory under ~/.engram/archive/.",
)
@click.argument("name")
@click.option(
    "--reason",
    default=None,
    help="Free-text reason recorded in the archive directory name.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned action without moving any file.",
)
@click.pass_obj
def reject_cmd(
    _cfg: GlobalConfig, name: str, reason: str | None, dry_run: bool
) -> None:
    project = find_project_root()
    mem = memory_dir(project)
    src = _workflows_dir(mem) / name
    proposal = src / "proposal.md"
    if not proposal.exists():
        raise click.ClickException(
            f"no Workflow proposal named {name} under {_workflows_dir(mem)}; "
            "run 'engram propose review'."
        )

    today = date.today()
    bucket = _archive_dir() / today.strftime("%Y-%m")
    suffix = f"-{_slug_reason(reason)}" if reason else ""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = bucket / f"{name}.{ts}{suffix}"

    click.echo(f"reject: {src} → {dest}")
    if dry_run:
        click.echo("(dry-run; nothing moved)")
        return

    bucket.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    click.echo(f"archived: {dest}")
