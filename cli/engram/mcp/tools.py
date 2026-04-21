"""MCP tool definitions for engram (T-52).

Each tool is a ``(schema, handler)`` pair. The schema is a
JSON-Schema-object the client exposes to the model; the handler is a
plain Python function with signature
``(store_root: Path, arguments: dict) -> dict``. Handlers return a dict
that the server wraps into an MCP ``CallToolResult``.

Kept small on purpose — MCP tools are a *protocol surface*, not a
framework. Anything that should be scriptable (migrations, consistency
apply) stays on the CLI; the MCP tools expose only the read-side that
an LLM legitimately needs to ground a reply.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from engram.commands.memory import graph_db_path
from engram.core.frontmatter import FrontmatterError, parse_file
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.relevance.bm25 import bm25_scores
from engram.relevance.gate import Asset, RelevanceRequest, run_relevance_gate
from engram.relevance.weights import ENFORCEMENT_WEIGHTS, SCOPE_WEIGHTS

__all__ = ["TOOLS", "Tool", "render_tool_list"]


ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: ToolHandler


# ------------------------------------------------------------------
# engram_memory_search
# ------------------------------------------------------------------


def _handle_search(store_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("'query' (non-empty string) is required")
    limit = int(args.get("limit", 10))

    mem = memory_dir(store_root)
    with open_graph_db(graph_db_path(store_root)) as conn:
        rows = conn.execute(
            "SELECT id, path FROM assets WHERE kind = 'memory'"
        ).fetchall()

    documents: list[tuple[str, str]] = []
    meta: dict[str, tuple[str, str]] = {}
    for r in rows:
        path = mem / r["path"]
        if not path.exists():
            continue
        try:
            fm, body = parse_file(path)
        except FrontmatterError:
            continue
        documents.append((r["id"], f"{fm.name}\n{fm.description}\n{body}"))
        meta[r["id"]] = (fm.scope.value, fm.enforcement.value)

    raw = bm25_scores(query, documents)
    hits = []
    for doc_id, raw_score in raw[:limit]:
        scope, enforcement = meta.get(doc_id, ("project", "default"))
        weighted = (
            raw_score
            * SCOPE_WEIGHTS.get(scope, 1.0)
            * ENFORCEMENT_WEIGHTS.get(enforcement, 1.0)
        )
        hits.append(
            {
                "id": doc_id,
                "score": round(weighted, 4),
                "raw_score": round(raw_score, 4),
                "scope": scope,
                "enforcement": enforcement,
            }
        )
    return {"query": query, "hits": hits}


# ------------------------------------------------------------------
# engram_memory_read
# ------------------------------------------------------------------


def _handle_read(store_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    asset_id = args.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ValueError("'asset_id' (non-empty string) is required")

    mem = memory_dir(store_root)
    path = mem / f"{asset_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"asset not found: {asset_id}")
    try:
        fm, body = parse_file(path)
    except FrontmatterError as e:
        raise ValueError(f"asset has malformed frontmatter: {e}") from e

    return {
        "asset_id": asset_id,
        "frontmatter": {
            "name": fm.name,
            "description": fm.description,
            "type": fm.type.value,
            "scope": fm.scope.value,
            "enforcement": fm.enforcement.value,
        },
        "body": body,
    }


# ------------------------------------------------------------------
# engram_context_pack
# ------------------------------------------------------------------


def _handle_context_pack(
    store_root: Path, args: dict[str, Any]
) -> dict[str, Any]:
    task = args.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("'task' (non-empty string) is required")
    budget = int(args.get("budget", 4000))

    mem = memory_dir(store_root)
    with open_graph_db(graph_db_path(store_root)) as conn:
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
        assets.append(
            Asset(
                id=r["id"],
                scope=fm.scope.value,
                enforcement=fm.enforcement.value,
                subscribed_at=fm.subscribed_at,
                body=body,
                updated=fm.updated or date.today(),
                size_bytes=path.stat().st_size,
            )
        )
    result = run_relevance_gate(
        RelevanceRequest(
            query=task,
            assets=tuple(assets),
            budget_tokens=budget,
            now=date.today(),
        )
    )
    return {
        "task": task,
        "budget": budget,
        "total_tokens": result.total_tokens,
        "mandatory": [
            {"id": a.id, "scope": a.scope} for a in result.mandatory
        ],
        "included": [
            {
                "id": c.asset.id,
                "score": round(c.final_score, 4),
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


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="engram_memory_search",
        description=(
            "BM25 + scope/enforcement-weighted search over project memories. "
            "Returns a ranked list of asset ids with scores. Use before "
            "engram_memory_read when the exact asset id isn't known."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_handle_search,
    ),
    Tool(
        name="engram_memory_read",
        description=(
            "Read one memory asset by id (e.g. 'local/user_kernel_fluency'). "
            "Returns frontmatter and body."
        ),
        schema={
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": (
                        "Full asset id, e.g. 'local/feedback_confirm_push'. "
                        "Discover ids via engram_memory_search."
                    ),
                },
            },
            "required": ["asset_id"],
            "additionalProperties": False,
        },
        handler=_handle_read,
    ),
    Tool(
        name="engram_context_pack",
        description=(
            "Assemble a token-budgeted context pack for a task description "
            "using the Relevance Gate (DESIGN §5.1). Mandatory assets are "
            "included unconditionally; ranked tail is filled by score/token "
            "until the budget is consumed."
        ),
        schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description; the Relevance Gate query.",
                },
                "budget": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 100_000,
                    "default": 4000,
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
        handler=_handle_context_pack,
    ),
)


def render_tool_list() -> list[dict[str, Any]]:
    """Render TOOLS as the MCP ``tools/list`` payload."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.schema,
        }
        for t in TOOLS
    ]


def call_tool(
    store_root: Path, name: str, arguments: dict[str, Any] | None
) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t.name == name), None)
    if tool is None:
        raise LookupError(f"unknown tool: {name}")
    args = arguments or {}
    # MCP isError responses — the server wraps typed exceptions into
    # isError payloads; re-raise unchanged so it can do that.
    payload = tool.handler(store_root, args)
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}
