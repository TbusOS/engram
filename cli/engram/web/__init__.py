"""engram web UI — a stdlib-only, server-rendered local browser.

Architecture decision (2026-06-14): the DESIGN §7 sketch named a
FastAPI + SvelteKit stack. We deliberately deviate (SPEC > DESIGN >
TASKS authority chain + the project's zero-non-stdlib-core principle):
the web UI is a stdlib ``http.server`` app that server-renders HTML,
ships inside the Python wheel, and runs with ``engram web serve`` — no
node toolchain, no build step, works offline. It honors the DESIGN §7.4
security model exactly: default 127.0.0.1 bind, a non-loopback bind
refuses to start without auth, and no secret ever travels in a request.

P0 pages are read-only views in this first cut; the DESIGN read-write
widgets (CodeMirror edit, autolearn controls, inbox actions) and SSE
live updates are documented follow-ons. Mutations remain available via
the CLI and MCP today.
"""

from __future__ import annotations

from engram.web.server import Response, route, serve

__all__ = ["Response", "route", "serve"]
