"""HTML layout + escaping helpers for the server-rendered web UI.

No template engine — stdlib only. Every dynamic value goes through
:func:`esc` (``html.escape``) before it touches the page; the page
functions never interpolate un-escaped user content. The CSS embeds a
compact subset of the project's Anthropic design tokens so the served
pages match the brand of ``docs/`` without shipping external assets.
"""

from __future__ import annotations

from html import escape

__all__ = ["card", "esc", "layout", "table"]

_NAV = (
    ("/", "Dashboard"),
    ("/memory", "Memory"),
    ("/workflows", "Workflows"),
    ("/kb", "Knowledge Base"),
    ("/inbox", "Inbox"),
    ("/context", "Context Preview"),
    ("/health", "Health"),
)

_CSS = """
:root{
  --bg:#faf9f5; --bg-subtle:#f0ede3; --text:#141413; --muted:#6b6a5f;
  --orange:#d97757; --orange-hover:#c56544; --blue:#6a9bcc; --green:#788c5d;
  --danger:#a14238; --card:#fff; --radius:14px;
  --shadow:0 2px 12px rgba(20,20,19,.05);
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:"Helvetica Neue",Arial,sans-serif;font-size:15px;line-height:1.5}
a{color:var(--orange);text-decoration:none}
a:hover{color:var(--orange-hover);text-decoration:underline}
.wrap{display:flex;min-height:100vh}
nav.side{width:220px;background:var(--bg-subtle);padding:20px 0;flex-shrink:0;
  border-right:1px solid #e6e2d6}
nav.side .brand{font-weight:700;font-size:20px;padding:0 22px 16px;letter-spacing:-.5px}
nav.side a{display:block;color:var(--text);padding:9px 22px;border-left:3px solid transparent}
nav.side a:hover{background:#e9e5d8;text-decoration:none}
nav.side a.active{border-left-color:var(--orange);background:#e9e5d8;font-weight:600}
main{flex:1;padding:28px 38px;max-width:1100px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.5px}
.sub{color:var(--muted);margin:0 0 24px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:18px 20px;border:1px solid #efece2}
.card h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;
  color:var(--muted)}
.stat{font-size:30px;font-weight:700}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:var(--radius);
  overflow:hidden;box-shadow:var(--shadow);margin:6px 0 22px}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid #f0ede3;font-size:14px}
th{background:var(--bg-subtle);color:var(--muted);font-weight:600;
  text-transform:uppercase;font-size:11px;letter-spacing:.5px}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:12px;
  background:var(--bg-subtle);color:var(--muted)}
.pill.mandatory{background:#f6dfd6;color:var(--danger)}
.pill.warn{background:#f3ead3;color:#8a6d1f}
.pill.error{background:#f6dfd6;color:var(--danger)}
.pill.ok{background:#e3ead6;color:var(--green)}
pre,code{font-family:var(--mono);font-size:13px}
pre{background:var(--bg-subtle);padding:14px;border-radius:var(--radius);overflow:auto}
form.ctx{display:flex;gap:10px;margin:0 0 18px;flex-wrap:wrap}
form.ctx textarea{flex:1;min-width:280px;font-family:inherit;padding:10px;
  border:1px solid #ddd;border-radius:10px}
form.ctx input[type=number]{width:110px;padding:10px;border:1px solid #ddd;border-radius:10px}
button{background:var(--orange);color:#fff;border:none;border-radius:9999px;
  padding:10px 22px;font-weight:600;cursor:pointer}
button:hover{background:var(--orange-hover)}
.empty{color:var(--muted);font-style:italic;padding:14px 0}
.bound{border-top:2px dashed var(--orange);color:var(--orange);font-size:12px;
  text-align:center;padding:6px}
"""


def esc(value: object) -> str:
    """HTML-escape any value (stringified first)."""
    return escape(str(value), quote=True)


def layout(title: str, body_html: str, *, active: str = "/") -> str:
    """Wrap page body in the full HTML shell + sidebar nav."""
    link_parts = []
    for href, label in _NAV:
        cls = ' class="active"' if href == active else ""
        link_parts.append(f'<a href="{esc(href)}"{cls}>{esc(label)}</a>')
    links = "\n".join(link_parts)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)} · engram</title><style>{_CSS}</style></head>"
        '<body><div class="wrap">'
        f'<nav class="side" aria-label="Primary"><div class="brand">engram</div>{links}</nav>'
        f"<main>{body_html}</main>"
        "</div></body></html>"
    )


def card(title: str, value: object, *, sub: str = "") -> str:
    sub_html = f'<div class="sub" style="margin:6px 0 0">{esc(sub)}</div>' if sub else ""
    return (
        f'<div class="card"><h3>{esc(title)}</h3>'
        f'<div class="stat">{esc(value)}</div>{sub_html}</div>'
    )


def table(headers: list[str], rows: list[list[str]], *, empty: str = "(none)") -> str:
    """Render a table. Cell strings are treated as TRUSTED pre-rendered HTML;
    callers MUST pass cells through :func:`esc` (or build safe links) first."""
    if not rows:
        return f'<div class="empty">{esc(empty)}</div>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
