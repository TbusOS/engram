"""Filesystem primitives — atomic writes, advisory locks, atomic symlink swaps.

These are the lowest-level helpers in Layer 1 (Data). Every mutation to
``.memory/`` or ``~/.engram/`` state goes through one of them, so that:

- a reader never observes a partial write (`write_atomic` stages to a sibling
  tmp file and renames, which is atomic on POSIX filesystems for same-directory
  renames);
- concurrent writers within the same store cooperate via an advisory lock
  (`acquire_lock` wraps ``fcntl.flock`` in a context manager);
- the ``rev/current -> rN/`` symlink and similar pointers flip without a
  missing-link window (`atomic_symlink` stages the new symlink under a unique
  tmp name in the same directory, then renames over the existing pointer).

POSIX-only (macOS + Linux). Windows is not supported in v0.2 per DESIGN §9.5
packaging targets.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

__all__ = [
    "acquire_lock",
    "atomic_symlink",
    "write_atomic",
]


def write_atomic(path: Path, content: str | bytes, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically via tmp + rename.

    Creates parent directories if missing. The tmp file lives in ``path.parent``
    so the final ``os.replace`` stays on the same filesystem (cross-device
    rename is not atomic). On any failure, the tmp file is removed and the
    original ``path`` (if it existed) is left untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data: bytes = content.encode(encoding) if isinstance(content, str) else content

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


@contextmanager
def acquire_lock(path: Path, *, exclusive: bool = True) -> Iterator[None]:
    """Advisory file lock held for the duration of the ``with`` block.

    Creates the lock file (and parent directories) if missing. The lock file is
    not deleted on release so repeated acquires share the same inode. Callers
    should name a dedicated lock file (``<store>/.lock``), not a data file —
    flock is advisory and independent of file content.

    ``exclusive=True`` (default) uses ``LOCK_EX``; ``False`` uses ``LOCK_SH``
    for read-only critical sections.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, mode)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def atomic_symlink(target: str | Path, link: Path) -> None:
    """Create (or replace) a symlink at ``link`` pointing to ``target``, atomically.

    Uses a sibling tmp symlink + ``os.replace`` so observers never see a moment
    where ``link`` is missing. Works whether or not ``link`` exists, whether or
    not ``target`` exists (broken symlinks are fine), and for both absolute and
    relative targets — the target string is passed through verbatim.
    """
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.parent / f".{link.name}.symlink.{uuid.uuid4().hex[:8]}"
    with suppress(FileNotFoundError):
        tmp.unlink()
    os.symlink(os.fspath(target), tmp)
    try:
        os.replace(tmp, link)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
