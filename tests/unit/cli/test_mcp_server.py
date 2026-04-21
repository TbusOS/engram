"""T-51/T-52 tests: MCP (Model Context Protocol) server.

The server is stateless, stdio-transport, and exposes engram's read
surface to any MCP-capable client — Claude Desktop, Zed, Cursor, and
VS Code (through ``continue.dev`` / ``cline`` / Copilot extensions that
speak MCP). Tests drive the ``dispatch()`` entry point directly; the
``serve_stdio()`` loop is a thin wrapper that is exercised by an
integration test at the end.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.mcp.server import ServerContext, dispatch, serve_stdio


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "proj"
    runner = CliRunner()

    def _invoke(*args: str) -> None:
        result = runner.invoke(cli, list(args))
        assert result.exit_code == 0, result.output

    _invoke("--dir", str(root), "init", "--name", "mcp-test")
    _invoke(
        "--dir",
        str(root),
        "memory",
        "add",
        "--type",
        "user",
        "--name",
        "kernel",
        "--description",
        "reads mm fs",
        "--body",
        "The user reads kernel mm and fs regularly.",
    )
    _invoke(
        "--dir",
        str(root),
        "memory",
        "add",
        "--type",
        "feedback",
        "--enforcement",
        "mandatory",
        "--name",
        "confirm push",
        "--description",
        "confirm before pushing",
        "--body",
        "Ask before pushing.\n\n**Why:** safety.\n\n**How to apply:** always.",
    )
    return root


@pytest.fixture
def ctx(project: Path) -> ServerContext:
    return ServerContext(store_root=project)


def _rpc(method: str, params: dict | None = None, id_: int | str = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "method": method,
        "params": params or {},
    }


# ------------------------------------------------------------------
# Protocol handshake
# ------------------------------------------------------------------


def test_initialize_returns_protocol_and_server_info(ctx: ServerContext) -> None:
    resp = dispatch(_rpc("initialize", {"protocolVersion": "2024-11-05"}), ctx)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert "protocolVersion" in result
    assert "serverInfo" in result
    assert result["serverInfo"]["name"] == "engram"
    assert "capabilities" in result
    assert result["capabilities"]["tools"] is not None


def test_unknown_method_returns_method_not_found(ctx: ServerContext) -> None:
    resp = dispatch(_rpc("wibble/flarn"), ctx)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_malformed_json_returns_parse_error() -> None:
    from engram.mcp.server import handle_line

    ctx = ServerContext(store_root=Path("/tmp/nonexistent"))
    out = handle_line("{not: valid json", ctx)
    payload = json.loads(out)
    assert payload["error"]["code"] == -32700


def test_missing_jsonrpc_field_is_invalid_request(ctx: ServerContext) -> None:
    resp = dispatch({"id": 1, "method": "initialize"}, ctx)
    assert resp["error"]["code"] == -32600


# ------------------------------------------------------------------
# tools/list
# ------------------------------------------------------------------


def test_tools_list_returns_known_tools(ctx: ServerContext) -> None:
    resp = dispatch(_rpc("tools/list"), ctx)
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {
        "engram_memory_read",
        "engram_memory_search",
        "engram_context_pack",
    }.issubset(names)
    # Every tool has a usable schema.
    for t in tools:
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"


# ------------------------------------------------------------------
# tools/call — engram_memory_search
# ------------------------------------------------------------------


def test_tools_call_memory_search(ctx: ServerContext) -> None:
    resp = dispatch(
        _rpc(
            "tools/call",
            {"name": "engram_memory_search", "arguments": {"query": "kernel"}},
        ),
        ctx,
    )
    result = resp["result"]
    assert "content" in result
    payload = json.loads(result["content"][0]["text"])
    assert any("kernel" in hit["id"].lower() for hit in payload["hits"])


def test_tools_call_memory_read(ctx: ServerContext) -> None:
    # First find the asset id via search.
    resp = dispatch(
        _rpc(
            "tools/call",
            {"name": "engram_memory_search", "arguments": {"query": "kernel"}},
        ),
        ctx,
    )
    hits = json.loads(resp["result"]["content"][0]["text"])["hits"]
    assert hits
    asset_id = hits[0]["id"]

    resp2 = dispatch(
        _rpc(
            "tools/call",
            {
                "name": "engram_memory_read",
                "arguments": {"asset_id": asset_id},
            },
        ),
        ctx,
    )
    payload = json.loads(resp2["result"]["content"][0]["text"])
    assert payload["asset_id"] == asset_id
    assert "frontmatter" in payload
    assert "body" in payload


def test_tools_call_memory_read_missing_id(ctx: ServerContext) -> None:
    resp = dispatch(
        _rpc(
            "tools/call",
            {
                "name": "engram_memory_read",
                "arguments": {"asset_id": "local/does_not_exist"},
            },
        ),
        ctx,
    )
    # isError surface — MCP tool errors return result with isError=true
    assert resp["result"].get("isError") is True


# ------------------------------------------------------------------
# tools/call — engram_context_pack
# ------------------------------------------------------------------


def test_tools_call_context_pack_returns_mandatory(ctx: ServerContext) -> None:
    resp = dispatch(
        _rpc(
            "tools/call",
            {
                "name": "engram_context_pack",
                "arguments": {"task": "anything", "budget": 4000},
            },
        ),
        ctx,
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    # Mandatory rule seeded in fixture must appear regardless of query.
    assert len(payload["mandatory"]) >= 1
    assert "total_tokens" in payload


def test_tools_call_unknown_tool(ctx: ServerContext) -> None:
    resp = dispatch(
        _rpc("tools/call", {"name": "not_a_tool", "arguments": {}}),
        ctx,
    )
    assert resp["result"].get("isError") is True


def test_tools_call_missing_arguments(ctx: ServerContext) -> None:
    resp = dispatch(
        _rpc("tools/call", {"name": "engram_memory_search"}),
        ctx,
    )
    # Missing 'arguments' field entirely — expect schema-level error.
    assert resp["result"].get("isError") is True


# ------------------------------------------------------------------
# Stdio integration
# ------------------------------------------------------------------


def test_serve_stdio_round_trip(ctx: ServerContext) -> None:
    """Feed two requests through the stdio loop and parse the responses."""
    in_buf = StringIO()
    in_buf.write(json.dumps(_rpc("initialize")) + "\n")
    in_buf.write(json.dumps(_rpc("tools/list", id_=2)) + "\n")
    in_buf.seek(0)
    out_buf = StringIO()

    serve_stdio(ctx, stdin=in_buf, stdout=out_buf)

    lines = [line for line in out_buf.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    r2 = json.loads(lines[1])
    assert r1["id"] == 1
    assert r2["id"] == 2
    assert "result" in r1
    assert "tools" in r2["result"]


# ------------------------------------------------------------------
# CLI wiring — engram mcp serve
# ------------------------------------------------------------------


def test_engram_mcp_help_lists_serve(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "mcp", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
