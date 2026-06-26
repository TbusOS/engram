"""T-200 tests for engram.observer.cli — engram observe command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from engram.observer.cli import observe_cmd
from engram.observer.paths import queue_file_for_session, raw_session_file


def _run(runner: CliRunner, args: list[str], stdin: str | None = None):
    return runner.invoke(observe_cmd, args, input=stdin)


def test_observe_via_event_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "Read"}),
            "--base",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["queue_depth"] == 1
    assert payload["session_id"] == "sess_abc"
    assert payload["kind"] == "tool_use"


def test_observe_via_stdin(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "codex",
            "--base",
            str(tmp_path),
        ],
        stdin=json.dumps({"event": "user_prompt", "prompt_chars": 50}),
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True


def test_observe_writes_to_queue_file(tmp_path: Path) -> None:
    runner = CliRunner()
    _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "cursor",
            "--event",
            json.dumps({"event": "tool_use", "tool": "Edit"}),
            "--base",
            str(tmp_path),
        ],
    )
    path = queue_file_for_session("sess_abc", base=tmp_path)
    assert path.exists()
    line = json.loads(path.read_text().strip())
    assert line["tool"] == "Edit"
    assert line["client"] == "cursor"


def test_observe_raw_retention_keeps_full_prompt(tmp_path: Path) -> None:
    """C8 end-to-end — a prompt large enough that parse_event trims it from
    the queue line still lands in full in the raw-retention file."""
    runner = CliRunner()
    big = "Z" * 6000
    _run(
        runner,
        [
            "--session", "sess_abc",
            "--client", "claude-code",
            "--event", json.dumps({"event": "tool_use", "tool": "Edit", "prompt": big}),
            "--raw-retention",
            "--base", str(tmp_path),
        ],
    )
    queue_line = queue_file_for_session("sess_abc", base=tmp_path).read_text()
    assert big not in queue_line  # trimmed out of the queue line
    raw = raw_session_file("sess_abc", base=tmp_path).read_text()
    assert big in raw  # preserved in full in the raw file


def test_observe_payload_session_id_does_not_override_cli(tmp_path: Path) -> None:
    """F15 — the CLI --session is the source of truth; a session_id smuggled
    in the event payload never redirects the queue file."""
    runner = CliRunner()
    _run(
        runner,
        [
            "--session", "sess_good",
            "--client", "claude-code",
            "--event", json.dumps({"event": "tool_use", "tool": "Read", "session_id": "evil"}),
            "--base", str(tmp_path),
        ],
    )
    assert queue_file_for_session("sess_good", base=tmp_path).exists()
    assert not queue_file_for_session("evil", base=tmp_path).exists()


def test_observe_text_format(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "Read"}),
            "--format",
            "text",
            "--base",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "ok queued" in result.output
    assert "depth=1" in result.output


def test_observe_invalid_json(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            "not json",
            "--base",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert "invalid_json" in payload["reason"]


def test_observe_invalid_session_id(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "BAD/ID",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use"}),
            "--base",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert "invalid_session_id" in payload["reason"]


def test_observe_unknown_event_kind(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "telepathy"}),
            "--base",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert "protocol_error" in payload["reason"]


def test_observe_queue_full_returns_ok_false_exit_zero(tmp_path: Path) -> None:
    """Queue full is non-fatal — hooks must `|| true` cleanly."""
    runner = CliRunner()
    # Cap=1, fill once.
    r1 = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "A"}),
            "--max-events-per-session",
            "1",
            "--base",
            str(tmp_path),
        ],
    )
    assert r1.exit_code == 0
    # Second call hits the cap.
    r2 = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "B"}),
            "--max-events-per-session",
            "1",
            "--base",
            str(tmp_path),
        ],
    )
    assert r2.exit_code == 0  # exit zero, but ok=false
    payload = json.loads(r2.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["reason"] == "queue_full"


def test_observe_empty_payload(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "claude-code",
            "--base",
            str(tmp_path),
        ],
        stdin="",
    )
    assert result.exit_code == 2
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["reason"] == "empty_payload"


def test_observe_invalid_client_choice(tmp_path: Path) -> None:
    runner = CliRunner()
    result = _run(
        runner,
        [
            "--session",
            "sess_abc",
            "--client",
            "made-up-client",
            "--event",
            json.dumps({"event": "tool_use"}),
            "--base",
            str(tmp_path),
        ],
    )
    # click rejects invalid choice with exit code 2.
    assert result.exit_code == 2
