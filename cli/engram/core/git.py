"""Shared git subprocess helpers.

Used by both pool propagation (``engram pool pull``) and team / org scope
synchronisation (``engram team sync``, ``engram org publish``, ...). Stays at
the subprocess layer on purpose — we do **not** pull GitPython in, because
engram's CLI should have zero mandatory dependencies beyond click, PyYAML,
and tomli/tomli-w.

All helpers raise :class:`click.ClickException` on failure so the CLI layer
can surface the git stderr message directly to the operator.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import click

__all__ = [
    "clone",
    "commit_all",
    "diff_name_status",
    "head_sha",
    "pull_ff",
    "push",
    "run_git",
    "status_porcelain",
]


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <cwd> <args...>`` and capture its output. Never raises."""
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _require_zero(result: subprocess.CompletedProcess[str], action: str, cwd: Path) -> None:
    if result.returncode != 0:
        raise click.ClickException(
            f"{action} failed in {cwd}: "
            f"{result.stderr.strip() or result.stdout.strip() or 'unknown git error'}"
        )


def head_sha(cwd: Path) -> str:
    """Return the current ``HEAD`` commit SHA of ``cwd``."""
    result = run_git(cwd, "rev-parse", "HEAD")
    _require_zero(result, "rev-parse HEAD", cwd)
    return result.stdout.strip()


def diff_name_status(cwd: Path, before: str, after: str) -> dict[str, int]:
    """Return ``{added, modified, removed}`` counts between two SHAs."""
    result = run_git(cwd, "diff", "--name-status", f"{before}..{after}")
    counts = {"added": 0, "modified": 0, "removed": 0}
    if result.returncode != 0:
        return counts
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        status = line.split("\t", 1)[0][:1]
        if status == "A":
            counts["added"] += 1
        elif status == "M":
            counts["modified"] += 1
        elif status == "D":
            counts["removed"] += 1
    return counts


def pull_ff(cwd: Path) -> dict[str, Any]:
    """``git pull --ff-only`` inside ``cwd`` with before/after SHA diff stats.

    Returns ``{name, before, after, changed, added, modified, removed}``.
    Fast-forward only — a diverged repo errors out so the operator resolves it.
    """
    before = head_sha(cwd)
    result = run_git(cwd, "pull", "--ff-only")
    _require_zero(result, "git pull", cwd)
    after = head_sha(cwd)
    entry: dict[str, Any] = {
        "name": cwd.name,
        "before": before,
        "after": after,
        "changed": before != after,
    }
    if before != after:
        entry.update(diff_name_status(cwd, before, after))
    else:
        entry.update({"added": 0, "modified": 0, "removed": 0})
    return entry


def clone(dest: Path, url: str) -> None:
    """``git clone <url> <dest>``. Creates parent dirs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", url, str(dest)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(
            f"git clone {url} → {dest} failed: {result.stderr.strip() or 'unknown git error'}"
        )


def status_porcelain(cwd: Path) -> list[str]:
    """Return ``git status --porcelain`` lines (empty list if clean)."""
    result = run_git(cwd, "status", "--porcelain")
    _require_zero(result, "git status", cwd)
    return [line for line in result.stdout.splitlines() if line]


def commit_all(cwd: Path, message: str) -> str | None:
    """``git add -A`` + ``git commit -m <message>``.

    Returns the new HEAD SHA, or ``None`` when there was nothing to commit
    (clean working tree). Raises on other errors.
    """
    before = head_sha(cwd)
    add = run_git(cwd, "add", "-A")
    _require_zero(add, "git add", cwd)
    commit = run_git(cwd, "commit", "-m", message)
    if commit.returncode != 0:
        # `git commit` with nothing to commit exits non-zero with the well-known
        # "nothing to commit" message. Treat that as a no-op, not an error.
        combined = (commit.stdout + commit.stderr).lower()
        if "nothing to commit" in combined or "no changes added" in combined:
            return None
        raise click.ClickException(
            f"git commit failed in {cwd}: {commit.stderr.strip() or commit.stdout.strip()}"
        )
    after = head_sha(cwd)
    return None if after == before else after


def push(cwd: Path) -> None:
    """``git push`` from ``cwd``. Raises on failure."""
    result = run_git(cwd, "push")
    _require_zero(result, "git push", cwd)
