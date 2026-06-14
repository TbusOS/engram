"""Server-rendered page bodies for the web UI (read-only P0).

Every page is a pure ``render_*(root, ...) -> str`` returning a body
HTML fragment that the server wraps with :func:`engram.web.render.layout`.
All dynamic content is escaped via :func:`esc`; ids that index into the
store are resolved through graph.db / typed parsers (never by joining raw
request input into a filesystem path).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from engram.web.render import card, esc, table


@contextmanager
def _ro_conn(db: Path) -> Iterator[sqlite3.Connection]:
    """Open graph.db strictly read-only.

    The web server promises to never mutate the store, but the shared
    ``open_graph_db`` helper is read-write (it mkdirs, sets WAL, and runs
    migrations on open). A GET request must not migrate or create
    anything, so the UI opens the DB in SQLite ``mode=ro`` instead.
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

__all__ = [
    "render_context",
    "render_dashboard",
    "render_health",
    "render_inbox",
    "render_kb",
    "render_memory_detail",
    "render_memory_list",
    "render_workflows",
]


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------


def render_dashboard(root: Path) -> str:
    from engram.commands.review import run_review
    from engram.commands.status import run_status

    status = run_status(root)
    if not status.initialized:
        return (
            "<h1>Dashboard</h1>"
            '<p class="sub">No engram store here. Run <code>engram init</code>.</p>'
        )
    review = run_review(root)

    cards = [
        card("Total assets", status.total_assets),
        card("Store version", status.store_version or "—"),
        card("Validation errors", review.by_severity.get("error", 0)),
        card("Validation warnings", review.by_severity.get("warning", 0)),
    ]
    cards += [card(f"{k} memories", v) for k, v in sorted(status.by_subtype.items())]
    cards.append(card("Workflows", _count_dir(root, "workflows")))
    cards.append(card("KB articles", _count_dir(root, "kb")))

    by_life = table(
        ["Lifecycle", "Count"],
        [[esc(k), esc(v)] for k, v in sorted(status.by_lifecycle.items())],
        empty="(no assets yet)",
    )
    return (
        "<h1>Dashboard</h1>"
        f'<p class="sub">{esc(root)}</p>'
        f'<div class="cards">{"".join(cards)}</div>'
        "<h2 style='margin-top:28px'>By lifecycle</h2>"
        f"{by_life}"
    )


def _count_dir(root: Path, kind: str) -> int:
    d = root / ".memory" / kind
    if not d.is_dir():
        return 0
    doc = {"workflows": "workflow.md", "kb": "README.md"}.get(kind, "")
    return sum(
        1
        for c in d.iterdir()
        if c.is_dir() and not c.is_symlink() and (not doc or (c / doc).is_file())
    )


# ----------------------------------------------------------------------
# Memory
# ----------------------------------------------------------------------


def _memory_rows(root: Path) -> list[dict[str, Any]]:
    from engram.commands.memory import graph_db_path

    db = graph_db_path(root)
    if not db.exists():
        return []
    with _ro_conn(db) as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, subtype, scope, lifecycle_state, enforcement, path "
                "FROM assets WHERE kind='memory' ORDER BY id"
            ).fetchall()
        ]


def render_memory_list(root: Path) -> str:
    rows = _memory_rows(root)
    body = table(
        ["ID", "Type", "Scope", "Enforcement", "Lifecycle"],
        [
            [
                f'<a href="/memory/{esc(r["id"])}">{esc(r["id"])}</a>',
                esc(r["subtype"]),
                esc(r["scope"]),
                _enf_pill(r["enforcement"]),
                esc(r["lifecycle_state"]),
            ]
            for r in rows
        ],
        empty="(no memories — add one with `engram memory add`)",
    )
    return f"<h1>Memory</h1><p class='sub'>{len(rows)} asset(s)</p>{body}"


def _enf_pill(enforcement: str) -> str:
    cls = "mandatory" if enforcement == "mandatory" else ""
    return f'<span class="pill {cls}">{esc(enforcement)}</span>'


