"""stdlib HTTP server + pure router for the web UI.

The routing logic is a pure function — :func:`route` maps a path +
query + store root to a :class:`Response` — so pages are testable
without opening a socket. :func:`serve` is the thin ``http.server``
wrapper that adds the DESIGN §7.4 security model: a 127.0.0.1 default
bind, a hard refusal to start on a non-loopback bind without auth, and
optional HTTP Basic auth. The UI is read-only (GET); other methods 405.
"""

from __future__ import annotations

import base64
import http.server
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from engram.web import pages
from engram.web.render import esc, layout

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "Response", "route", "serve"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"


def _page(title: str, body: str, active: str, status: int = 200) -> Response:
    return Response(status=status, body=layout(title, body, active=active))


def route(path: str, query: dict[str, str], root: Path) -> Response:
    """Pure router: (path, query, store root) -> Response. Never raises."""
    try:
        if path == "/":
            return _page("Dashboard", pages.render_dashboard(root), "/")
        if path == "/memory":
            return _page("Memory", pages.render_memory_list(root), "/memory")
        if path.startswith("/memory/"):
            asset_id = urllib.parse.unquote(path[len("/memory/") :])
            body = pages.render_memory_detail(root, asset_id)
            if body is None:
                return _page("Not found", _not_found(f"memory {asset_id!r}"), "/memory", 404)
            return _page("Memory", body, "/memory")
        if path == "/workflows":
            return _page("Workflows", pages.render_workflows(root), "/workflows")
        if path == "/kb":
            return _page("Knowledge Base", pages.render_kb(root), "/kb")
        if path == "/inbox":
            return _page("Inbox", pages.render_inbox(root), "/inbox")
        if path == "/context":
            task = query.get("task", "")
            budget = _clamp_int(query.get("budget", "4000"), 4000, lo=500, hi=32000)
            body = pages.render_context(root, task=task, budget=budget)
            return _page("Context Preview", body, "/context")
        if path == "/health":
            return _page("Health", pages.render_health(root), "/health")
        return _page("Not found", _not_found(path), "/", 404)
    except Exception as exc:
        # Never leak a stack trace to the browser — show the type only.
        msg = f"<h1>Server error</h1><p class='sub'>{esc(type(exc).__name__)}</p>"
        return _page("Error", msg, "/", 500)


def _not_found(what: object) -> str:
    return f"<h1>Not found</h1><p class='sub'>{esc(what)}</p><p><a href='/'>← Dashboard</a></p>"


def _clamp_int(raw: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def serve(
    root: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    auth: tuple[str, str] | None = None,
    open_browser: bool = True,
) -> http.server.ThreadingHTTPServer:
    """Start the web server. Returns the server (caller runs serve_forever).

    Security (DESIGN §7.4): a non-loopback bind without ``auth`` is
    refused — no bypass. ``auth`` is an optional ``(user, password)``
    enforced via HTTP Basic.
    """
    if host not in _LOOPBACK and auth is None:
        raise ValueError(
            f"refusing to bind {host!r} without auth: a non-loopback bind requires "
            "--auth user:pass (DESIGN §7.4, no bypass)"
        )

    expected_header: str | None = None
    if auth is not None:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode("ascii")
        expected_header = f"Basic {token}"

    class _Handler(http.server.BaseHTTPRequestHandler):
        server_version = "engram-web"

        def _authed(self) -> bool:
            if expected_header is None:
                return True
            got = self.headers.get("Authorization", "")
            # Constant-time compare to avoid leaking the credential by timing.
            return secrets.compare_digest(got, expected_header)

        def do_GET(self) -> None:
            if not self._authed():
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="engram"')
                self.end_headers()
                return
            parsed = urllib.parse.urlparse(self.path)
            query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
            resp = route(parsed.path, query, root)
            payload = resp.body.encode("utf-8")
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(payload)))
            # Defense-in-depth on top of uniform output escaping.
            self.send_header("Content-Security-Policy", "default-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            self.send_response(405)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return  # quiet by default

    httpd = http.server.ThreadingHTTPServer((host, port), _Handler)
    if open_browser:
        opener = threading.Timer(0.4, lambda: webbrowser.open(f"http://{host}:{port}/"))
        opener.daemon = True  # don't block interpreter exit on a fast Ctrl-C
        opener.start()
    return httpd
