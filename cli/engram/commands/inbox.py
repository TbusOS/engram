"""``engram inbox`` — cross-repo message CLI (T-50, SPEC §10)."""

from __future__ import annotations

import json

import click

from engram.config_types import GlobalConfig
from engram.inbox import (
    acknowledge,
    list_messages,
    reject,
    resolve,
    send_message,
)

__all__ = ["inbox_cmd"]


_VALID_INTENTS = (
    "bug-report",
    "api-change",
    "question",
    "update-notify",
    "task",
)
_VALID_SEVERITIES = ("info", "warning", "critical")
_VALID_STATUSES = ("pending", "acknowledged", "resolved", "rejected")


@click.group("inbox")
def inbox_cmd() -> None:
    """Cross-repo message inbox (SPEC §10)."""


@inbox_cmd.command("send")
@click.option("--to", required=True, metavar="REPO_ID")
@click.option(
    "--intent",
    required=True,
    type=click.Choice(_VALID_INTENTS),
)
@click.option("--summary", required=True)
@click.option("--what", required=True)
@click.option("--why", required=True)
@click.option("--how", default="")
@click.option("--severity", type=click.Choice(_VALID_SEVERITIES), default="info")
@click.option("--deadline", default=None, help="ISO 8601 UTC deadline")
@click.option("--dedup-key", default=None)
@click.option("--reply-to", default=None)
@click.pass_obj
def send_cmd(
    cfg: GlobalConfig,
    to: str,
    intent: str,
    summary: str,
    what: str,
    why: str,
    how: str,
    severity: str,
    deadline: str | None,
    dedup_key: str | None,
    reply_to: str | None,
) -> None:
    """Send a cross-repo message."""
    result = send_message(
        project_root=cfg.resolve_project_root(),
        to=to,
        intent=intent,
        summary=summary,
        what=what,
        why=why,
        how=how,
        severity=severity,
        deadline=deadline,
        dedup_key=dedup_key,
        reply_to=reply_to,
    )
    if cfg.output_format == "json":
        click.echo(json.dumps(result))
        return
    status = result["status"]
    if status == "sent":
        click.echo(f"sent {result['message_id']} → {result['path']}")
    elif status == "duplicate-merged":
        click.echo(f"duplicate merged into {result['message_id']}")
    else:
        click.echo(f"rate-limit: {result['detail']}")


@inbox_cmd.command("list")
@click.option(
    "--as",
    "as_repo",
    required=True,
    metavar="REPO_ID",
    help="Recipient repo id whose inbox to list.",
)
@click.option("--status", type=click.Choice(_VALID_STATUSES), default="pending")
@click.pass_obj
def list_cmd(cfg: GlobalConfig, as_repo: str, status: str) -> None:
    msgs = list_messages(recipient_id=as_repo, status=status)
    rendered = [
        {
            "message_id": m.get("message_id"),
            "from": m.get("from"),
            "intent": m.get("intent"),
            "severity": m.get("severity"),
            "created": m.get("created"),
            "path": m.get("_path"),
        }
        for m in msgs
    ]
    if cfg.output_format == "json":
        click.echo(json.dumps(rendered))
        return
    if not msgs:
        click.echo(f"no {status} messages")
        return
    for m in rendered:
        click.echo(
            f"{m['severity']:<8}  {m['intent']:<14}  "
            f"{m['from']:<20}  {m['message_id']}"
        )


@inbox_cmd.command("acknowledge")
@click.argument("message_id")
@click.option("--as", "as_repo", required=True, metavar="REPO_ID")
@click.pass_obj
def ack_cmd(cfg: GlobalConfig, message_id: str, as_repo: str) -> None:
    path = acknowledge(recipient_id=as_repo, message_id=message_id)
    _ = cfg
    click.echo(f"acknowledged {message_id} → {path}")


@inbox_cmd.command("resolve")
@click.argument("message_id")
@click.option("--as", "as_repo", required=True, metavar="REPO_ID")
@click.option("--note", required=True)
@click.pass_obj
def resolve_cmd(
    cfg: GlobalConfig, message_id: str, as_repo: str, note: str
) -> None:
    path = resolve(recipient_id=as_repo, message_id=message_id, note=note)
    _ = cfg
    click.echo(f"resolved {message_id} → {path}")


@inbox_cmd.command("reject")
@click.argument("message_id")
@click.option("--as", "as_repo", required=True, metavar="REPO_ID")
@click.option("--reason", required=True)
@click.pass_obj
def reject_cmd(
    cfg: GlobalConfig, message_id: str, as_repo: str, reason: str
) -> None:
    path = reject(recipient_id=as_repo, message_id=message_id, reason=reason)
    _ = cfg
    click.echo(f"rejected {message_id} → {path}")
