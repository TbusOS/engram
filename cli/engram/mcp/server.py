"""MCP server — line-delimited JSON-RPC 2.0 over stdio (T-51).

Minimal implementation of the MCP 2024-11-05 baseline. Supported
methods: ``initialize``, ``tools/list``, ``tools/call``, plus the
``notifications/initialized`` one-way notification.

We implement the wire protocol directly rather than pulling in the
official ``mcp`` Python SDK because (a) engram's discipline is zero
non-essential dependencies, (b) our tool surface is tiny and fixed,
(c) the protocol handler is easier to unit-test when it's a pure
function. If/when we add streaming tools or SSE transport, a direct
switch to the SDK is a small lift.

The stateless model means every request is independent: the server
does not retain session state, and a client can invoke ``tools/call``
at any time without first calling ``initialize`` (though standard
clients always do). This matches DESIGN §6.2.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from engram.mcp.tools import call_tool, render_tool_list

__all__ = [
    "ServerContext",
    "dispatch",
    "handle_line",
    "serve_stdio",
]


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "engram", "version": "0.2.0"}


@dataclass(frozen=True, slots=True)
class ServerContext:
    store_root: Path


# ------------------------------------------------------------------
# JSON-RPC helpers
# ------------------------------------------------------------------


def _error(
    id_: Any, code: int, message: str, data: Any | None = None
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _result(id_: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _is_valid_request(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("jsonrpc") == "2.0"
        and isinstance(payload.get("method"), str)
    )


# ------------------------------------------------------------------
# Method handlers
# ------------------------------------------------------------------


def _handle_initialize(
    payload: dict[str, Any], ctx: ServerContext
) -> dict[str, Any]:
    _ = payload, ctx  # no per-session state
    return _result(
        payload.get("id"),
        {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": SERVER_INFO,
            "capabilities": {
                # We only expose tools today. Resources + prompts are a
                # future surface once the read-side stabilises.
                "tools": {},
            },
        },
    )


def _handle_tools_list(
    payload: dict[str, Any], ctx: ServerContext
) -> dict[str, Any]:
    _ = ctx
    return _result(payload.get("id"), {"tools": render_tool_list()})


def _handle_tools_call(
    payload: dict[str, Any], ctx: ServerContext
) -> dict[str, Any]:
    params = payload.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(name, str):
        return _tool_error(payload.get("id"), "tools/call requires 'name' (string)")
    if arguments is not None and not isinstance(arguments, dict):
        return _tool_error(
            payload.get("id"), "tools/call 'arguments' must be an object"
        )
    if arguments is None:
        return _tool_error(
            payload.get("id"),
            f"tool {name!r} requires 'arguments' object in params",
        )
    try:
        result = call_tool(ctx.store_root, name, arguments)
    except (LookupError, ValueError, FileNotFoundError) as e:
        return _tool_error(payload.get("id"), str(e))
    return _result(payload.get("id"), result)


def _tool_error(id_: Any, message: str) -> dict[str, Any]:
    """MCP tool errors are returned as a *result* with ``isError: true``,
    not as a JSON-RPC error frame. This matches the protocol so clients
    that distinguish tool failures from transport failures stay happy."""
    return _result(
        id_,
        {
            "isError": True,
            "content": [{"type": "text", "text": message}],
        },
    )


_METHODS: dict[str, Any] = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


# ------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------


def dispatch(payload: Any, ctx: ServerContext) -> dict[str, Any]:
    """Dispatch one JSON-RPC request payload. Pure function — no IO."""
    if not _is_valid_request(payload):
        return _error(
            payload.get("id") if isinstance(payload, dict) else None,
            -32600,
            "Invalid Request",
        )
    method = payload["method"]

    # Notifications (no id) are one-way; the 'notifications/initialized'
    # handshake follow-up is the canonical case. Acknowledge silently.
    if "id" not in payload:
        return {}  # caller drops empty responses; see handle_line

    handler = _METHODS.get(method)
    if handler is None:
        return _error(payload["id"], -32601, f"Method not found: {method}")
    return handler(payload, ctx)


def handle_line(line: str, ctx: ServerContext) -> str:
    """Handle one line of stdio input; return the JSON response line.

    On parse error returns a JSON-RPC parse-error frame with id=None.
    """
    line = line.strip()
    if not line:
        return ""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as e:
        resp = _error(None, -32700, "Parse error", str(e))
        return json.dumps(resp)
    resp = dispatch(payload, ctx)
    if not resp:
        return ""  # notification — nothing to send
    return json.dumps(resp)


# ------------------------------------------------------------------
# Stdio driver
# ------------------------------------------------------------------


def serve_stdio(
    ctx: ServerContext,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Block on stdin, dispatch each line, write each response."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        response = handle_line(line, ctx)
        if response:
            stdout.write(response + "\n")
            stdout.flush()
