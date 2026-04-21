"""T-11 tests for engram.core.paths — project root detection + ENGRAM_DIR override."""

from __future__ import annotations

from pathlib import Path

import pytest

from engram.core.paths import (
    ENV_VAR,
    MEMORY_MARKER,
    ProjectNotFoundError,
    engram_dir,
    find_project_root,
    memory_dir,
    user_root,
)


def test_memory_marker_is_dot_memory() -> None:
    assert MEMORY_MARKER == ".memory"
    assert ENV_VAR == "ENGRAM_DIR"


def test_find_project_root_from_same_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".memory").mkdir()
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert find_project_root(tmp_path) == tmp_path.resolve()


def test_find_project_root_walks_up_from_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".memory").mkdir()
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert find_project_root(nested) == tmp_path.resolve()


def test_find_project_root_defaults_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".memory").mkdir()
    nested = tmp_path / "sub"
    nested.mkdir()
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(nested)
    assert find_project_root() == tmp_path.resolve()


def test_find_project_root_raises_when_no_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(ProjectNotFoundError) as exc:
        find_project_root(tmp_path)
    assert ".memory" in str(exc.value)
    assert "ENGRAM_DIR" in str(exc.value)


def test_find_project_root_raises_is_filenotfounderror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ProjectNotFoundError is-a FileNotFoundError so callers can use either."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(FileNotFoundError):
        find_project_root(tmp_path)


def test_env_var_override_wins_even_without_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "chosen"
    override.mkdir()
    monkeypatch.setenv(ENV_VAR, str(override))
    assert find_project_root(tmp_path) == override.resolve()


def test_env_var_override_returns_verbatim_even_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENGRAM_DIR is trusted: `engram init` will create the directory, so we don't pre-validate."""
    override = tmp_path / "will-be-created"
    monkeypatch.setenv(ENV_VAR, str(override))
    assert find_project_root(tmp_path) == override.resolve()


def test_env_var_override_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "~/some-engram-project")
    result = find_project_root()
    assert "~" not in str(result)
    assert result.is_absolute()
    assert result.name == "some-engram-project"


def test_user_root_is_home_dot_engram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_root() == tmp_path / ".engram"


def test_memory_dir_returns_project_dot_memory(tmp_path: Path) -> None:
    assert memory_dir(tmp_path) == tmp_path / ".memory"


def test_engram_dir_returns_project_dot_engram(tmp_path: Path) -> None:
    assert engram_dir(tmp_path) == tmp_path / ".engram"


def test_find_project_root_accepts_string_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".memory").mkdir()
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert find_project_root(str(tmp_path)) == tmp_path.resolve()
