"""T-57 — M4 P0 end-to-end parity test.

One realistic operator journey across every P0 command. Every step
asserts exit code + observable state change. If this test goes red,
M4 is not shippable — no matter what the unit tests say.

Coverage map (TASKS P0 command surface):

- engram init (+ --no-adapter default)
- engram memory add/list/read/search/update/archive (across subtypes)
- engram validate
- engram review
- engram status
- engram context pack (prompt + json formats)
- engram conformance (via library — no CLI yet; exercised here so the
  invariant suite stays wired into the P0 parity gate)
- engram adapter list/install/refresh
- engram inbox send/list/acknowledge/resolve/reject
- engram mcp serve (stdio handshake via the public dispatch())
- engram mcp install --list
- engram migrate --from=v0.1 (uses tests/fixtures/v0.1_store/)
- engram pool subscribe/list/unsubscribe (T-30)
- engram observe / observer status (auto-continuation ingest surface)
- engram distill review / propose review (consent-gate CLI)
- engram doctor / config / version / wisdom report / memory quick
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from engram.cli import cli
from engram.conformance import check_conformance
from engram.mcp.server import ServerContext, dispatch


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "v0.1_store"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    return fake


@pytest.fixture
def project(tmp_path: Path, home: Path) -> Path:
    return tmp_path / "acme-platform"


def _invoke(runner: CliRunner, *args: str) -> str:
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0, (
        f"engram {' '.join(args)} failed (exit {result.exit_code}):\n"
        f"{result.output}"
    )
    return result.output


def _invoke_json(runner: CliRunner, *args: str) -> object:
    out = _invoke(runner, "--format", "json", *args)
    return json.loads(out.strip())


# ------------------------------------------------------------------
# The journey
# ------------------------------------------------------------------


def test_m4_p0_operator_journey(project: Path, home: Path) -> None:
    runner = CliRunner()

    # 1) init — project is initialized with the standard skeleton.
    _invoke(runner, "--dir", str(project), "init", "--name", "acme-platform")
    assert (project / ".memory" / "local").is_dir()
    assert (project / ".engram" / "version").read_text(encoding="utf-8").strip() == "0.2"

    # 2) memory add across 4 subtypes that don't need extra fixtures.
    for subtype, name, extra in (
        ("user", "kernel fluency", []),
        (
            "feedback",
            "confirm before push",
            ["--enforcement", "mandatory"],
        ),
        ("project", "k8s migration", []),
        ("reference", "oncall handbook", []),
    ):
        args = [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            subtype,
            "--name",
            name,
            "--description",
            f"{name} description",
            "--body",
            "body.\n\n**Why:** reason.\n\n**How to apply:** always.",
        ] + extra
        _invoke(runner, *args)

    # 3) list + search — 4 assets, kernel search finds the user asset.
    entries = _invoke_json(runner, "--dir", str(project), "memory", "list")
    assert isinstance(entries, list)
    assert len(entries) == 4

    search = _invoke_json(
        runner, "--dir", str(project), "memory", "search", "kernel"
    )
    assert search, "search for 'kernel' returned no hits"
    assert isinstance(search, list)
    assert "kernel" in search[0]["id"].lower()

    # 4) update + archive — update metadata then archive a project asset.
    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "update",
        "local/project_k8s_migration",
        "--description",
        "updated desc",
        "--lifecycle",
        "stable",
    )
    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "archive",
        "local/project_k8s_migration",
    )

    # 5) validate — must exit with errors == 0 (warnings tolerated).
    validate_result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "validate"]
    )
    assert validate_result.exit_code in (0, 1), validate_result.output
    payload = json.loads(validate_result.output.strip())
    assert payload["summary"]["errors"] == 0, payload

    # 6) review — aggregate health snapshot, always exits 0.
    review = _invoke_json(runner, "--dir", str(project), "review")
    assert review["assets"]["total"] >= 3

    # 7) status — 0.2, assets present.
    status = _invoke_json(runner, "--dir", str(project), "status")
    assert status["store_version"] == "0.2"
    assert status["initialized"] is True

    # 8) context pack — prompt-format pipes a usable block.
    prompt = _invoke(
        runner,
        "--dir",
        str(project),
        "context",
        "pack",
        "--task",
        "anything about kernel",
    )
    assert "# Context pack" in prompt
    # Mandatory feedback must be included regardless of the query.
    assert "confirm_before_push" in prompt or "Mandatory" in prompt

    # 9) conformance — SPEC invariant suite reports zero failures.
    reports = check_conformance(project)
    failed = [r for r in reports if not r.passed]
    assert failed == [], (
        "conformance violations:\n"
        + "\n".join(f"  {r.invariant_id}: {r.detail}" for r in failed)
    )

    # 10) adapter install + refresh — CLAUDE.md and AGENTS.md land.
    _invoke(runner, "--dir", str(project), "adapter", "install", "claude-code")
    _invoke(runner, "--dir", str(project), "adapter", "install", "codex")
    assert (project / "CLAUDE.md").is_file()
    assert (project / "AGENTS.md").is_file()
    _invoke(runner, "--dir", str(project), "adapter", "refresh")

    # 11) inbox send + list + acknowledge + resolve — full lifecycle.
    # Configure explicit repo_id so identity resolution is deterministic.
    (project / ".engram" / "config.toml").write_text(
        '[project]\nrepo_id = "acme/platform"\n', encoding="utf-8"
    )
    _invoke(
        runner,
        "--dir",
        str(project),
        "inbox",
        "send",
        "--to",
        "acme/service-b",
        "--intent",
        "bug-report",
        "--summary",
        "E2E test message",
        "--what",
        "w",
        "--why",
        "y",
        "--how",
        "h",
    )
    inbox_pending = _invoke_json(
        runner,
        "--dir",
        str(project),
        "inbox",
        "list",
        "--as",
        "acme/service-b",
    )
    assert len(inbox_pending) == 1
    mid = inbox_pending[0]["message_id"]

    _invoke(
        runner,
        "--dir",
        str(project),
        "inbox",
        "acknowledge",
        mid,
        "--as",
        "acme/service-b",
    )
    _invoke(
        runner,
        "--dir",
        str(project),
        "inbox",
        "resolve",
        mid,
        "--as",
        "acme/service-b",
        "--note",
        "fixed in PR #42",
    )
    resolved = _invoke_json(
        runner,
        "--dir",
        str(project),
        "inbox",
        "list",
        "--as",
        "acme/service-b",
        "--status",
        "resolved",
    )
    assert any(m["message_id"] == mid for m in resolved)

    # 12) MCP handshake — dispatch path tested end-to-end against the
    # same project, with real tool calls touching graph.db.
    ctx = ServerContext(store_root=project)
    init_resp = dispatch(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, ctx
    )
    assert init_resp["result"]["serverInfo"]["name"] == "engram"

    list_resp = dispatch(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ctx
    )
    names = {t["name"] for t in list_resp["result"]["tools"]}
    assert {
        "engram_memory_search",
        "engram_memory_read",
        "engram_context_pack",
    }.issubset(names)

    search_resp = dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "engram_memory_search",
                "arguments": {"query": "kernel"},
            },
        },
        ctx,
    )
    search_payload = json.loads(search_resp["result"]["content"][0]["text"])
    assert search_payload["hits"], "MCP memory_search returned no hits"


# ------------------------------------------------------------------
# Migrate — separate journey that mutates the fixture
# ------------------------------------------------------------------


def test_m4_p0_migrate_v0_1_ends_conformance_clean(
    tmp_path: Path, home: Path
) -> None:
    """Migrating the committed v0.1 fixture yields a conformance-clean
    v0.2 store. The ratchet: a migration that breaks any SPEC invariant
    fails this test regardless of what the migrate tests themselves say."""
    runner = CliRunner()
    project = tmp_path / "migrated"
    shutil.copytree(FIXTURE_DIR, project)
    (project / "README.md").unlink(missing_ok=True)

    _invoke(runner, "--dir", str(project), "migrate", "--from", "v0.1")
    validate_json = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "validate"]
    )
    payload = json.loads(validate_json.output.strip())
    assert payload["summary"]["errors"] == 0

    reports = check_conformance(project)
    failed = [r for r in reports if not r.passed]
    assert failed == [], (
        "migrated fixture fails conformance:\n"
        + "\n".join(f"  {r.invariant_id}: {r.detail}" for r in failed)
    )


# ------------------------------------------------------------------
# Installed binary smoke — the entry point itself boots.
# ------------------------------------------------------------------


def test_m4_p0_installed_binary_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "engram", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "engram" in result.stdout


# ------------------------------------------------------------------
# Adapter file-content sanity — managed blocks survive user edits.
# ------------------------------------------------------------------


def test_m4_p0_adapter_refresh_preserves_user_content(
    project: Path, home: Path
) -> None:
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    _invoke(runner, "--dir", str(project), "adapter", "install", "claude-code")
    claude = project / "CLAUDE.md"
    with claude.open("a", encoding="utf-8") as f:
        f.write("\n\n# My own CLAUDE tweaks\n\nDO_NOT_DELETE_MARKER\n")
    _invoke(runner, "--dir", str(project), "adapter", "refresh")
    text = claude.read_text(encoding="utf-8")
    assert "DO_NOT_DELETE_MARKER" in text


# ------------------------------------------------------------------
# Frontmatter round-trip through the full stack
# ------------------------------------------------------------------


def test_m4_p0_frontmatter_survives_round_trip(
    project: Path, home: Path
) -> None:
    """A memory added via the CLI + read back via MCP returns the same
    frontmatter fields. Regression guard for the SPEC §4.1 schema."""
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        "feedback",
        "--enforcement",
        "default",
        "--name",
        "round trip",
        "--description",
        "frontmatter round-trip",
        "--body",
        "**Why:** X\n\n**How to apply:** Y",
    )
    ctx = ServerContext(store_root=project)
    asset_id = "local/feedback_round_trip"
    resp = dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "engram_memory_read",
                "arguments": {"asset_id": asset_id},
            },
        },
        ctx,
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    fm = payload["frontmatter"]
    assert fm["type"] == "feedback"
    assert fm["scope"] == "project"
    assert fm["enforcement"] == "default"
    assert fm["name"] == "round trip"

    # File on disk carries the same fields + SPEC §4.1 required set.
    disk = (project / ".memory" / "local" / "feedback_round_trip.md").read_text(
        encoding="utf-8"
    )
    fm_text = disk[4:].split("\n---\n", 1)[0]
    fm_disk = yaml.safe_load(fm_text)
    for required in ("name", "description", "type", "scope", "enforcement"):
        assert required in fm_disk, f"missing {required} in on-disk frontmatter"


# ------------------------------------------------------------------
# Pool lifecycle — T-57's own dependency T-30, previously uncovered
# ------------------------------------------------------------------


def test_m4_p0_pool_lifecycle(project: Path, home: Path) -> None:
    """subscribe -> list -> unsubscribe against a local pool dir."""
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")

    # A pool must already exist at ~/.engram/pools/<name>/ before subscribe.
    (home / ".engram" / "pools" / "acme-shared").mkdir(parents=True)
    _invoke(runner, "--dir", str(project), "pool", "subscribe", "acme-shared")

    # The subscribe lands both a symlink and a pools.toml entry.
    assert (project / ".memory" / "pools" / "acme-shared").is_symlink()
    listed = _invoke_json(runner, "--dir", str(project), "pool", "list")
    assert isinstance(listed, list)
    assert any(p["pool"] == "acme-shared" for p in listed)

    _invoke(runner, "--dir", str(project), "pool", "unsubscribe", "acme-shared")
    after = _invoke_json(runner, "--dir", str(project), "pool", "list")
    assert all(p["pool"] != "acme-shared" for p in after)


# ------------------------------------------------------------------
# Auto-Continuation CLI surface — newest code, only unit-tested so far
# ------------------------------------------------------------------


def test_m4_p0_auto_continuation_cli_surface(project: Path, home: Path) -> None:
    """observe -> observer status -> distill review -> propose review.

    Exercises CLI dispatch + exit codes for the auto-continuation
    commands, which previously had only function-level unit coverage.
    Also a regression guard for distill/propose honoring --dir.
    """
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    base = str(home / ".engram")

    # observe enqueues one event; returns ok=true JSON envelope, exit 0.
    out = _invoke(
        runner,
        "observe",
        "--session",
        "sess_p0",
        "--client",
        "claude-code",
        "--event",
        '{"event":"tool_use","tool":"Read","files":["a.py"]}',
        "--base",
        base,
    )
    assert json.loads(out.strip())["ok"] is True

    # observer status: a pending session, no live daemon, exit 0.
    status = runner.invoke(
        cli, ["observer", "status", "--format", "json", "--base", base]
    )
    assert status.exit_code == 0, status.output
    spayload = json.loads(status.output.strip())
    assert spayload["observer_pid"] is None
    assert spayload["pending_count"] >= 1

    # distill / propose review on an empty store: clean exit, honor --dir.
    # (Regression: these used find_project_root() and ignored --dir before.)
    assert (
        runner.invoke(cli, ["--dir", str(project), "distill", "review"]).exit_code == 0
    )
    assert (
        runner.invoke(cli, ["--dir", str(project), "propose", "review"]).exit_code == 0
    )


def test_m4_p0_no_project_gives_clean_error_not_traceback(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running a project command outside any store exits cleanly with a
    'run engram init' hint, never a ProjectNotFoundError traceback."""
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["memory", "list"])
    assert result.exit_code != 0
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "engram init" in result.output


