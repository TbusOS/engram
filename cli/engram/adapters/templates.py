"""Template text for each canonical adapter.

Kept in Python rather than external files so that shipping the package
via pip installs the templates alongside the code — no data-file
packaging to get right. Every template is a short brief, not a tutorial:
the LLM reads it once, gets the surface, and moves on.
"""

from __future__ import annotations

__all__ = [
    "render_body",
    "render_body_for_cursor",
]


_COMMON_BODY = """\
# engram memory system

This project uses **engram** (https://github.com/TbusOS/engram) for
long-term memory. Memories live under `.memory/` as plain markdown
with YAML frontmatter; the CLI is `engram` and an MCP server is
available (`engram mcp serve`) for tool-based access.

## Read first

- `.memory/MEMORY.md` — landing index. Always start here.
- `.memory/local/` — project-scope memories (scope=project).
- `.memory/pools/<name>/` — subscribed pool symlinks.

## How rules work (SPEC §8)

- `enforcement: mandatory` — absolute priority. Follow unconditionally.
- `enforcement: default` — follow unless a more specific scope overrides.
- `enforcement: hint` — advisory.
- Hierarchy specificity: `project > user > team > org`. A more
  specific scope beats a less specific one at the same enforcement
  level. `pool` assets project onto their `subscribed_at` level.

## Tools available to you

- `engram memory search "<query>"` — BM25 + scope-weighted search.
- `engram memory read <asset_id>` — read one memory.
- `engram context pack --task="<task>" --budget=4000` — assemble a
  ranked context pack within a token budget.
- MCP equivalents: `engram_memory_search`, `engram_memory_read`,
  `engram_context_pack`.

## Writing memories

- `engram memory add --type=<subtype> --name=<name> --description=<one-liner> --body=<body>`
  where subtype is one of `user / feedback / project / reference /
  workflow_ptr / agent`.
- Every `feedback` asset needs `--enforcement=<mandatory|default|hint>`.
- Never edit `.memory/local/*.md` directly to "patch" an existing
  rule — the user decides retirements; use `engram memory archive`
  or `engram consistency scan` to propose changes.

## Rules of engagement

- Respect `enforcement: mandatory` absolutely.
- Ask the user before `git push` (this rule is almost always stored
  as a mandatory feedback asset; check `.memory/local/` before
  acting).
- When uncertain whether a memory applies, run
  `engram memory search "<task keywords>"` before proceeding.
"""


def render_body() -> str:
    return _COMMON_BODY


def render_body_for_cursor() -> str:
    """Cursor rule files use MDC front-matter; wrap the same body."""
    return (
        "---\n"
        "description: engram memory system — read .memory/ before writing code\n"
        "globs:\n"
        "  - '**/*'\n"
        "alwaysApply: true\n"
        "---\n\n"
        + _COMMON_BODY
    )
