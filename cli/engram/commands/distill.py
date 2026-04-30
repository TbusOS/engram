"""``engram distill`` — consent gate for Tier 2 distilled candidates.

T-209. Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §8.1.

Tier 2 (T-208) writes candidate Memory files to
``.memory/distilled/<name>.proposed.md``. Those files **never enter
the Relevance Gate** until the user — or an LLM agent acting on the
user's behalf — runs an explicit consent action:

- ``engram distill review`` lists candidates with their summary and
  source-session count.
- ``engram distill promote <name>`` moves the file from
  ``distilled/`` into ``local/``, making it a real Memory asset.
  After this, the Relevance Gate / search / mandatory bypass can see
  it. Source sessions get a back-link via ``distilled_into``.
- ``engram distill reject <name>`` moves the file to
  ``~/.engram/archive/distilled/<YYYY-MM>/`` so it never re-appears
  but is preserved per SPEC §1.2 6-month retention floor.

LLMs are first-class consenters here. ``engram distill promote`` does
not require a TTY — running it from a hook / subagent counts as a
deliberate action because the LLM had to write the command. SPEC §1.2
principle 4 requires *deliberate action*, not human eyeballs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import click
import yaml

from engram.config_types import GlobalConfig
from engram.core.fs import write_atomic
from engram.core.paths import find_project_root, memory_dir, user_root

__all__ = ["distill_group"]


# Security reviewer F3 — `<name>` arrives from CLI / LLM hooks. A
# slug-shaped regex prevents path-traversal joins like
# ``.memory/distilled/../../etc/foo.proposed.md``.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise click.ClickException(
            f"invalid name {name!r}; must match {_NAME_RE.pattern}"
        )
    return name


# ----------------------------------------------------------------------
# Path helpers
# ----------------------------------------------------------------------


def _distilled_dir(mem: Path) -> Path:
    return mem / "distilled"


def _local_dir(mem: Path) -> Path:
    return mem / "local"


def _archive_dir() -> Path:
    return user_root() / "archive" / "distilled"


def _list_candidates(mem: Path) -> list[Path]:
    d = _distilled_dir(mem)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.proposed.md") if p.is_file())


def _read_frontmatter_and_body(path: Path) -> tuple[dict[str, Any], str]:
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


def _write_frontmatter_and_body(
    path: Path, fm: dict[str, Any], body: str
) -> None:
    yaml_text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.endswith("\n"):
        body = body + "\n"
    write_atomic(path, f"---\n{yaml_text}---\n{body}")


# ----------------------------------------------------------------------
# Group + review
# ----------------------------------------------------------------------


@click.group("distill", help="Consent gate for Tier 2 distilled candidates.")
def distill_group() -> None:
    pass


@distill_group.command("review", help="List distilled candidates awaiting consent.")
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
    for path in _list_candidates(mem):
        try:
            fm, _ = _read_frontmatter_and_body(path)
        except click.ClickException:
            continue
        rows.append(
            {
                "name": fm.get("name") or path.stem.replace(".proposed", ""),
                "description": fm.get("description", ""),
                "source_sessions": list(fm.get("source_sessions", []) or []),
                "scope": fm.get("scope", "project"),
                "enforcement": fm.get("enforcement", "hint"),
                "path": str(path),
            }
        )

    if fmt == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    if not rows:
        click.echo("(no distilled candidates pending review)")
        return

    click.echo(f"{len(rows)} candidate(s) under {_distilled_dir(mem)}:")
    for row in rows:
        sources = ", ".join(row["source_sessions"]) or "(none)"
        click.echo(f"  {row['name']}  [{row['enforcement']}/{row['scope']}]")
        click.echo(f"    {row['description']}")
        click.echo(f"    sources: {sources}")


# ----------------------------------------------------------------------
# Promote
# ----------------------------------------------------------------------


@distill_group.command(
    "promote",
    help="Promote a distilled candidate to a real Memory asset (consent required).",
)
@click.argument("name")
@click.option(
    "--scope",
    type=click.Choice(["project", "user", "team", "org"]),
    default=None,
    help="Override scope on promotion. Default: keep frontmatter value.",
)
@click.option(
    "--enforcement",
    type=click.Choice(["mandatory", "default", "hint"]),
    default=None,
    help="Override enforcement on promotion. Default: keep frontmatter value.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the planned action without moving any file.",
)
@click.pass_obj
def promote_cmd(
    _cfg: GlobalConfig,
    name: str,
    scope: str | None,
    enforcement: str | None,
    dry_run: bool,
) -> None:
    name = _validate_name(name)
    project = find_project_root()
    mem = memory_dir(project)
    src = _distilled_dir(mem) / f"{name}.proposed.md"
    if not src.exists():
        raise click.ClickException(
            f"no candidate named {name} under {_distilled_dir(mem)}; "
            "run 'engram distill review'."
        )

    fm, body = _read_frontmatter_and_body(src)
    if scope is not None:
        fm["scope"] = scope
    if enforcement is not None:
        fm["enforcement"] = enforcement
    fm["updated"] = date.today().isoformat()

    dest = _local_dir(mem) / f"{name}.md"

    click.echo(f"promote: {src} → {dest}")
    if dry_run:
        click.echo("(dry-run; nothing moved)")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    _write_frontmatter_and_body(dest, fm, body)
    src.unlink()

    # Best-effort back-link: stamp source sessions with distilled_into.
    sources = fm.get("source_sessions") or []
    if isinstance(sources, list):
        _stamp_source_sessions(project, sources, name)

    click.echo(f"wrote: {dest}")


def _stamp_source_sessions(
    project: Path, source_session_ids: Iterable[str], promoted_name: str
) -> None:
    """Append ``promoted_name`` to each source Session's ``distilled_into`` list.

    Best-effort: missing files / parse errors are skipped silently.
    The Session frontmatter format is fixed by SPEC §3.5; we read /
    write via the same helpers so the round-trip stays clean.
    """
    from engram.observer.session import (
        SessionFrontmatter,
        parse_session_file,
        render_session_file,
        sessions_root,
    )

    candidate_ids = {s for s in source_session_ids if isinstance(s, str)}
    if not candidate_ids:
        return

    roots: list[Path] = [
        sessions_root(memory_dir(project)),
        sessions_root(user_root()),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("sess_*.md"):
            # Security reviewer F5 — never follow symlinks; skip anything
            # that is not a real regular file.
            if not path.is_file() or path.is_symlink():
                continue
            try:
                fm, body = parse_session_file(path)
            except Exception:
                continue
            if fm.session_id not in candidate_ids:
                continue
            already = list(fm.distilled_into)
            if promoted_name in already:
                continue
            already.append(promoted_name)
            updated = SessionFrontmatter(
                type=fm.type,
                session_id=fm.session_id,
                client=fm.client,
                started_at=fm.started_at,
                ended_at=fm.ended_at,
                task_hash=fm.task_hash,
                tool_calls=fm.tool_calls,
                files_touched=fm.files_touched,
                files_modified=fm.files_modified,
                outcome=fm.outcome,
                error_summary=fm.error_summary,
                prev_session=fm.prev_session,
                next_session=fm.next_session,
                distilled_into=tuple(already),
                scope=fm.scope,
                enforcement=fm.enforcement,
                confidence=fm.confidence,
                extra=fm.extra,
            )
            try:
                write_atomic(path, render_session_file(updated, body))
            except OSError:
                continue


# ----------------------------------------------------------------------
# Reject
# ----------------------------------------------------------------------


@distill_group.command(
    "reject",
    help="Archive a distilled candidate. Preserves the file under ~/.engram/archive/.",
)
@click.argument("name")
@click.option(
    "--reason",
    default=None,
    help="Free-text reason recorded in the archive filename.",
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
    name = _validate_name(name)
    project = find_project_root()
    mem = memory_dir(project)
    src = _distilled_dir(mem) / f"{name}.proposed.md"
    if not src.exists():
        raise click.ClickException(
            f"no candidate named {name} under {_distilled_dir(mem)}; "
            "run 'engram distill review'."
        )

    today = date.today()
    bucket = _archive_dir() / today.strftime("%Y-%m")
    suffix = f"-{_slug_reason(reason)}" if reason else ""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = bucket / f"{name}.{ts}{suffix}.md"

    click.echo(f"reject: {src} → {dest}")
    if dry_run:
        click.echo("(dry-run; nothing moved)")
        return

    bucket.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    write_atomic(dest, text)
    src.unlink()
    click.echo(f"archived: {dest}")


def _slug_reason(reason: str | None) -> str:
    if not reason:
        return "rejected"
    import re as _re

    s = _re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")
    return (s or "rejected")[:48]
