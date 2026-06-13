"""Tests for the Knowledge Base asset class (SPEC §6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.kb.compiler import check_staleness, compile_article
from engram.kb.format import (
    KbFormatError,
    parse_compile_state,
    parse_readme,
    render_readme,
)
from engram.kb.paths import kb_dir, validate_topic_name


# ----------------------------------------------------------------------
# paths + format
# ----------------------------------------------------------------------


def test_validate_topic_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        validate_topic_name("../escape")


def test_readme_round_trip_preserves_unknown(tmp_path: Path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text(
        "---\nname: A\ndescription: d\ntype: kb\nscope: project\n"
        "lifecycle_state: active\nchapters:\n  - 01-x.md\ncustom: keep\n---\nbody\n",
        encoding="utf-8",
    )
    fm, body = parse_readme(doc)
    assert fm.chapters == ("01-x.md",)
    assert fm.extra == {"custom": "keep"}
    assert "custom: keep" in render_readme(fm, body)


def test_readme_rejects_wrong_type(tmp_path: Path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text(
        "---\nname: A\ndescription: d\ntype: memory\nscope: project\nlifecycle_state: active\n---\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(KbFormatError):
        parse_readme(doc)


# ----------------------------------------------------------------------
# compiler — rule-based digest + staleness
# ----------------------------------------------------------------------


def _make_article(root: Path, topic: str = "demo") -> Path:
    tdir = kb_dir(root, topic)
    tdir.mkdir(parents=True)
    (tdir / "README.md").write_text(
        "---\nname: Demo\ndescription: d\ntype: kb\nscope: project\n"
        "lifecycle_state: active\nchapters:\n  - 01-overview.md\n  - 02-arch.md\n---\nabstract\n",
        encoding="utf-8",
    )
    (tdir / "01-overview.md").write_text(
        "# Overview\n\nThis chapter explains the overview.\n\n## Details\n\nmore\n",
        encoding="utf-8",
    )
    (tdir / "02-arch.md").write_text(
        "# Architecture\n\nThe architecture has three layers.\n", encoding="utf-8"
    )
    return tdir


def test_compile_creates_digest_and_state(tmp_path: Path) -> None:
    tdir = _make_article(tmp_path)
    result = compile_article(tdir)
    assert result.sections == 2
    digest = (tdir / "_compiled.md").read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in digest
    # Every chapter gets a heading (SPEC §6.5).
    assert "## Overview" in digest
    assert "## Architecture" in digest
    assert "[Read the full chapter](01-overview.md)" in digest
    state = parse_compile_state(tdir / "_compile_state.toml")
    assert state.model == "local/none"
    assert "01-overview.md" in state.files


def test_compile_is_fresh_immediately_after(tmp_path: Path) -> None:
    tdir = _make_article(tmp_path)
    compile_article(tdir)
    # README is hashed AFTER its frontmatter is updated, so no false stale.
    assert check_staleness(tdir).is_stale is False


def test_staleness_detects_chapter_change(tmp_path: Path) -> None:
    tdir = _make_article(tmp_path)
    compile_article(tdir)
    (tdir / "01-overview.md").write_text("# Overview\n\nCHANGED content.\n", encoding="utf-8")
    report = check_staleness(tdir)
    assert report.is_stale is True
    assert "01-overview.md" in report.changed_files
    # The stale flag is persisted; the digest itself is not deleted.
    assert (tdir / "_compiled.md").is_file()
    assert parse_compile_state(tdir / "_compile_state.toml").is_stale is True


def test_recompile_clears_stale(tmp_path: Path) -> None:
    tdir = _make_article(tmp_path)
    compile_article(tdir)
    (tdir / "02-arch.md").write_text("# Architecture\n\nrewritten\n", encoding="utf-8")
    assert check_staleness(tdir).is_stale is True
    compile_article(tdir)
    assert check_staleness(tdir).is_stale is False


def test_compile_empty_chapters_raises(tmp_path: Path) -> None:
    tdir = kb_dir(tmp_path, "empty")
    tdir.mkdir(parents=True)
    (tdir / "README.md").write_text(
        "---\nname: E\ndescription: d\ntype: kb\nscope: project\nlifecycle_state: draft\n---\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(KbFormatError):
        compile_article(tdir)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    proj = tmp_path / "proj"
    assert CliRunner().invoke(cli, ["--dir", str(proj), "init"]).exit_code == 0
    return proj


def _run(project: Path, *args: str):
    return CliRunner().invoke(cli, ["--dir", str(project), *args])


def test_cli_new_article_compile_list_read(project: Path) -> None:
    assert _run(project, "kb", "new-article", "obs", "--name", "Observability").exit_code == 0
    assert (project / ".memory" / "kb" / "obs" / "README.md").is_file()
    assert (project / ".memory" / "kb" / "obs" / "01-overview.md").is_file()

    comp = _run(project, "kb", "compile", "obs")
    assert comp.exit_code == 0
    assert (project / ".memory" / "kb" / "obs" / "_compiled.md").is_file()

    listed = _run(project, "--format", "json", "kb", "list")
    rows = json.loads(listed.output)
    assert any(r["topic"] == "obs" and r["stale"] is False for r in rows)

    read = _run(project, "--format", "json", "kb", "read", "obs")
    assert json.loads(read.output)["type"] == "kb"


def test_cli_compile_check_exit_code(project: Path) -> None:
    _run(project, "kb", "new-article", "obs")
    _run(project, "kb", "compile", "obs")
    assert _run(project, "kb", "compile", "obs", "--check").exit_code == 0
    # Mutate a chapter -> check exits 2.
    (project / ".memory" / "kb" / "obs" / "01-overview.md").write_text("# X\n\nchanged\n")
    res = _run(project, "kb", "compile", "obs", "--check")
    assert res.exit_code == 2
    assert "STALE" in res.output


def test_cli_new_article_rejects_duplicate(project: Path) -> None:
    assert _run(project, "kb", "new-article", "dup").exit_code == 0
    dup = _run(project, "kb", "new-article", "dup")
    assert dup.exit_code != 0
    assert "already exists" in dup.output


def test_cli_read_unknown_clean_error(project: Path) -> None:
    res = _run(project, "kb", "read", "ghost")
    assert res.exit_code != 0
    assert "no KB article" in res.output


def test_cli_honors_dir_no_project_clean_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENGRAM_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli, ["kb", "list"])
    assert res.exit_code != 0
    assert "engram init" in res.output


# ----------------------------------------------------------------------
# Review fixes (2026-06-14): chapter path traversal, scope rejection,
# bounded state read
# ----------------------------------------------------------------------


def test_compile_rejects_chapter_path_traversal(tmp_path: Path) -> None:
    """A chapters: entry that escapes the article dir is refused, not read."""
    tdir = kb_dir(tmp_path, "evil")
    tdir.mkdir(parents=True)
    (tdir / "README.md").write_text(
        "---\nname: E\ndescription: d\ntype: kb\nscope: project\n"
        "lifecycle_state: draft\nchapters:\n  - ../../../etc/passwd\n---\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(KbFormatError, match="safe in-article"):
        compile_article(tdir)


def test_compile_rejects_absolute_chapter(tmp_path: Path) -> None:
    tdir = kb_dir(tmp_path, "evil2")
    tdir.mkdir(parents=True)
    (tdir / "README.md").write_text(
        "---\nname: E\ndescription: d\ntype: kb\nscope: project\n"
        "lifecycle_state: draft\nchapters:\n  - /etc/hosts\n---\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(KbFormatError):
        compile_article(tdir)


def test_kb_root_rejects_unresolvable_scope(tmp_path: Path) -> None:
    from engram.kb.paths import kb_root

    with pytest.raises(ValueError, match="scope name"):
        kb_root(tmp_path, scope="team")


def test_cli_new_article_rejects_team_scope(project: Path) -> None:
    res = _run(project, "kb", "new-article", "x", "--scope", "team")
    assert res.exit_code != 0  # not in the restricted Choice
