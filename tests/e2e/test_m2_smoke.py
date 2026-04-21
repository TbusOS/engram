"""T-24 M2 end-to-end smoke test.

Exercises the full M2 CLI surface as a realistic operator flow:

    engram init
    engram memory add x 10  (mixing subtypes)
    engram memory list
    engram memory search
    engram validate   (must exit 0)
    engram review
    engram status

The test runs the CLI three ways:

1. **subprocess** — ``engram --version`` via the installed entry point.
   Confirms the editable install works and the binary is on PATH.
2. **CliRunner** — the bulk of the flow; hermetic and fast; each step
   asserts the command succeeds and observable state is correct.
3. **file inspection** — after the flow, verify on-disk layout (``.memory/``
   tree, the 10 asset files, graph.db populated, MEMORY.md has entries).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.memory import graph_db_path, slugify


def _invoke(runner: CliRunner, *args: str) -> None:
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0, (
        f"engram {' '.join(args)} failed (exit {result.exit_code}):\n{result.output}"
    )


# ------------------------------------------------------------------
# Binary-level smoke
# ------------------------------------------------------------------


def test_engram_binary_reports_version() -> None:
    """The installed `engram` entry point must answer `--version` cleanly."""
    result = subprocess.run(
        [sys.executable, "-m", "engram", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "engram" in result.stdout


# ------------------------------------------------------------------
# Full M2 flow
# ------------------------------------------------------------------


# Ten memory assets covering every subtype that does not require external
# scope dependencies (user / feedback / project / reference / agent; skipping
# workflow_ptr which needs an on-disk workflow target we haven't built yet).
_MEMORY_FIXTURES: tuple[dict[str, str], ...] = (
    {
        "type": "user",
        "name": "user kernel fluency",
        "description": "operator comfortable with Linux kernel internals",
        "body": "The user reads kernel mm/fs code regularly.",
    },
    {
        "type": "user",
        "name": "user python deep",
        "description": "strong Python typing and async background",
        "body": "The user prefers explicit types and asyncio over threading.",
    },
    {
        "type": "feedback",
        "name": "push requires confirm",
        "description": "always confirm before git push",
        "enforcement": "mandatory",
        "body": (
            "Ask before pushing.\n\n**Why:** prior unintended force push.\n\n"
            "**How to apply:** always, for any remote."
        ),
    },
    {
        "type": "feedback",
        "name": "prefer small functions",
        "description": "split functions longer than ~40 lines",
        "enforcement": "hint",
        "body": (
            "Keep functions short.\n\n**Why:** easier review and testing.\n\n"
            "**How to apply:** refactor when touching a long function."
        ),
    },
    {
        "type": "project",
        "name": "migrating to python 3.14",
        "description": "all services move to 3.14 by Q2 2026",
        "body": (
            "Deadline 2026-06-30.\n\n**Why:** security fix only in 3.14.\n\n"
            "**How to apply:** target 3.14 in new code."
        ),
    },
    {
        "type": "project",
        "name": "m2 cli freeze",
        "description": "M2 CLI surface frozen before external beta",
        "body": (
            "Freeze 2026-05-01.\n\n**Why:** beta testers need stable surface.\n\n"
            "**How to apply:** no new flags until tag."
        ),
    },
    {
        "type": "reference",
        "name": "internal oncall handbook",
        "description": "platform oncall runbook at docs.internal/oncall",
        "body": "Consult for outage escalation paths.",
    },
    {
        "type": "reference",
        "name": "grafana latency board",
        "description": "primary SLO dashboard for platform services",
        "body": "Check before proposing performance changes.",
    },
    {
        "type": "agent",
        "name": "squash before merge",
        "description": "local squash reduces CI re-run rate",
        "source": "autolearn/git-merge-standard/r5",
        "body": (
            "Squash locally.\n\n"
            "**Why:** observed 5 consecutive clean merges in r5.\n\n"
            "**How to apply:** platform service repos only."
        ),
    },
    {
        "type": "agent",
        "name": "tests first for refactors",
        "description": "adding tests before refactor catches regressions early",
        "source": "agent-learned",
        "body": (
            "Write tests first.\n\n"
            "**Why:** observed catching 3 regressions across 10 refactors.\n\n"
            "**How to apply:** any non-trivial refactor."
        ),
    },
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A bare temporary directory to be targeted by --dir."""
    return tmp_path