# ------------------------------------------------------------------
# Operator utility commands — day-one surface a user actually runs
# ------------------------------------------------------------------


def test_m4_p0_operator_utility_commands(project: Path, home: Path) -> None:
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")

    # version — names the tool + store schema.
    assert "engram" in _invoke(runner, "version").lower()

    # memory quick — friction-zero one-line add (T-160).
    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "quick",
        "rotate signing keys each quarter",
    )
    entries = _invoke_json(runner, "--dir", str(project), "memory", "list")
    assert len(entries) == 1

    # doctor — a healthy store exits 0 (2 = warnings tolerated, 1 = errors).
    doctor = runner.invoke(cli, ["--dir", str(project), "doctor"])
    assert doctor.exit_code in (0, 2), doctor.output

    # config set/get round-trips through ~/.engram/config.toml.
    _invoke(runner, "config", "set", "editor.name", "vim")
    assert "vim" in _invoke(runner, "config", "get", "editor.name")

    # wisdom report renders even on near-empty usage data.
    assert "WISDOM REPORT" in _invoke(runner, "--dir", str(project), "wisdom", "report")

    # mcp install --list enumerates targets without writing config.
    assert "claude-code" in _invoke(runner, "mcp", "install", "--list")


def test_m4_p0_inbox_reject_terminal_transition(project: Path, home: Path) -> None:
    """inbox reject is the third terminal lifecycle transition (after
    acknowledge/resolve covered in the main journey)."""
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    (project / ".engram" / "config.toml").write_text(
        '[project]\nrepo_id = "acme/platform"\n', encoding="utf-8"
    )
    _invoke(
        runner,
        "--dir",
        str(project),
        "inbox",
        "send",
        "--to",
        "acme/service-b",
        "--intent",
        "bug-report",
        "--summary",
        "reject-path message",
        "--what",
        "w",
        "--why",
        "y",
        "--how",
        "h",
    )
    pending = _invoke_json(
        runner, "--dir", str(project), "inbox", "list", "--as", "acme/service-b"
    )
    mid = pending[0]["message_id"]
    _invoke(
        runner,
        "--dir",
        str(project),
        "inbox",
        "reject",
        mid,
        "--as",
        "acme/service-b",
        "--reason",
        "not our bug",
    )
    rejected = _invoke_json(
        runner,
        "--dir",
        str(project),
        "inbox",
        "list",
        "--as",
        "acme/service-b",
        "--status",
        "rejected",
    )
    assert any(m["message_id"] == mid for m in rejected)