def render_memory_detail(root: Path, asset_id: str) -> str | None:
    """Render one memory. Returns None (-> 404) if the id is unknown.

    Security: the id is matched against graph.db; the file path read is
    the stored ``path`` column, never a path built from request input.
    """
    from engram.core.frontmatter import FrontmatterError, parse_file
    from engram.core.paths import memory_dir

    row = next((r for r in _memory_rows(root) if r["id"] == asset_id), None)
    if row is None:
        return None
    path = memory_dir(root) / row["path"]
    try:
        fm, body = parse_file(path)
    except (FrontmatterError, OSError):
        return None
    meta = table(
        ["Field", "Value"],
        [
            [esc("name"), esc(fm.name)],
            [esc("type"), esc(fm.type.value)],
            [esc("scope"), esc(fm.scope.value)],
            [esc("enforcement"), _enf_pill(fm.enforcement.value)],
            [esc("description"), esc(fm.description)],
            [esc("tags"), esc(", ".join(fm.tags) or "—")],
        ],
    )
    return (
        f"<h1>{esc(fm.name)}</h1><p class='sub'>{esc(asset_id)}</p>"
        f"{meta}<h2>Body</h2><pre>{esc(body)}</pre>"
    )


# ----------------------------------------------------------------------
# Workflows
# ----------------------------------------------------------------------


def render_workflows(root: Path) -> str:
    from engram.workflow import parse_workflow_file, workflows_root
    from engram.workflow.format import WorkflowFormatError
    from engram.workflow.rev import current_revision

    wr = workflows_root(root)
    rows: list[list[str]] = []
    if wr.is_dir():
        for child in sorted(wr.iterdir()):
            doc = child / "workflow.md"
            if not doc.is_file() or child.is_symlink():
                continue
            try:
                fm, _ = parse_workflow_file(doc)
            except WorkflowFormatError:
                continue
            rows.append(
                [
                    esc(child.name),
                    f'<span class="pill">{esc(fm.lifecycle_state)}</span>',
                    esc(fm.spine_lang),
                    esc(current_revision(child) or "—"),
                    esc(fm.description),
                ]
            )
    body = table(
        ["Name", "Lifecycle", "Spine", "Rev", "Description"],
        rows,
        empty="(no workflows — create one with `engram workflow add`)",
    )
    return f"<h1>Workflows</h1><p class='sub'>{len(rows)} workflow(s)</p>{body}"


# ----------------------------------------------------------------------
# Knowledge Base
# ----------------------------------------------------------------------


def render_kb(root: Path) -> str:
    from engram.kb import check_staleness, kb_root, parse_readme
    from engram.kb.format import KbFormatError

    kr = kb_root(root)
    rows: list[list[str]] = []
    if kr.is_dir():
        for child in sorted(kr.iterdir()):
            readme = child / "README.md"
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
            stale_pill = (
                '<span class="pill warn">stale</span>'
                if stale
                else ('<span class="pill ok">fresh</span>' if stale is False else "—")
            )
            rows.append(
                [
                    esc(child.name),
                    f'<span class="pill">{esc(fm.lifecycle_state)}</span>',
                    esc(len(fm.chapters)),
                    stale_pill,
                    esc(fm.name),
                ]
            )
    body = table(
        ["Topic", "Lifecycle", "Chapters", "Digest", "Title"],
        rows,
        empty="(no KB articles — create one with `engram kb new-article`)",
    )
    return f"<h1>Knowledge Base</h1><p class='sub'>{len(rows)} article(s)</p>{body}"


# ----------------------------------------------------------------------
# Inbox
# ----------------------------------------------------------------------


def render_inbox(root: Path) -> str:
    from engram.inbox import list_messages, resolve_repo_id

    repo = resolve_repo_id(root)
    sections = []
    for status in ("pending", "acknowledged", "resolved", "rejected"):
        msgs = list_messages(recipient_id=repo, status=status)
        rows = [
            [
                esc(m.get("from", "?")),
                esc(m.get("intent", "?")),
                _sev_pill(m.get("severity", "info")),
                esc(m.get("message_id", "")),
                esc(m.get("created", "")),
            ]
            for m in msgs
        ]
        sections.append(
            f"<h2>{esc(status)} ({len(rows)})</h2>"
            + table(["From", "Intent", "Severity", "Message ID", "Created"], rows, empty="(none)")
        )
    return f"<h1>Inbox</h1><p class='sub'>recipient: {esc(repo)}</p>{''.join(sections)}"


def _sev_pill(sev: str) -> str:
    cls = {"critical": "error", "warning": "warn"}.get(sev, "")
    return f'<span class="pill {cls}">{esc(sev)}</span>'


# ----------------------------------------------------------------------
# Context Preview — the critical debug page (DESIGN §7.1)
# ----------------------------------------------------------------------