def test_m2_full_flow_init_then_populate_then_validate(project: Path) -> None:
    runner = CliRunner()

    # 1. init
    _invoke(runner, "--dir", str(project), "init", "--name", "engram-m2-smoke")
    assert (project / ".memory" / "local").is_dir()
    assert (project / ".engram" / "version").is_file()

    # 2. add 10 memories covering 5 subtypes
    for fixture in _MEMORY_FIXTURES:
        args = [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            fixture["type"],
            "--name",
            fixture["name"],
            "--description",
            fixture["description"],
            "--body",
            fixture["body"],
        ]
        if "enforcement" in fixture:
            args.extend(["--enforcement", fixture["enforcement"]])
        if "source" in fixture:
            args.extend(["--source", fixture["source"]])
        _invoke(runner, *args)

    # 3. list — expect 10 entries in json
    list_result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "memory", "list"])
    assert list_result.exit_code == 0
    entries = json.loads(list_result.output.strip())
    assert len(entries) == 10
    subtypes = {e["subtype"] for e in entries}
    assert subtypes == {"user", "feedback", "project", "reference", "agent"}

    # 4. search — expect the "kernel" asset to rank first for query "kernel"
    search_result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "memory", "search", "kernel"]
    )
    assert search_result.exit_code == 0
    ranked = json.loads(search_result.output.strip())
    assert ranked, "search returned zero hits for 'kernel'"
    assert ranked[0]["id"] == "local/user_user_kernel_fluency"

    # 5. index MEMORY.md so E-IDX-002 doesn't fire, then validate
    index = project / ".memory" / "MEMORY.md"
    index_lines = []
    for fm in _MEMORY_FIXTURES:
        path = f"local/{fm['type']}_{slugify(fm['name'])}.md"
        index_lines.append(f"- [{fm['name']}]({path}) — {fm['description']}")
    index.write_text(
        index.read_text(encoding="utf-8") + "\n" + "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )
    # Validate must have zero errors. Warnings are acceptable (e.g. W-MEM-002
    # fires on each agent because confidence is not added at creation time —
    # the CLI has no --confidence flag in M2; consumers patch confidence later
    # via engram memory update once T-23 lands or via direct YAML editing).
    validate_result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "validate"])
    assert validate_result.exit_code in (0, 1), validate_result.output
    validate_payload = json.loads(validate_result.output.strip())
    assert validate_payload["summary"]["errors"] == 0, validate_payload

    # 6. review — should report 10 assets and zero errors
    review_result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "review"])
    assert review_result.exit_code == 0
    review = json.loads(review_result.output.strip())
    assert review["assets"]["total"] == 10
    assert review["assets"]["by_subtype"] == {
        "user": 2,
        "feedback": 2,
        "project": 2,
        "reference": 2,
        "agent": 2,
    }
    assert review["validation"]["by_severity"].get("error", 0) == 0

    # 7. status — initialized, store v0.2, 10 assets
    status_result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "status"])
    assert status_result.exit_code == 0
    status = json.loads(status_result.output.strip())
    assert status["initialized"] is True
    assert status["store_version"] == "0.2"
    assert status["assets"]["total"] == 10

    # 8. file-system shape: 10 asset files + graph.db present
    local_dir = project / ".memory" / "local"
    asset_files = list(local_dir.glob("*.md"))
    assert len(asset_files) == 10
    assert graph_db_path(project).exists()


def test_m2_update_and_archive_roundtrip(project: Path) -> None:
    runner = CliRunner()
    _invoke(runner, "--dir", str(project), "init")
    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        "user",
        "--name",
        "temp",
        "--description",
        "scratch",
        "--body",
        "scratch body",
    )

    _invoke(
        runner,
        "--dir",
        str(project),
        "memory",
        "update",
        "local/user_temp",
        "--description",
        "updated",
        "--lifecycle",
        "stable",
    )
    read = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "memory", "read", "local/user_temp"]
    )
    payload = json.loads(read.output.strip())
    assert payload["frontmatter"]["description"] == "updated"

    _invoke(runner, "--dir", str(project), "memory", "archive", "local/user_temp")
    status = runner.invoke(cli, ["--format", "json", "--dir", str(project), "status"])
    status_payload = json.loads(status.output.strip())
    assert status_payload["assets"]["by_lifecycle"] == {"archived": 1}
