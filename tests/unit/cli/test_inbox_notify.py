"""Tests for inbox reverse notification (SPEC §10.4, T-96)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.inbox import (
    acknowledge,
    collect_reverse_notifications,
    render_reverse_notifications,
    resolve,
    send_message,
)


@pytest.fixture
def two_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    a, b = tmp_path / "svc-a", tmp_path / "svc-b"
    runner = CliRunner()
    for root, rid in ((a, "acme/service-a"), (b, "acme/service-b")):
        assert runner.invoke(cli, ["--dir", str(root), "init"]).exit_code == 0
        (root / ".engram" / "config.toml").write_text(
            f'[project]\nrepo_id = "{rid}"\n', encoding="utf-8"
        )
    return a, b


def _send(a: Path, summary: str = "GET 404 fix") -> str:
    result = send_message(
        project_root=a,
        to="acme/service-b",
        intent="bug-report",
        summary=summary,
        what="w",
        why="y",
        how="h",
    )
    return result["message_id"]


def test_sender_sees_resolution_once(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="Fixed in abc123")

    notes = collect_reverse_notifications(a)
    assert len(notes) == 1
    assert notes[0].label == "RESOLVED"
    assert notes[0].message_id == mid
    assert notes[0].detail == "Fixed in abc123"

    # Second call: watermark advanced, nothing new.
    assert collect_reverse_notifications(a) == []


def test_acknowledge_then_resolve_both_surface(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    acknowledge(message_id=mid, recipient_id="acme/service-b")
    first = collect_reverse_notifications(a)
    assert [n.label for n in first] == ["ACK"]

    resolve(message_id=mid, recipient_id="acme/service-b", note="done")
    second = collect_reverse_notifications(a)
    assert [n.label for n in second] == ["RESOLVED"]


def test_advance_false_does_not_consume(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="x")
    peek = collect_reverse_notifications(a, advance=False)
    assert len(peek) == 1
    # Cursor not advanced → still visible.
    assert len(collect_reverse_notifications(a, advance=False)) == 1


def test_only_own_sent_messages_surface(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="x")
    # B is the recipient, not the sender — B sees no reverse notifications.
    assert collect_reverse_notifications(b) == []


def test_render_empty_is_blank() -> None:
    assert render_reverse_notifications([]) == ""


def test_render_includes_note(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="see PR 42")
    block = render_reverse_notifications(collect_reverse_notifications(a))
    assert "RESOLVED" in block
    assert "see PR 42" in block
    assert "acme/service-b" in block


def test_no_journal_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    root = tmp_path / "proj"
    CliRunner().invoke(cli, ["--dir", str(root), "init"])
    assert collect_reverse_notifications(root) == []


# ------------------------------------------------------------------
# CLI wiring — review / status surface the block
# ------------------------------------------------------------------


def test_review_surfaces_updates(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="fixed")
    res = CliRunner().invoke(cli, ["--dir", str(a), "review"])
    assert res.exit_code == 0
    assert "Cross-repo inbox" in res.output
    assert "RESOLVED" in res.output
    # Consumed: a second review does not repeat.
    res2 = CliRunner().invoke(cli, ["--dir", str(a), "review"])
    assert "RESOLVED" not in res2.output


def test_review_json_includes_inbox_updates(two_repos: tuple[Path, Path]) -> None:
    import json

    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="fixed")
    res = CliRunner().invoke(cli, ["--dir", str(a), "--format", "json", "review"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    assert any(u["message_id"] == mid for u in payload["inbox_updates"])


def test_status_surfaces_updates(two_repos: tuple[Path, Path]) -> None:
    a, b = two_repos
    mid = _send(a)
    resolve(message_id=mid, recipient_id="acme/service-b", note="fixed")
    res = CliRunner().invoke(cli, ["--dir", str(a), "status"])
    assert res.exit_code == 0
    assert "Cross-repo inbox" in res.output
