"""Tests for the stdlib server-rendered web UI (SPEC §7)."""

from __future__ import annotations

import base64
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.web.render import esc, layout
from engram.web.server import route, serve


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    proj = tmp_path / "proj"
    runner = CliRunner()
    assert runner.invoke(cli, ["--dir", str(proj), "init"]).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "--dir", str(proj), "memory", "add",
            "--type", "feedback", "--enforcement", "mandatory",
            "--name", "confirm push", "--description", "ask before pushing",
            "--body", "**Why:** safety\n\n**How to apply:** always",
        ],
    ).exit_code == 0
    return proj


# ----------------------------------------------------------------------
# render helpers
# ----------------------------------------------------------------------


def test_esc_blocks_html_injection() -> None:
    assert esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert "&quot;" in esc('a"b')


def test_layout_marks_active_nav() -> None:
    html = layout("Memory", "<p>x</p>", active="/memory")
    assert '<a href="/memory" class="active">Memory</a>' in html
    assert "engram" in html


# ----------------------------------------------------------------------
# routing
# ----------------------------------------------------------------------


def test_routes_render_200(project: Path) -> None:
    for path in ("/", "/memory", "/workflows", "/kb", "/inbox", "/context", "/health"):
        resp = route(path, {}, project)
        assert resp.status == 200, path
        assert "<html" in resp.body


def test_memory_detail_route(project: Path) -> None:
    resp = route("/memory/local/feedback_confirm_push", {}, project)
    assert resp.status == 200
    assert "confirm push" in resp.body
    assert "safety" in resp.body


def test_unknown_memory_is_404(project: Path) -> None:
    resp = route("/memory/local/ghost", {}, project)
    assert resp.status == 404


def test_unknown_path_is_404(project: Path) -> None:
    assert route("/nope", {}, project).status == 404


def test_dashboard_shows_counts(project: Path) -> None:
    body = route("/", {}, project).body
    assert "Dashboard" in body
    assert "Total assets" in body


def test_context_preview_runs_gate(project: Path) -> None:
    resp = route("/context", {"task": "confirm before pushing", "budget": "4000"}, project)
    assert resp.status == 200
    # The mandatory feedback asset must appear regardless of the query.
    assert "mandatory" in resp.body.lower()


def test_context_budget_is_clamped(project: Path) -> None:
    # Non-numeric budget falls back to default, no crash.
    assert route("/context", {"task": "x", "budget": "abc"}, project).status == 200


def test_memory_detail_escapes_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    proj = tmp_path / "proj"
    runner = CliRunner()
    runner.invoke(cli, ["--dir", str(proj), "init"])
    runner.invoke(
        cli,
        [
            "--dir", str(proj), "memory", "add", "--type", "project",
            "--name", "xss test", "--description", "d",
            "--body", "<script>alert('pwn')</script>",
        ],
    )
    body = route("/memory/local/project_xss_test", {}, proj).body
    assert "<script>alert('pwn')</script>" not in body
    assert "&lt;script&gt;" in body


# ----------------------------------------------------------------------
# server security (DESIGN §7.4)
# ----------------------------------------------------------------------


def test_non_loopback_without_auth_refuses(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        serve(tmp_path, host="0.0.0.0", open_browser=False)


def test_non_loopback_with_auth_allowed(tmp_path: Path) -> None:
    # Binding 0.0.0.0 is allowed *with* auth; bind to port 0 then close.
    httpd = serve(tmp_path, host="0.0.0.0", port=0, auth=("u", "p"), open_browser=False)
    httpd.server_close()


def test_http_basic_auth_round_trip(project: Path) -> None:
    httpd = serve(project, port=0, auth=("u", "p"), open_browser=False)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}/"
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(url, timeout=5)
        assert ei.value.code == 401

        hdr = {"Authorization": "Basic " + base64.b64encode(b"u:p").decode()}
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=5)
        assert resp.status == 200
        assert b"Dashboard" in resp.read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_post_is_405(project: Path) -> None:
    httpd = serve(project, port=0, open_browser=False)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", data=b"x", method="POST")
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=5)
        assert ei.value.code == 405
    finally:
        httpd.shutdown()
        httpd.server_close()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def test_cli_web_serve_bad_auth(project: Path) -> None:
    res = CliRunner().invoke(cli, ["--dir", str(project), "web", "serve", "--auth", "noColon"])
    assert res.exit_code != 0
    assert "USER:PASS" in res.output
