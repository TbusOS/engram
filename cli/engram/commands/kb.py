"""``engram kb`` — the Knowledge Base asset class CLI (SPEC §6).

Subcommands:

- ``new-article``  scaffold a KB article (README.md + first chapter).
- ``list``         list articles with lifecycle state + stale flag.
- ``read``         print the article README (text) or frontmatter (json).
- ``compile``      regenerate the ``_compiled.md`` digest (rule-based).
- ``compile --check``  staleness check only; flags drift, writes no digest.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import click

from engram.config_types import GlobalConfig
from engram.core.fs import write_atomic
from engram.kb.compiler import check_staleness, compile_article
from engram.kb.format import KbFormatError, parse_readme
from engram.kb.paths import (
    KB_README_NAME,
    kb_dir,
    kb_root,
    validate_topic_name,
)

__all__ = ["kb_group"]


def _topic_dir_or_fail(project: Path, topic: str) -> Path:
    try:
        topic = validate_topic_name(topic)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    tdir = kb_dir(project, topic)
    if not (tdir / KB_README_NAME).is_file():
        raise click.ClickException(
            f"no KB article named {topic!r} under {kb_root(project)}; "
            "run `engram kb list`."
        )
    return tdir


@click.group("kb", help="Knowledge Base asset class — reference articles (SPEC §6).")
def kb_group() -> None:
    pass


_README_TMPL = """\
---
name: {name}
description: {description}
type: kb
scope: {scope}
primary_author: {author}
chapters:
  - 01-overview.md
lifecycle_state: draft
---

## Abstract

What this article covers, its scope, and who the audience is (1-3
paragraphs).

## Table of contents

- [Overview](01-overview.md)

## When to read this

Load this article when the task involves {topic}. Write the trigger
conditions for an LLM — these are the primary signal the Relevance Gate
uses to decide whether to surface the full article.
"""

_CHAPTER_TMPL = """\
---
title: Overview
updated: {today}
---

# Overview

Write the first chapter here. Cross-link sibling chapters with relative
paths, reference Memory with `@memory:<id>` and Workflows with
`@workflow:<name>` (SPEC §6.3).
"""


@kb_group.command("new-article", help="Scaffold a new KB article.")
@click.argument("topic")
@click.option("--name", default=None, help="Article title (defaults to the topic).")
@click.option("--description", default="Reference article (<=150 chars).")
@click.option(
    "--scope",
    type=click.Choice(["project", "user"]),
    default="project",
    show_default=True,
    help="team/org/pool need a scope name; create those under their root directly.",
)
@click.option("--author", default="", help="Primary author handle/email.")
@click.pass_obj
def new_article_cmd(
    cfg: GlobalConfig, topic: str, name: str | None, description: str, scope: str, author: str
) -> None:
    project = cfg.resolve_project_root()
    try:
        topic = validate_topic_name(topic)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    tdir = kb_dir(project, topic, scope=scope)
    if tdir.exists():
        raise click.ClickException(f"KB article {topic!r} already exists at {tdir}")
    (tdir / "assets").mkdir(parents=True, exist_ok=True)
    write_atomic(
        tdir / KB_README_NAME,
        _README_TMPL.format(
            name=name or topic,
            description=description,
            scope=scope,
            author=author,
            topic=topic,
        ),
    )
    write_atomic(tdir / "01-overview.md", _CHAPTER_TMPL.format(today=date.today().isoformat()))
    click.echo(f"created KB article {topic} at {tdir}")
    click.echo(f"  edit chapters, then: engram kb compile {topic}")


@kb_group.command("list", help="List KB articles with lifecycle + stale flag.")
@click.pass_obj
def list_cmd(cfg: GlobalConfig) -> None:
    project = cfg.resolve_project_root()
    root = kb_root(project)
    rows: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            readme = child / KB_README_NAME
            if not readme.is_file() or child.is_symlink():
                continue
            try:
                fm, _ = parse_readme(readme)
            except KbFormatError:
                continue
            stale = (
                check_staleness(child).is_stale
                if (child / "_compile_state.toml").is_file()
                else None
            )
            rows.append(
                {
                    "topic": child.name,
                    "name": fm.name,
                    "lifecycle_state": fm.lifecycle_state,
                    "chapters": len(fm.chapters),
                    "stale": stale,
                }
            )
    if cfg.output_format == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        click.echo("(no KB articles; create one with `engram kb new-article <topic>`)")
        return
    for row in rows:
        flag = "  [STALE]" if row["stale"] else ""
        click.echo(f"  {row['topic']}  [{row['lifecycle_state']}, {row['chapters']} ch]{flag}")
        click.echo(f"    {row['name']}")


@kb_group.command("read", help="Print a KB article README (text) or frontmatter (json).")
@click.argument("topic")
@click.pass_obj
def read_cmd(cfg: GlobalConfig, topic: str) -> None:
    project = cfg.resolve_project_root()
    tdir = _topic_dir_or_fail(project, topic)
    fm, _ = parse_readme(tdir / KB_README_NAME)
    if cfg.output_format == "json":
        click.echo(json.dumps(fm.to_yaml_dict(), indent=2, ensure_ascii=False))
        return
    click.echo((tdir / KB_README_NAME).read_text(encoding="utf-8"))


@kb_group.command("compile", help="Regenerate the _compiled.md digest (rule-based).")
@click.argument("topic")
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Only check staleness; do not rewrite the digest.",
)
@click.pass_obj
def compile_cmd(cfg: GlobalConfig, topic: str, check: bool) -> None:
    project = cfg.resolve_project_root()
    tdir = _topic_dir_or_fail(project, topic)

    if check:
        report = check_staleness(tdir)
        payload = {
            "topic": topic,
            "is_stale": report.is_stale,
            "changed_files": list(report.changed_files),
            "missing_files": list(report.missing_files),
            "detected_at": report.detected_at,
        }
        if cfg.output_format == "json":
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        elif report.is_stale:
            click.echo(f"{topic}: STALE (changed: {list(report.changed_files)})")
        else:
            click.echo(f"{topic}: digest up to date")
        if report.is_stale:
            raise SystemExit(2)
        return

    try:
        result = compile_article(tdir)
    except KbFormatError as exc:
        raise click.ClickException(str(exc)) from exc
    if cfg.output_format == "json":
        click.echo(
            json.dumps(
                {
                    "topic": topic,
                    "compiled": str(result.compiled_path),
                    "source_files": list(result.source_files),
                    "sections": result.sections,
                },
                indent=2,
            )
        )
    else:
        click.echo(
            f"compiled {topic}: {result.sections} section(s) from "
            f"{len(result.source_files)} source file(s) -> {result.compiled_path.name}"
        )
