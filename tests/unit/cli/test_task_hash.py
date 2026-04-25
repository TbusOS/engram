"""T-173 tests for ``engram.usage.task_hash`` — auto-derive task_hash so
CLI / MCP callers do not have to supply one.

Resolution order (highest priority first):

1. explicit ``task_hash=`` argument
2. ``ENGRAM_TASK_HASH`` env var (set by hooks / wrappers)
3. git HEAD SHA + current branch (when cwd is in a git repo)
4. time-window bucket (15-minute floor, deterministic across processes)

The hash is opaque — callers MUST NOT parse it. The only requirement is
that two events from "the same task" share the same hash.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from engram.usage.task_hash import derive_task_hash


@pytest.fixture
def fresh_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip ENGRAM_TASK_HASH so default resolution kicks in."""
    monkeypatch.delenv("ENGRAM_TASK_HASH", raising=False)
    yield


@pytest.fixture
def git_repo(tmp_path: Path) -> Iterator[Path]:
    """A working git repo with one initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=repo,
        check=True,
    )
    yield repo


class TestExplicitOverride:
    def test_explicit_arg_wins(self, fresh_env: None, tmp_path: Path) -> None:
        out = derive_task_hash(cwd=tmp_path, explicit="my-task-id")
        assert out == "my-task-id"


class TestEnvVar:
    def test_env_var_used_when_no_explicit(
        self, fresh_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENGRAM_TASK_HASH", "from-env")
        out = derive_task_hash(cwd=tmp_path)
        assert out == "from-env"

    def test_explicit_overrides_env(
        self, fresh_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENGRAM_TASK_HASH", "from-env")
        out = derive_task_hash(cwd=tmp_path, explicit="explicit-wins")
        assert out == "explicit-wins"


class TestGitDerived:
    def test_git_repo_yields_sha_branch_hash(
        self, fresh_env: None, git_repo: Path
    ) -> None:
        out = derive_task_hash(cwd=git_repo)
        # Hex digest, opaque — just assert it's a non-empty string with no
        # newline / whitespace and stable across calls.
        assert isinstance(out, str)
        assert out
        assert "\n" not in out and " " not in out
        out2 = derive_task_hash(cwd=git_repo)
        assert out == out2

    def test_branch_change_changes_hash(
        self, fresh_env: None, git_repo: Path
    ) -> None:
        out_main = derive_task_hash(cwd=git_repo)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feature/x"], cwd=git_repo, check=True
        )
        out_feat = derive_task_hash(cwd=git_repo)
        assert out_main != out_feat


class TestTimeWindowFallback:
    def test_no_git_falls_back_to_time_bucket(
        self, fresh_env: None, tmp_path: Path
    ) -> None:
        # tmp_path is not inside a git repo
        out = derive_task_hash(cwd=tmp_path)
        assert isinstance(out, str)
        assert out
        # Two calls within the same 15-minute window MUST yield same hash
        out2 = derive_task_hash(cwd=tmp_path)
        assert out == out2

    def test_fallback_hash_format(self, fresh_env: None, tmp_path: Path) -> None:
        out = derive_task_hash(cwd=tmp_path)
        # Hex-ish, no slashes / paths leaking in
        assert re.fullmatch(r"[a-f0-9]{8,}", out) or out.startswith("tw-")
