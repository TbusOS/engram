"""T-19 tests for engram.commands.memory — CRUD + BM25 search."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project
from engram.commands.memory import (
    compute_id,
    graph_db_path,
    memory_file_path,
    render_asset_file,
    sha256_hex,
    slugify,
)
from engram.core.frontmatter import (
    Enforcement,
    MemoryFrontmatter,
    MemoryType,
    Scope,
    parse_frontmatter,
)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    """An initialized engram project at tmp_path."""
    init_project(tmp_path)
    yield tmp_path


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("kernel fluency", "kernel_fluency"),
        ("Kernel Fluency", "kernel_fluency"),
        ("multi   spaces", "multi_spaces"),
        ("punctuation!!!", "punctuation"),
        ("symbols/and.dots", "symbols_and_dots"),
        ("你好 world 42", "world_42"),
        ("   leading_trailing   ", "leading_trailing"),
        ("", "untitled"),
        ("!!!", "untitled"),
    ],
)
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_compute_id_format() -> None:
    assert compute_id("local", "feedback", "push_confirm") == "local/feedback_push_confirm"


def test_memory_file_path_uses_dot_memory(tmp_path: Path) -> None:
    path = memory_file_path(tmp_path, "local", "user", "kernel_fluency")
    assert path == tmp_path / ".memory" / "local" / "user_kernel_fluency.md"


def test_graph_db_path_is_project_local(tmp_path: Path) -> None:
    """M2 choice: graph.db lives at <project>/.engram/graph.db (see project memory)."""
    assert graph_db_path(tmp_path) == tmp_path / ".engram" / "graph.db"


def test_sha256_hex_deterministic() -> None:
    a = sha256_hex("hello")
    b = sha256_hex("hello")
    assert a == b
    assert a != sha256_hex("world")
    # sha256 hex digest is 64 chars
    assert len(a) == 64


def test_render_asset_file_round_trips() -> None:
    """Written frontmatter must be re-parseable by parse_frontmatter."""
    fm = MemoryFrontmatter(
        name="test name",
        description="one-line hook",
        type=MemoryType.FEEDBACK,
        scope=Scope.PROJECT,
        enforcement=Enforcement.DEFAULT,
        tags=("go", "testing"),
    )
    content = render_asset_file(fm, "This is the body.\nSecond line.\n")
    reparsed = parse_frontmatter(content)
    assert reparsed.name == fm.name
    assert reparsed.description == fm.description
    assert reparsed.type is MemoryType.FEEDBACK
    assert reparsed.scope is Scope.PROJECT
    assert reparsed.enforcement is Enforcement.DEFAULT
    assert reparsed.tags == ("go", "testing")
    assert "This is the body." in content


def test_render_asset_file_omits_none_fields() -> None:
    fm = MemoryFrontmatter(
        name="x",
        description="y",
        type=MemoryType.USER,
        scope=Scope.USER,
        enforcement=Enforcement.HINT,
    )
    content = render_asset_file(fm, "body")
    # Optional fields should not appear when unset
    assert "created:" not in content
    assert "expires:" not in content
    assert "confidence:" not in content
    assert "workflow_ref:" not in content


# ------------------------------------------------------------------
# memory add
# ------------------------------------------------------------------


def test_add_creates_file_and_graph_db_row(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "kernel fluency",
            "--description",
            "user is comfortable with Linux kernel mm/fs concepts",
            "--body",
            "The user reads kernel source regularly and doesn't need term-level hand-holding.",
        ],
    )
    assert result.exit_code == 0, result.output
    file_path = project / ".memory" / "local" / "user_kernel_fluency.md"
    assert file_path.exists()

    with sqlite3.connect(graph_db_path(project)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets").fetchone()
    assert row is not None
    assert row["id"] == "local/user_kernel_fluency"
    assert row["subtype"] == "user"
    assert row["kind"] == "memory"
    assert row["lifecycle_state"] == "active"


def test_add_feedback_requires_enforcement(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "feedback",
            "--name",
            "push requires confirm",
            "--description",
            "explicit confirmation before git push",
            "--body",
            "Ask before push.\n\n**Why:** prior accident.\n**How to apply:** always.",
        ],
    )
    assert result.exit_code != 0
    assert "enforcement" in result.output.lower()


def test_add_feedback_with_enforcement_succeeds(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "feedback",
            "--name",
            "push confirm",
            "--description",
            "explicit confirmation before push",
            "--enforcement",
            "mandatory",
            "--body",
            "Ask.\n\n**Why:** safety.\n**How to apply:** always.",
        ],
    )
    assert result.exit_code == 0, result.output


def test_add_workflow_ptr_requires_workflow_ref(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "workflow_ptr",
            "--name",
            "git merge",
            "--description",
            "standard merge procedure",
            "--body",
            "See workflow.",
        ],
    )
    assert result.exit_code != 0
    assert "workflow_ref" in result.output.lower()


def test_add_agent_requires_source(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "agent",
            "--name",
            "squash before merge",
            "--description",
            "squashing reduces CI re-run",
            "--body",
            "Squash.\n\n**Why:** observed.\n**How to apply:** platform repos.",
        ],
    )
    assert result.exit_code != 0
    assert "source" in result.output.lower()


def test_add_duplicate_errors_without_force(project: Path) -> None:
    runner = CliRunner()
    args = [
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        "user",
        "--name",
        "dup",
        "--description",
        "d",
        "--body",
        "b",
    ]
    assert runner.invoke(cli, args).exit_code == 0
    result = runner.invoke(cli, args)
    assert result.exit_code != 0
    assert "exists" in result.output.lower()


def test_add_force_overwrites(project: Path) -> None:
    runner = CliRunner()
    base_args = [
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        "user",
        "--name",
        "dup",
        "--description",
        "first",
        "--body",
        "first body",
    ]
    assert runner.invoke(cli, base_args).exit_code == 0

    force_args = base_args.copy()
    force_args[force_args.index("--description") + 1] = "second"
    force_args[force_args.index("--body") + 1] = "second body"
    force_args.append("--force")
    result = runner.invoke(cli, force_args)
    assert result.exit_code == 0, result.output

    file_path = project / ".memory" / "local" / "user_dup.md"
    content = file_path.read_text(encoding="utf-8")
    assert "second body" in content
    assert "first body" not in content


def test_add_tags_repeatable(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "tagged",
            "--description",
            "d",
            "--tags",
            "alpha",
            "--tags",
            "beta",
            "--body",
            "b",
        ],
    )
    assert result.exit_code == 0, result.output
    file_path = project / ".memory" / "local" / "user_tagged.md"
    content = file_path.read_text(encoding="utf-8")
    assert "alpha" in content
    assert "beta" in content


def test_add_body_from_stdin(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "stdin-body",
            "--description",
            "d",
            "--body",
            "-",
        ],
        input="body from stdin\n",
    )
    assert result.exit_code == 0, result.output
    file_path = project / ".memory" / "local" / "user_stdin_body.md"
    content = file_path.read_text(encoding="utf-8")
    assert "body from stdin" in content


def test_add_json_output(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "json out",
            "--description",
            "d",
            "--body",
            "b",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert payload["id"] == "local/user_json_out"
    assert payload["path"].endswith(".memory/local/user_json_out.md")


# ------------------------------------------------------------------
# memory list
# ------------------------------------------------------------------


def test_list_empty_project(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--dir", str(project), "memory", "list"])
    assert result.exit_code == 0


def test_list_after_adds_text(project: Path) -> None:
    runner = CliRunner()
    for n in ("alpha", "beta", "gamma"):
        assert (
            runner.invoke(
                cli,
                [
                    "--dir",
                    str(project),
                    "memory",
                    "add",
                    "--type",
                    "user",
                    "--name",
                    n,
                    "--description",
                    f"desc {n}",
                    "--body",
                    "b",
                ],
            ).exit_code
            == 0
        )
    result = runner.invoke(cli, ["--dir", str(project), "memory", "list"])
    assert result.exit_code == 0
    for n in ("alpha", "beta", "gamma"):
        assert f"local/user_{n}" in result.output


def test_list_json(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "one",
            "--description",
            "d",
            "--body",
            "b",
        ],
    )
    result = runner.invoke(
        cli, ["--format", "json", "--dir", str(project), "memory", "list"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["id"] == "local/user_one"


# ------------------------------------------------------------------
# memory read
# ------------------------------------------------------------------


def test_read_existing_memory(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "target",
            "--description",
            "the description",
            "--body",
            "the body text",
        ],
    )
    result = runner.invoke(
        cli, ["--dir", str(project), "memory", "read", "local/user_target"]
    )
    assert result.exit_code == 0
    assert "the body text" in result.output
    assert "the description" in result.output


def test_read_missing_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "memory", "read", "local/user_nope"]
    )
    assert result.exit_code != 0


def test_read_json_output(project: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "add",
            "--type",
            "user",
            "--name",
            "json read",
            "--description",
            "d",
            "--body",
            "body text",
        ],
    )
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "memory",
            "read",
            "local/user_json_read",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["id"] == "local/user_json_read"
    assert payload["frontmatter"]["name"] == "json read"
    assert "body text" in payload["body"]


# ------------------------------------------------------------------
# memory update
# ------------------------------------------------------------------


def _add(project: Path, **overrides: str) -> None:
    runner = CliRunner()
    args = [
        "--dir",
        str(project),
        "memory",
        "add",
        "--type",
        overrides.pop("type", "user"),
        "--name",
        overrides.pop("name", "thing"),
        "--description",
        overrides.pop("description", "desc"),
        "--body",
        overrides.pop("body", "body"),
    ]
    for k, v in overrides.items():
        args.extend([f"--{k.replace('_', '-')}", v])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output


def test_update_description(project: Path) -> None:
    _add(project, name="target", description="old")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_target",
            "--description",
            "new description",
        ],
    )
    assert result.exit_code == 0, result.output
    file_path = project / ".memory" / "local" / "user_target.md"
    assert "new description" in file_path.read_text(encoding="utf-8")


def test_update_body(project: Path) -> None:
    _add(project, name="target", body="old body")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_target",
            "--body",
            "replacement body",
        ],
    )
    assert result.exit_code == 0, result.output
    content = (project / ".memory" / "local" / "user_target.md").read_text(
        encoding="utf-8"
    )
    assert "replacement body" in content
    assert "old body" not in content


def test_update_lifecycle_flips_graph_db(project: Path) -> None:
    _add(project, name="target")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_target",
            "--lifecycle",
            "stable",
        ],
    )
    assert result.exit_code == 0, result.output
    with sqlite3.connect(graph_db_path(project)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lifecycle_state FROM assets WHERE id = ?",
            ("local/user_target",),
        ).fetchone()
    assert row["lifecycle_state"] == "stable"


def test_update_tags_replaces(project: Path) -> None:
    _add(project, name="target")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_target",
            "--tags",
            "alpha",
            "--tags",
            "beta",
        ],
    )
    assert result.exit_code == 0, result.output
    content = (project / ".memory" / "local" / "user_target.md").read_text(
        encoding="utf-8"
    )
    assert "alpha" in content
    assert "beta" in content


def test_update_sets_updated_date(project: Path) -> None:
    _add(project, name="target")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_target",
            "--description",
            "touched",
        ],
    )
    assert result.exit_code == 0, result.output
    content = (project / ".memory" / "local" / "user_target.md").read_text(
        encoding="utf-8"
    )
    assert "updated:" in content


def test_update_missing_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "update",
            "local/user_nope",
            "--description",
            "x",
        ],
    )
    assert result.exit_code != 0


# ------------------------------------------------------------------
# memory archive
# ------------------------------------------------------------------


def test_archive_moves_file_to_user_archive(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _add(project, name="target")
    file_path = project / ".memory" / "local" / "user_target.md"
    assert file_path.exists()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "memory", "archive", "local/user_target"],
    )
    assert result.exit_code == 0, result.output
    assert not file_path.exists()

    # Look for the archived file under ~/.engram/archive/
    archive_root = tmp_path / ".engram" / "archive"
    moved = list(archive_root.rglob("user_target.md"))
    assert len(moved) == 1


def test_archive_flips_lifecycle(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _add(project, name="target")
    runner = CliRunner()
    runner.invoke(
        cli,
        ["--dir", str(project), "memory", "archive", "local/user_target"],
    )
    with sqlite3.connect(graph_db_path(project)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lifecycle_state FROM assets WHERE id = ?",
            ("local/user_target",),
        ).fetchone()
    assert row["lifecycle_state"] == "archived"


def test_archive_missing_errors(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--dir", str(project), "memory", "archive", "local/user_nope"],
    )
    assert result.exit_code != 0


# ------------------------------------------------------------------
# memory search — BM25
# ------------------------------------------------------------------


def test_search_finds_relevant_memory(project: Path) -> None:
    _add(
        project,
        name="kernel",
        description="kernel fluency hook",
        body="the user reads Linux kernel source",
    )
    _add(
        project,
        name="frontend",
        description="frontend preferences",
        body="the user prefers React over Vue",
    )
    _add(
        project,
        name="python",
        description="Python style guide",
        body="prefer dataclasses over TypedDict",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "memory", "search", "kernel"]
    )
    assert result.exit_code == 0, result.output
    # The top result should be the kernel one
    first_line = result.output.strip().split("\n")[0]
    assert "kernel" in first_line


def test_search_respects_limit(project: Path) -> None:
    for i in range(5):
        _add(project, name=f"topic {i}", description=f"desc {i}", body=f"keyword_{i}")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--dir",
            str(project),
            "memory",
            "search",
            "keyword",
            "--limit",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.strip().split("\n") if ln]
    assert len(lines) <= 2


def test_search_json_output(project: Path) -> None:
    _add(project, name="kernel", body="Linux kernel mm subsystem")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--format", "json", "--dir", str(project), "memory", "search", "kernel"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    assert isinstance(payload, list)
    assert payload[0]["id"] == "local/user_kernel"
    assert "score" in payload[0]


def test_search_empty_project(project: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--dir", str(project), "memory", "search", "anything"]
    )
    assert result.exit_code == 0


def test_search_no_matches(project: Path) -> None:
    _add(project, name="kernel", body="Linux kernel")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "--dir",
            str(project),
            "memory",
            "search",
            "zzzxxxnever",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload == []
