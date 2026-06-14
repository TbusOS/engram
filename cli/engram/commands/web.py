"""``engram web`` — serve the local web UI (SPEC §7 / DESIGN §7).

A stdlib-only, server-rendered browser for the store. Read-only in this
cut; mutations stay on the CLI / MCP. Binds 127.0.0.1 by default; a
non-loopback bind requires ``--auth`` (DESIGN §7.4, no bypass).
"""

from __future__ import annotations

import click

from engram.config_types import GlobalConfig
from engram.web.server import DEFAULT_HOST, DEFAULT_PORT, serve

__all__ = ["web_group"]


@click.group("web", help="Local web UI for browsing the engram store (SPEC §7).")
def web_group() -> None:
    pass


@web_group.command("serve", help="Serve the web UI and open a browser.")
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Bind address.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int, help="Bind port.")
@click.option(
    "--auth",
    default=None,
    metavar="USER:PASS",
    help="Enable HTTP Basic auth. Required for a non-loopback --host.",
)
@click.option("--no-open", is_flag=True, default=False, help="Do not open a browser.")
@click.pass_obj
def serve_cmd(
    cfg: GlobalConfig, host: str, port: int, auth: str | None, no_open: bool
) -> None:
    root = cfg.resolve_project_root()
    auth_pair: tuple[str, str] | None = None
    if auth is not None:
        if ":" not in auth:
            raise click.ClickException("--auth must be USER:PASS")
        user, _, password = auth.partition(":")
        if not user or not password:
            raise click.ClickException("--auth must be USER:PASS (both non-empty)")
        auth_pair = (user, password)

    try:
        httpd = serve(root, host=host, port=port, auth=auth_pair, open_browser=not no_open)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except OSError as exc:
        raise click.ClickException(f"could not bind {host}:{port}: {exc}") from exc

    click.echo(f"engram web UI on http://{host}:{port}/  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nshutting down")
    finally:
        httpd.shutdown()
        httpd.server_close()
