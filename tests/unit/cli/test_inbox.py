"""T-50 tests: Inter-Repo Messenger inbox (SPEC §10).

Covers repo-id resolution, send/dedup/rate-limit, lifecycle transitions
(ack/resolve/reject), list, journaling. Per authority chain SPEC > TASKS:
rate limits follow SPEC §10.5 (20 pending / 50 per day) not TASKS' stale
"10/day" note.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import engram.cli  # noqa: F401  # import order
from engram.commands.init import init_project
from engram.inbox.identity import resolve_repo_id
from engram.inbox.lifecycle import acknowledge, reject, resolve
from engram.inbox.list_ import list_messages
from engram.inbox.messenger import (
    DEDUP_DETECTED,
    MAX_PENDING_PER_SENDER,
    MAX_PER_SENDER_PER_DAY,
    RATE_LIMIT_HIT,
    SENT,
    send_message,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    return fake


@pytest.fixture
def sender_project(tmp_path: Path, home: Path) -> Path:
    proj = tmp_path / "sender"
    init_project(proj)
    cfg = proj / ".engram" / "config.toml"
    cfg.write_text(
        '[project]\nrepo_id = "acme/service-a"\n', encoding="utf-8"
    )
    return proj


def _send(project: Path, **kwargs) -> dict:
    defaults = {
        "to": "acme/service-b",
        "intent": "bug-report",
        "summary": "empty array for missing user id",
        "what": "GET /api/users?id=ghost returns [] instead of 404.",
        "why": "service-a treats [] as no-results and silently drops data.",
        "how": "return 404 JSON body for by-id lookups.",
    }
    defaults.update(kwargs)
    return send_message(project_root=project, **defaults)


# ------------------------------------------------------------------
# Repo ID resolution (SPEC §10.6)
# ------------------------------------------------------------------


def test_repo_id_explicit_config_wins(home: Path, tmp_path: Path) -> None:
    proj = tmp_path / "explicit"
    init_project(proj)
    cfg = proj / ".engram" / "config.toml"
    cfg.write_text('[project]\nrepo_id = "acme/my-service"\n', encoding="utf-8")
    assert resolve_repo_id(proj) == "acme/my-service"


def test_repo_id_path_hash_when_no_config_no_git(
    home: Path, tmp_path: Path
) -> None:
    proj = tmp_path / "plain"
    init_project(proj)
    rid = resolve_repo_id(proj)
    assert len(rid) == 12
    assert all(c in "0123456789abcdef" for c in rid)


def test_repo_id_stable_across_calls(home: Path, tmp_path: Path) -> None:
    proj = tmp_path / "stable"
    init_project(proj)
    assert resolve_repo_id(proj) == resolve_repo_id(proj)


# ------------------------------------------------------------------
# send_message — SPEC §10.2 file creation
# ------------------------------------------------------------------


def test_send_creates_pending_message_file(
    home: Path, sender_project: Path
) -> None:
    result = _send(sender_project)
    assert result["status"] == SENT
    inbox = home / ".engram" / "inbox" / "acme-service-b" / "pending"
    files = list(inbox.glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    fm_text, body = text.split("\n---\n", 1)[0][4:], text.split("\n---\n", 1)[1]
    fm = yaml.safe_load(fm_text)
    assert fm["from"] == "acme/service-a"
    assert fm["to"] == "acme/service-b"
    assert fm["intent"] == "bug-report"
    assert fm["status"] == "pending"
    assert fm["message_id"].startswith("acme/service-a:")
    # Body has all four sections.
    for marker in ("**What:**", "**Why:**", "**How to resolve"):
        assert marker in body


def test_send_writes_message_sent_journal_event(
    home: Path, sender_project: Path
) -> None:
    _send(sender_project)
    journal = home / ".engram" / "journal" / "inter_repo.jsonl"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert any(e["event"] == "message_sent" for e in events)


def test_send_rejects_invalid_intent(
    home: Path, sender_project: Path
) -> None:
    with pytest.raises(ValueError, match="intent"):
        _send(sender_project, intent="not-a-real-intent")


# ------------------------------------------------------------------
# Deduplication (SPEC §10.5)
# ------------------------------------------------------------------


def test_dedup_by_code_refs_merges_into_existing(
    home: Path, sender_project: Path
) -> None:
    ref = "src/api/users.py:L42@abc123def456"
    first = _send(sender_project, related_code_refs=[ref])
    second = _send(sender_project, related_code_refs=[ref])
    assert first["status"] == SENT
    assert second["status"] == DEDUP_DETECTED

    inbox = home / ".engram" / "inbox" / "acme-service-b" / "pending"
    files = list(inbox.glob("*.md"))
    assert len(files) == 1  # still one file
    text = files[0].read_text(encoding="utf-8")
    assert text.count("<!-- duplicate received") == 1


def test_dedup_by_first_line_fallback(
    home: Path, sender_project: Path
) -> None:
    first = _send(sender_project)
    # Same summary / sender / intent / no code refs → first-line fallback.
    second = _send(sender_project)
    assert second["status"] == DEDUP_DETECTED

    inbox = home / ".engram" / "inbox" / "acme-service-b" / "pending"
    files = list(inbox.glob("*.md"))
    assert len(files) == 1
    fm_text = files[0].read_text(encoding="utf-8").split("\n---\n")[0][4:]
    fm = yaml.safe_load(fm_text)
    assert fm.get("duplicate_count", 0) == 1


def test_dedup_explicit_key_wins(home: Path, sender_project: Path) -> None:
    first = _send(sender_project, dedup_key="user-404-bug", summary="A different summary")
    second = _send(
        sender_project, dedup_key="user-404-bug", summary="Yet another different summary"
    )
    assert second["status"] == DEDUP_DETECTED


# ------------------------------------------------------------------
# Rate limit (SPEC §10.5)
# ------------------------------------------------------------------


def test_rate_limit_pending_cap(home: Path, sender_project: Path) -> None:
    """Sending MAX_PENDING_PER_SENDER+1 distinct messages yields rate-limit."""
    for i in range(MAX_PENDING_PER_SENDER):
        r = _send(sender_project, summary=f"distinct bug {i}")
        assert r["status"] == SENT
    # One more distinct message trips the cap.
    over = _send(sender_project, summary="tripping bug")
    assert over["status"] == RATE_LIMIT_HIT
    assert "pending" in over["detail"].lower()


def test_rate_limit_hit_journaled(home: Path, sender_project: Path) -> None:
    for i in range(MAX_PENDING_PER_SENDER):
        _send(sender_project, summary=f"distinct {i}")
    _send(sender_project, summary="over the cap")
    journal = home / ".engram" / "journal" / "inter_repo.jsonl"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert any(e["event"] == "rate_limit_hit" for e in events)


def test_constants_track_spec() -> None:
    """SPEC §10.5 says 20 / 50 as defaults. Lock them here."""
    assert MAX_PENDING_PER_SENDER == 20
    assert MAX_PER_SENDER_PER_DAY == 50


# ------------------------------------------------------------------
# Lifecycle — acknowledge / resolve / reject
# ------------------------------------------------------------------


def _message_id_from_send(sender_project: Path) -> str:
    r = _send(sender_project)
    return r["message_id"]


def test_acknowledge_moves_file_and_updates_frontmatter(
    home: Path, sender_project: Path
) -> None:
    mid = _message_id_from_send(sender_project)
    acknowledge(recipient_id="acme/service-b", message_id=mid)

    ack_dir = home / ".engram" / "inbox" / "acme-service-b" / "acknowledged"
    pending_dir = home / ".engram" / "inbox" / "acme-service-b" / "pending"
    assert list(pending_dir.glob("*.md")) == []
    files = list(ack_dir.glob("*.md"))
    assert len(files) == 1
    fm = yaml.safe_load(files[0].read_text(encoding="utf-8").split("\n---\n")[0][4:])
    assert fm["status"] == "acknowledged"
    assert "acknowledged_at" in fm


def test_resolve_requires_note(home: Path, sender_project: Path) -> None:
    mid = _message_id_from_send(sender_project)
    with pytest.raises(ValueError, match="note"):
        resolve(recipient_id="acme/service-b", message_id=mid, note="")


def test_resolve_moves_and_sets_note(home: Path, sender_project: Path) -> None:
    mid = _message_id_from_send(sender_project)
    acknowledge(recipient_id="acme/service-b", message_id=mid)
    resolve(
        recipient_id="acme/service-b",
        message_id=mid,
        note="Fixed in commit abc123",
    )
    resolved_dir = home / ".engram" / "inbox" / "acme-service-b" / "resolved"
    files = list(resolved_dir.glob("*.md"))
    assert len(files) == 1
    fm = yaml.safe_load(files[0].read_text(encoding="utf-8").split("\n---\n")[0][4:])
    assert fm["status"] == "resolved"
    assert fm["resolution_note"] == "Fixed in commit abc123"


def test_reject_moves_and_sets_reason(home: Path, sender_project: Path) -> None:
    mid = _message_id_from_send(sender_project)
    reject(
        recipient_id="acme/service-b",
        message_id=mid,
        reason="Intentional behavior per API contract v2",
    )
    rej_dir = home / ".engram" / "inbox" / "acme-service-b" / "rejected"
    files = list(rej_dir.glob("*.md"))
    assert len(files) == 1


def test_resolved_is_terminal(home: Path, sender_project: Path) -> None:
    """SPEC §10.4: `resolved` cannot be re-opened."""
    mid = _message_id_from_send(sender_project)
    acknowledge(recipient_id="acme/service-b", message_id=mid)
    resolve(recipient_id="acme/service-b", message_id=mid, note="done")
    with pytest.raises(ValueError, match="terminal|not.*pending"):
        acknowledge(recipient_id="acme/service-b", message_id=mid)


# ------------------------------------------------------------------
# list_messages
# ------------------------------------------------------------------


def test_list_filters_by_status(home: Path, sender_project: Path) -> None:
    _send(sender_project, summary="first bug")
    _send(sender_project, summary="second bug")
    mid3 = _send(sender_project, summary="third bug")["message_id"]
    acknowledge(recipient_id="acme/service-b", message_id=mid3)

    pending = list_messages(recipient_id="acme/service-b", status="pending")
    acked = list_messages(recipient_id="acme/service-b", status="acknowledged")
    assert len(pending) == 2
    assert len(acked) == 1
    assert acked[0]["message_id"] == mid3


def test_list_priority_order(home: Path, sender_project: Path) -> None:
    """SPEC §10.3: severity → intent → deadline → created."""
    _send(sender_project, summary="low info", severity="info")
    _send(sender_project, summary="critical bug", severity="critical")
    _send(sender_project, summary="warn", severity="warning")
    msgs = list_messages(recipient_id="acme/service-b", status="pending")
    severities = [m["severity"] for m in msgs]
    assert severities == ["critical", "warning", "info"]


# ------------------------------------------------------------------
# CLI smoke — `engram inbox`
# ------------------------------------------------------------------


def test_cli_inbox_send_end_to_end(
    home: Path, sender_project: Path
) -> None:
    from click.testing import CliRunner

    from engram.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(sender_project),
            "inbox",
            "send",
            "--to",
            "acme/service-b",
            "--intent",
            "bug-report",
            "--summary",
            "CLI-sent test",
            "--what",
            "w",
            "--why",
            "y",
            "--how",
            "h",
        ],
    )
    assert result.exit_code == 0, result.output
    inbox = home / ".engram" / "inbox" / "acme-service-b" / "pending"
    assert list(inbox.glob("*.md"))


def test_cli_inbox_list_and_lifecycle(
    home: Path, sender_project: Path
) -> None:
    from click.testing import CliRunner

    from engram.cli import cli

    mid = _message_id_from_send(sender_project)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(sender_project),
            "inbox",
            "list",
            "--as",
            "acme/service-b",
        ],
    )
    assert result.exit_code == 0
    items = json.loads(result.output)
    assert any(m["message_id"] == mid for m in items)