def render_context(root: Path, *, task: str = "", budget: int = 4000) -> str:
    form = (
        '<form class="ctx" method="get" action="/context">'
        f'<textarea name="task" rows="2" placeholder="Describe a task…">{esc(task)}</textarea>'
        f'<input type="number" name="budget" value="{esc(budget)}" min="500" max="32000">'
        "<button type=\"submit\">Run</button></form>"
    )
    if not task.strip():
        return (
            "<h1>Context Preview</h1>"
            "<p class='sub'>Simulate exactly what the LLM would see for a task, "
            "before any LLM is invoked.</p>" + form
        )

    result = _run_gate(root, task, budget)
    mand_rows = [[esc(a_id), esc(scope), '<span class="pill mandatory">mandatory</span>']
                 for a_id, scope in result["mandatory"]]
    inc_rows = [
        [esc(c["id"]), esc(c["scope"]), esc(round(c["score"], 3)), esc(c["tokens"]), "included"]
        for c in result["included"]
    ]
    exc_rows = [
        [esc(c["id"]), esc(c["scope"]), esc(round(c["score"], 3)), esc(c["tokens"]), "over budget"]
        for c in result["excluded"]
    ]
    mand = table(["ID", "Scope", ""], mand_rows, empty="(no mandatory assets)")
    boundary = [["<span class='bound'>— budget boundary —</span>", "", "", "", ""]]
    ranked_rows = [*inc_rows, *boundary, *exc_rows] if exc_rows else inc_rows
    ranked = table(
        ["ID", "Scope", "Score", "Tokens", "Status"],
        ranked_rows,
        empty="(no ranked matches)",
    )
    return (
        "<h1>Context Preview</h1>"
        f'<p class="sub">{result["total_tokens"]} / {budget} tokens used</p>'
        f"{form}<h2>Mandatory (always included)</h2>{mand}"
        f"<h2>Ranked</h2>{ranked}"
    )


def _run_gate(root: Path, task: str, budget: int) -> dict[str, Any]:
    from engram.commands.memory import graph_db_path
    from engram.core.frontmatter import FrontmatterError, parse_file
    from engram.core.paths import memory_dir
    from engram.relevance.gate import Asset, RelevanceRequest, run_relevance_gate

    mem = memory_dir(root)
    assets: list[Asset] = []
    db = graph_db_path(root)
    if db.exists():
        with _ro_conn(db) as conn:
            rows = conn.execute(
                "SELECT id, path FROM assets WHERE kind='memory'"
            ).fetchall()
        for r in rows:
            p = mem / r["path"]
            if not p.exists():
                continue
            try:
                fm, body = parse_file(p)
            except FrontmatterError:
                continue
            assets.append(
                Asset(
                    id=r["id"],
                    scope=fm.scope.value,
                    enforcement=fm.enforcement.value,
                    subscribed_at=fm.subscribed_at.value if fm.subscribed_at else None,
                    body=body,
                    updated=fm.updated or date.today(),
                    size_bytes=p.stat().st_size,
                )
            )
    res = run_relevance_gate(
        RelevanceRequest(query=task, assets=tuple(assets), budget_tokens=budget, now=date.today())
    )
    return {
        "mandatory": [(a.id, a.scope) for a in res.mandatory],
        "included": [
            {
                "id": c.asset.id,
                "scope": c.asset.scope,
                "score": c.final_score,
                "tokens": c.tokens_est,
            }
            for c in res.included
        ],
        "excluded": [
            {
                "id": c.asset.id,
                "scope": c.asset.scope,
                "score": c.final_score,
                "tokens": c.tokens_est,
            }
            for c in res.excluded_due_to_budget
        ],
        "total_tokens": res.total_tokens,
    }


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------


def render_health(root: Path) -> str:
    from engram.commands.review import run_review

    review = run_review(root)
    rows = [
        [
            _sev_pill_validation(i.severity),
            esc(i.code),
            esc(i.file or "—"),
            esc(i.message),
        ]
        for i in review.issues
    ]
    body = table(["Severity", "Code", "File", "Message"], rows, empty="No validation issues.")
    return (
        "<h1>Health</h1>"
        f'<p class="sub">{review.by_severity.get("error", 0)} error(s), '
        f'{review.by_severity.get("warning", 0)} warning(s)</p>{body}'
    )


def _sev_pill_validation(sev: object) -> str:
    s = getattr(sev, "value", str(sev))
    cls = {"error": "error", "warning": "warn"}.get(s, "")
    return f'<span class="pill {cls}">{esc(s)}</span>'
