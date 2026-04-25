"""Auto-derive ``task_hash`` so CLI / MCP callers do not have to supply one.

Resolution order (highest priority first):

1. ``explicit=`` argument
2. ``ENGRAM_TASK_HASH`` environment variable (set by hooks / agent wrappers)
3. git HEAD SHA + current branch + ahead-of-trunk count, when cwd is in a
   git repo. This produces a stable hash for "the work I'm doing on this
   branch right now" — distinct branches → distinct task_hashes.
4. 15-minute time-window bucket, opaque ``tw-<hex>`` value. Multiple events
   within the window correlate as one "task" without any context.

The hash is opaque on purpose — callers MUST NOT parse it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path


__all__ = ["derive_task_hash"]


# 15-minute window — 4 buckets/hour. Tunable but should change rarely;
# a smaller window risks splitting one task across multiple hashes.
_TIME_WINDOW_SECONDS = 15 * 60


def derive_task_hash(
    *, cwd: Path | None = None, explicit: str | None = None
) -> str:
    if explicit:
        return explicit

    env_value = os.environ.get("ENGRAM_TASK_HASH")
    if env_value:
        return env_value

    target = cwd or Path.cwd()
    git_hash = _try_git_hash(target)
    if git_hash:
        return git_hash

    return _time_window_bucket()


def _try_git_hash(cwd: Path) -> str | None:
    """Compose a hash from HEAD SHA + branch when ``cwd`` sits in a git repo."""
    sha = _run_git(cwd, ["rev-parse", "HEAD"])
    if not sha:
        return None
    branch = _run_git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"]) or "detached"
    payload = f"{sha}|{branch}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return digest


def _run_git(cwd: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _time_window_bucket() -> str:
    bucket = int(time.time()) // _TIME_WINDOW_SECONDS
    digest = hashlib.sha256(str(bucket).encode("ascii")).hexdigest()[:12]
    return f"tw-{digest}"
