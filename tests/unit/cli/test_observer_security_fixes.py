"""Security + production-readiness regression tests (2026-04-30 audit).

Each test pins a specific finding from the parallel code-reviewer +
security-reviewer pass:

- A1 single-shot timestamp
- A2 millisecond preservation in Session round-trip
- A8 marker-bracketed Tier 1 narrative preserves user edits
- C1 daemon error journal records tier exceptions
- C3 provider error subtypes map HTTP codes correctly
- C4 timeline.jsonl single-write atomicity
- C5 settings.json backup written before merge
- F1 api_key env-var allowlist
- F2 cross-host redirect strips Authorization
- F3 distill/propose name regex validation
- F4 secret-path denylist
- F5 symlink files skipped
- F6 install refuses non-dict hooks
- F7 settings.json command pins ENGRAM_BIN
- F8 total-session cap raises QueueOverflowError
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner


# ----------------------------------------------------------------------
# A1 — protocol._server_timestamp uses single now()
# ----------------------------------------------------------------------


def test_a1_server_timestamp_single_shot() -> None:
    from engram.observer.protocol import _server_timestamp

    out = _server_timestamp()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", out)


# ----------------------------------------------------------------------
# A2 — _iso preserves milliseconds + tz round-trip
# ----------------------------------------------------------------------


def test_a2_session_iso_preserves_milliseconds(tmp_path: Path) -> None:
    from engram.observer.session import (
        SessionFrontmatter,
        parse_session_file,
        render_session_file,
        session_path,
    )

    started = datetime(2026, 4, 26, 14, 23, 1, 123_000, tzinfo=timezone.utc)
    fm = SessionFrontmatter(
        type="session",
        session_id="abc",
        client="claude-code",
        started_at=started,
        ended_at=started,
    )
    p = session_path("abc", started_at=started, memory_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, "body\n"))

    fm2, _ = parse_session_file(p)
    assert fm2.started_at == started


# ----------------------------------------------------------------------
# A8 — merge_auto_block preserves user edits outside the markers
# ----------------------------------------------------------------------


def test_a8_merge_first_write_preserves_user_prose() -> None:
    from engram.observer.tier1 import (
        AUTO_BLOCK_END,
        AUTO_BLOCK_START,
        merge_auto_block,
    )

    user_body = "## My Notes\n\n- A note I wrote\n"
    out = merge_auto_block(user_body, "## Investigated\n- daemon narrative\n")
    assert "A note I wrote" in out
    assert AUTO_BLOCK_START in out
    assert AUTO_BLOCK_END in out
    assert "daemon narrative" in out


def test_a8_merge_subsequent_replaces_only_inside_markers() -> None:
    from engram.observer.tier1 import (
        AUTO_BLOCK_END,
        AUTO_BLOCK_START,
        merge_auto_block,
    )

    initial = (
        "## My Notes\n\n- Pre-existing note\n\n"
        + AUTO_BLOCK_START
        + "\n## Investigated\n- old narrative\n"
        + AUTO_BLOCK_END
        + "\n\n## After\n- post-block note\n"
    )
    out = merge_auto_block(initial, "## Investigated\n- new narrative\n")
    assert "Pre-existing note" in out
    assert "post-block note" in out
    assert "new narrative" in out
    assert "old narrative" not in out


# ----------------------------------------------------------------------
# C1 — daemon error journal records tier exceptions
# ----------------------------------------------------------------------


def test_c1_daemon_journals_tier_errors(tmp_path: Path) -> None:
    from engram.observer.daemon import DaemonConfig, ObserverDaemon, PendingSession
    from engram.observer.protocol import parse_event
    from engram.observer.queue import enqueue

    base = tmp_path / "engram"
    base.mkdir()
    e = parse_event(
        {"event": "tool_use", "tool": "Read"},
        session_id="sess_abc",
        client="claude-code",
        now="2026-04-30T14:00:00.000Z",
    )
    enqueue(e, base=base)

    def boom(_p: PendingSession) -> None:
        raise RuntimeError("synthetic tier0 failure")

    daemon = ObserverDaemon(
        base=base,
        config=DaemonConfig(max_iterations=1, poll_interval_seconds=0),
        tier0_runner=boom,
        sleeper=lambda _s: None,
    )
    daemon.run_forever(install_signals=False)

    journal = base / "journal" / "observer.jsonl"
    assert journal.exists(), "C1: tier exception MUST land in observer.jsonl"
    lines = [ln for ln in journal.read_text().splitlines() if ln.strip()]
    assert lines, "expected at least one journal line"
    record = json.loads(lines[-1])
    assert record["tier"] == "tier0"
    assert record["session_id"] == "sess_abc"
    assert record["error_type"] == "RuntimeError"
    assert "synthetic" in record["message"]
    assert daemon.stats.tier0_errors == 1
    assert "synthetic" in (daemon.stats.last_error or "")


# ----------------------------------------------------------------------
# C3 — provider error subtypes map HTTP codes
# ----------------------------------------------------------------------


class _StubHTTPError(urllib.error.HTTPError):
    def __init__(self, code: int, reason: str = "synthetic") -> None:
        super().__init__("http://example", code, reason, {}, None)


def _opener_raising_http(code: int) -> Any:
    def _opener(req: Any, timeout: float = 0) -> Any:
        raise _StubHTTPError(code)

    return _opener


@pytest.mark.parametrize(
    "code,error_cls",
    [
        (401, "ProviderAuthError"),
        (403, "ProviderAuthError"),
        (429, "ProviderRateLimitError"),
        (502, "ProviderUnavailable"),
        (404, "ProviderError"),
    ],
)
def test_c3_openai_compat_http_error_mapping(code: int, error_cls: str) -> None:
    from engram.observer.providers import openai_compatible
    from engram.observer.providers.base import (
        ProviderAuthError,
        ProviderError,
        ProviderRateLimitError,
        ProviderUnavailable,
    )

    expected = {
        "ProviderAuthError": ProviderAuthError,
        "ProviderRateLimitError": ProviderRateLimitError,
        "ProviderUnavailable": ProviderUnavailable,
        "ProviderError": ProviderError,
    }[error_cls]

    p = openai_compatible.make_openai_compatible_provider(
        endpoint="https://api.example.com/v1",
        model="m",
        opener=_opener_raising_http(code),
    )
    with pytest.raises(expected):
        p("hi")


# ----------------------------------------------------------------------
# C4 — timeline.jsonl line is one write
# ----------------------------------------------------------------------


def test_c4_tier0_writes_single_line_atomically(tmp_path: Path) -> None:
    """If the daemon dies between payload and newline, the line stays valid.

    We can't actually SIGKILL inside a unit test, but we can prove the
    code path emits one ``write()`` per fact. Patch ``write`` on the
    file and assert the call count == fact count exactly (no extra
    bare ``\\n`` writes).
    """
    from engram.observer.protocol import parse_event
    from engram.observer.queue import enqueue
    from engram.observer.tier0 import compact_session

    base = tmp_path
    for kind in (
        {"event": "tool_use", "tool": "Read"},
        {"event": "session_end", "outcome": "completed"},
    ):
        e = parse_event(
            kind,
            session_id="sess_abc",
            client="claude-code",
            now="2026-04-30T14:00:00.000Z",
        )
        enqueue(e, base=base)

    qpath = base / "observe-queue" / "sess_abc.jsonl"
    sessions_dir = base / "timelines"

    write_calls: list[str] = []
    real_open = open

    def patched_open(*args: Any, **kwargs: Any) -> Any:
        f = real_open(*args, **kwargs)
        if (
            len(args) > 0
            and "timeline.jsonl" in str(args[0])
            and "a" in (args[1] if len(args) > 1 else kwargs.get("mode", ""))
        ):
            orig_write = f.write

            def _wrapped(s: Any) -> Any:
                write_calls.append(s)
                return orig_write(s)

            f.write = _wrapped  # type: ignore[method-assign]
        return f

    import builtins

    builtins.open = patched_open  # type: ignore[assignment]
    try:
        compact_session("sess_abc", queue_path=qpath, sessions_dir=sessions_dir)
    finally:
        builtins.open = real_open  # type: ignore[assignment]

    # Each fact is exactly one write call ending in "\n"; no orphan newline writes.
    fact_writes = [s for s in write_calls if s.endswith("\n")]
    bare_newlines = [s for s in write_calls if s == "\n"]
    assert len(fact_writes) == 2
    assert bare_newlines == []


# ----------------------------------------------------------------------
# C5 — settings.json backup before merge
# ----------------------------------------------------------------------


def test_c5_settings_backup_written_first_run(tmp_path: Path) -> None:
    from engram.observer.install import InstallPlan, apply_install_plan

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PostToolUse": [], "extra": "keep"}}))

    plan = InstallPlan(
        target="claude-code",
        action="write",
        hook_path=tmp_path / "fake_hook.sh",
        snippet="ignored",
        config_path=settings,
    )
    apply_install_plan(plan)
    backup = settings.with_suffix(".json.engram-bak")
    assert backup.exists(), "C5: backup MUST be written before merge"
    backed_up = json.loads(backup.read_text())
    assert backed_up["hooks"]["extra"] == "keep"


def test_c5_settings_backup_not_overwritten_on_reinstall(tmp_path: Path) -> None:
    from engram.observer.install import InstallPlan, apply_install_plan

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"orig": True}))
    plan = InstallPlan(
        target="claude-code",
        action="write",
        hook_path=tmp_path / "fake_hook.sh",
        snippet="ignored",
        config_path=settings,
    )
    apply_install_plan(plan)
    settings.write_text(json.dumps({"v2": True}))
    apply_install_plan(plan)
    backup = settings.with_suffix(".json.engram-bak")
    backed_up = json.loads(backup.read_text())
    # First-write-wins: backup retains the very first contents.
    assert backed_up == {"orig": True}


# ----------------------------------------------------------------------
# F1 — api_key env allowlist (positive/negative covered in test_observer_config.py;
# this test re-verifies the literal-path rejection at unit level)
# ----------------------------------------------------------------------


def test_f1_literal_path_like_token_refused() -> None:
    from engram.observer.config import ObserverConfigError, _resolve_env_ref

    with pytest.raises(ObserverConfigError):
        _resolve_env_ref("/Users/victim")


# ----------------------------------------------------------------------
# F2 — Authorization stripped on cross-host redirect
# ----------------------------------------------------------------------


def test_f2_redirect_handler_drops_auth_cross_host() -> None:
    import urllib.request

    from engram.observer.providers.openai_compatible import _NoCrossHostAuthRedirect

    handler = _NoCrossHostAuthRedirect()
    req = urllib.request.Request(
        "https://api.example.com/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
    )
    new = handler.redirect_request(req, fp=io.BytesIO(), code=302, msg="x", headers={}, newurl="https://attacker.example/x")
    assert new is not None
    assert "Authorization" not in (new.headers or {})
    assert "Authorization" not in (new.unredirected_hdrs or {})


def test_f2_redirect_handler_keeps_auth_same_host() -> None:
    import urllib.request

    from engram.observer.providers.openai_compatible import _NoCrossHostAuthRedirect

    handler = _NoCrossHostAuthRedirect()
    req = urllib.request.Request(
        "https://api.example.com/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
    )
    new = handler.redirect_request(
        req,
        fp=io.BytesIO(),
        code=302,
        msg="x",
        headers={},
        newurl="https://api.example.com/v2/chat/completions",
    )
    assert new is not None
    # Auth header survives same-host redirects (legitimate API moves).
    has_auth = "Authorization" in (new.headers or {}) or "Authorization" in (
        new.unredirected_hdrs or {}
    )
    assert has_auth


def test_f2_endpoint_scheme_validation() -> None:
    from engram.observer.providers.base import ProviderError
    from engram.observer.providers.openai_compatible import (
        make_openai_compatible_provider,
    )

    with pytest.raises(ProviderError):
        make_openai_compatible_provider(
            endpoint="file:///etc/passwd", model="m"
        )


# ----------------------------------------------------------------------
# F3 — distill/propose name validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand",
    ["promote", "reject"],
)
def test_f3_distill_rejects_path_traversal_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subcommand: str
) -> None:
    from engram.cli import cli
    from engram.commands.init import init_project

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    init_project(project, name="t", force=False)
    monkeypatch.setenv("ENGRAM_DIR", str(project))
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", subcommand, "../../etc/passwd"])
    assert result.exit_code != 0
    assert "invalid name" in result.output


def test_f3_propose_rejects_path_traversal_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from engram.cli import cli
    from engram.commands.init import init_project

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    init_project(project, name="t", force=False)
    monkeypatch.setenv("ENGRAM_DIR", str(project))
    runner = CliRunner()
    result = runner.invoke(cli, ["propose", "promote", "../../tmp/x"])
    assert result.exit_code != 0
    assert "invalid name" in result.output


# ----------------------------------------------------------------------
# F4 — secret-path denylist
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/etc/shadow",
        "/etc/passwd",
        "/Users/alice/.aws/credentials",
        "/Users/alice/.ssh/id_rsa",
        "/home/bob/.ssh/id_ed25519",
        "/home/bob/.gnupg/secring.gpg",
        "/srv/app/secrets.yaml",
        "/srv/app/.env",
        "/srv/app/.env.production",
        "/etc/private.pem",
        "/var/lib/app/server.key",
        "/Users/alice/.netrc",
    ],
)
def test_f4_secret_paths_redacted(path: str) -> None:
    from engram.observer.translators import REDACTED_PATH_MARKER, redact_path

    assert redact_path(path) == REDACTED_PATH_MARKER


@pytest.mark.parametrize(
    "path",
    [
        "src/foo.ts",
        "tests/test_foo.py",
        "README.md",
        "/Users/alice/projects/app/main.go",
    ],
)
def test_f4_normal_paths_pass_through(path: str) -> None:
    from engram.observer.translators import redact_path

    assert redact_path(path) == path


def test_f4_translator_redacts_in_extracted_files() -> None:
    from engram.observer.translators import REDACTED_PATH_MARKER, translate_claude_code

    out = translate_claude_code(
        {
            "tool_name": "Read",
            "tool_input": {"file_path": "/Users/alice/.aws/credentials"},
        }
    )
    assert out is not None
    assert out["files"] == [REDACTED_PATH_MARKER]


# ----------------------------------------------------------------------
# F5 — symlink files skipped under sessions/
# ----------------------------------------------------------------------


def test_f5_symlink_session_files_are_skipped(tmp_path: Path) -> None:
    """A symlinked session file MUST NOT be read by the loader."""
    from engram.observer.loader import load_session_continuations

    project = tmp_path / "proj"
    sessions = project / ".memory" / "sessions" / "2026-04-26"
    sessions.mkdir(parents=True)

    # Real session that should load.
    real = sessions / "sess_real.md"
    real.write_text(
        "---\n"
        "type: session\n"
        "session_id: real\n"
        "client: claude-code\n"
        "started_at: 2026-04-26T14:00:00Z\n"
        "task_hash: t1\n"
        "---\nbody\n"
    )
    # Symlink masquerading as a session.
    target = tmp_path / "secret.md"
    target.write_text("---\ntype: session\nsession_id: bad\nclient: claude-code\n"
                      "started_at: 2026-04-26T14:00:00Z\ntask_hash: t1\n---\n/etc/secret\n")
    (sessions / "sess_bad.md").symlink_to(target)

    out = load_session_continuations(project_root=project)
    ids = {c.session_id for c in out}
    assert ids == {"real"}


# ----------------------------------------------------------------------
# F6 — install refuses non-dict / non-list hooks
# ----------------------------------------------------------------------


def test_f6_install_refuses_non_dict_hooks(tmp_path: Path) -> None:
    from engram.observer.install import HooksMergeError, _merge_claude_code_settings

    with pytest.raises(HooksMergeError):
        _merge_claude_code_settings(
            {"hooks": "disabled"}, tmp_path / "fake.sh"
        )


def test_f6_install_refuses_non_list_post_tool_use(tmp_path: Path) -> None:
    from engram.observer.install import HooksMergeError, _merge_claude_code_settings

    with pytest.raises(HooksMergeError):
        _merge_claude_code_settings(
            {"hooks": {"PostToolUse": "disabled"}}, tmp_path / "fake.sh"
        )


# ----------------------------------------------------------------------
# F7 — settings.json command pins ENGRAM_BIN
# ----------------------------------------------------------------------


def test_f7_command_pins_engram_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engram.observer.install import _build_claude_code_command

    fake_engram = tmp_path / "engram-fake"
    fake_engram.write_text("#!/bin/sh\necho fake")
    fake_engram.chmod(0o755)

    monkeypatch.setattr("shutil.which", lambda _name: str(fake_engram))
    cmd = _build_claude_code_command(tmp_path / "hook.sh")
    assert cmd.startswith("ENGRAM_BIN=")
    assert str(fake_engram) in cmd
    assert str(tmp_path / "hook.sh") in cmd


def test_f7_command_falls_back_when_no_engram_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from engram.observer.install import _build_claude_code_command

    monkeypatch.setattr("shutil.which", lambda _name: None)
    cmd = _build_claude_code_command(Path("/abs/hook.sh"))
    assert cmd == "/abs/hook.sh"


# ----------------------------------------------------------------------
# F8 — total session cap raises QueueOverflowError; default sid refused
# ----------------------------------------------------------------------


def test_f8_total_session_cap_raises_overflow(tmp_path: Path) -> None:
    from engram.observer.protocol import parse_event
    from engram.observer.queue import QueueOverflowError, enqueue

    base = tmp_path
    for i in range(2):
        e = parse_event(
            {"event": "tool_use", "tool": "Read"},
            session_id=f"sess_{i}",
            client="claude-code",
            now="2026-04-30T14:00:00.000Z",
        )
        enqueue(e, base=base, max_total_sessions=2)

    e3 = parse_event(
        {"event": "tool_use", "tool": "Read"},
        session_id="sess_3",
        client="claude-code",
        now="2026-04-30T14:00:00.000Z",
    )
    with pytest.raises(QueueOverflowError):
        enqueue(e3, base=base, max_total_sessions=2)


def test_f8_existing_session_unaffected_by_overflow_cap(tmp_path: Path) -> None:
    """Adding to an EXISTING session never trips the global cap."""
    from engram.observer.protocol import parse_event
    from engram.observer.queue import enqueue

    base = tmp_path
    e = parse_event(
        {"event": "tool_use", "tool": "Read"},
        session_id="sess_a",
        client="claude-code",
        now="2026-04-30T14:00:00.000Z",
    )
    enqueue(e, base=base, max_total_sessions=1)
    # Cap=1 reached; same-session enqueue still works.
    e2 = parse_event(
        {"event": "tool_use", "tool": "Edit"},
        session_id="sess_a",
        client="claude-code",
        now="2026-04-30T14:00:01.000Z",
    )
    enqueue(e2, base=base, max_total_sessions=1)


def test_f8_observe_cli_overflow_returns_ok_false(tmp_path: Path) -> None:
    from engram.cli import cli

    runner = CliRunner()
    base = tmp_path / "engram"
    base.mkdir()
    # First fills the cap
    runner.invoke(
        cli,
        [
            "observe",
            "--session",
            "sess_a",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "Read"}),
            "--max-total-sessions",
            "1",
            "--base",
            str(base),
        ],
    )
    result = runner.invoke(
        cli,
        [
            "observe",
            "--session",
            "sess_b",
            "--client",
            "claude-code",
            "--event",
            json.dumps({"event": "tool_use", "tool": "Read"}),
            "--max-total-sessions",
            "1",
            "--base",
            str(base),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["reason"] == "queue_overflow"
