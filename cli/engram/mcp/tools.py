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

from engram.commands.memory import MemoryWriteError, create_memory, graph_db_path
from engram.core.frontmatter import FrontmatterError, parse_file
from engram.core.graph_db import open_graph_db
from engram.core.paths import memory_dir
from engram.inbox.messenger import VALID_INTENTS, VALID_SEVERITIES
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
# engram_memory_add (write)
# ------------------------------------------------------------------

_MEMORY_TYPES = ("user", "feedback", "project", "reference", "agent")
_ENFORCEMENTS = ("mandatory", "default", "hint")


def _handle_memory_add(store_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    memory_type = args.get("type")
    if memory_type not in _MEMORY_TYPES:
        raise ValueError(f"'type' must be one of {_MEMORY_TYPES}")
    name = args.get("name")
    description = args.get("description")
    body = args.get("body", "")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' (non-empty string) is required")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("'description' (non-empty string) is required")
    if not isinstance(body, str):
        raise ValueError("'body' must be a string")
    _check_size(body, "body")
    enforcement = args.get("enforcement")
    if enforcement is not None and enforcement not in _ENFORCEMENTS:
        raise ValueError(f"'enforcement' must be one of {_ENFORCEMENTS}")
    raw_tags = args.get("tags", [])
    tags = tuple(str(t) for t in raw_tags) if isinstance(raw_tags, list) else ()

    try:
        result = create_memory(
            store_root,
            memory_type=str(memory_type),
            name=name,
            description=description,
            body=body,
            scope="project",
            enforcement=enforcement,
            tags=tags,
        )
    except MemoryWriteError as exc:
        # Surface as a ValueError so the server wraps it into an MCP
        # isError result instead of a transport-level failure.
        raise ValueError(str(exc)) from exc
    return {"id": result["id"], "path": result["path"], "size_bytes": result["size_bytes"]}


# ------------------------------------------------------------------
# engram_inbox_send / engram_inbox_list (write + read)
# ------------------------------------------------------------------

# Canonical intent/severity sets (imported at module top) so the MCP
# schema can never drift from what send_message actually accepts.
_INTENTS = tuple(sorted(VALID_INTENTS))
_SEVERITIES = tuple(sorted(VALID_SEVERITIES))

# Defensive cap on free-text fields written verbatim from a (prompt-
# injectable) model-driven tool call. Generous — a legitimate memory or
# message is far smaller — but bounds a single oversized write.
_MAX_FIELD_BYTES = 64 * 1024


def _check_size(value: str, field: str) -> None:
    if len(value.encode("utf-8")) > _MAX_FIELD_BYTES:
        raise ValueError(f"'{field}' exceeds the {_MAX_FIELD_BYTES}-byte limit")


def _handle_inbox_send(store_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    from engram.inbox import send_message

    to = args.get("to")
    intent = args.get("intent")
    summary = args.get("summary")
    if not isinstance(to, str) or not to.strip():
        raise ValueError("'to' (recipient repo id) is required")
    if intent not in _INTENTS:
        raise ValueError(f"'intent' must be one of {_INTENTS}")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("'summary' (non-empty string) is required")
    severity = str(args.get("severity", "info"))
    if severity not in _SEVERITIES:
        raise ValueError(f"'severity' must be one of {_SEVERITIES}")
    what, why, how = str(args.get("what", "")), str(args.get("why", "")), str(args.get("how", ""))
    for name, val in (("summary", summary), ("what", what), ("why", why), ("how", how)):
        _check_size(val, name)
    return send_message(
        project_root=store_root,
        to=to,
        intent=intent,
        summary=summary,
        what=what,
        why=why,
        how=how,
        severity=severity,
    )


def _handle_inbox_list(store_root: Path, args: dict[str, Any]) -> dict[str, Any]:
    from engram.inbox import list_messages, resolve_repo_id

    recipient = args.get("recipient")
    if not isinstance(recipient, str) or not recipient.strip():
        recipient = resolve_repo_id(store_root)
    status = str(args.get("status", "pending"))
    if status not in ("pending", "acknowledged", "resolved", "rejected"):
        raise ValueError("'status' must be pending/acknowledged/resolved/rejected")
    messages = list_messages(recipient_id=recipient, status=status)
    return {
        "recipient": recipient,
        "status": status,
        "messages": [
            {
                "message_id": m.get("message_id"),
                "from": m.get("from"),
                "intent": m.get("intent"),
                "severity": m.get("severity"),
                "created": m.get("created"),
            }
            for m in messages
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
    Tool(
        name="engram_memory_add",
        description=(
            "Create a new memory asset (the write side of curation). Use this "
            "to persist a durable fact, preference, rule, or pointer the user "
            "will want in future sessions. Choose 'type' carefully: user (who "
            "the user is), feedback (how to work — needs enforcement), project "
            "(ongoing work), reference (external pointer), agent (derived). "
            "Always written at project scope under local/. Returns the new "
            "asset id. Running this is a deliberate write — only persist what "
            "is genuinely worth remembering."
        ),
        schema={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": list(_MEMORY_TYPES)},
                "name": {"type": "string", "description": "Short human-readable title."},
                "description": {
                    "type": "string",
                    "description": "<=150 char summary used by the Relevance Gate.",
                },
                "body": {"type": "string", "description": "Markdown body of the memory."},
                "enforcement": {
                    "type": "string",
                    "enum": list(_ENFORCEMENTS),
                    "description": "Required for type=feedback (mandatory/default/hint).",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type", "name", "description"],
            "additionalProperties": False,
        },
        handler=_handle_memory_add,
    ),
    Tool(
        name="engram_inbox_send",
        description=(
            "Send a cross-repo message to another project's inbox (SPEC §10). "
            "Use when work in this repo surfaces something another repo's "
            "maintainer needs — a bug, a question, an FYI. Rate-limited and "
            "deduplicated automatically."
        ),
        schema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient repo id (e.g. 'acme/service-b').",
                },
                "intent": {"type": "string", "enum": list(_INTENTS)},
                "summary": {"type": "string", "description": "One-line summary."},
                "what": {"type": "string", "description": "What was observed."},
                "why": {"type": "string", "description": "Why it matters."},
                "how": {"type": "string", "description": "How to act on it."},
                "severity": {"type": "string", "enum": list(_SEVERITIES), "default": "info"},
            },
            "required": ["to", "intent", "summary"],
            "additionalProperties": False,
        },
        handler=_handle_inbox_send,
    ),
    Tool(
        name="engram_inbox_list",
        description=(
            "List inbox messages addressed to this repo (SPEC §10.3 priority "
            "order). Defaults to this repo's own pending messages; pass "
            "'recipient' to inspect another, 'status' to filter."
        ),
        schema={
            "type": "object",
            "properties": {
                "recipient": {
                    "type": "string",
                    "description": "Repo id whose inbox to read; defaults to this repo.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "acknowledged", "resolved", "rejected"],
                    "default": "pending",
                },
            },
            "additionalProperties": False,
        },
        handler=_handle_inbox_list,
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
