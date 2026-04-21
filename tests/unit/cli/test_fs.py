"""T-13 tests for engram.core.fs — atomic writes, advisory locks, atomic symlinks."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from engram.core.fs import acquire_lock, atomic_symlink, write_atomic


# ------------------------------------------------------------------
# write_atomic
# ------------------------------------------------------------------


def test_write_atomic_creates_file_with_content(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    write_atomic(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_atomic_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old")
    write_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_write_atomic_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "out.txt"
    write_atomic(target, "hi")
    assert target.read_text(encoding="utf-8") == "hi"


def test_write_atomic_accepts_bytes(tmp_path: Path) -> None:
    target = tmp_path / "bin.dat"
    write_atomic(target, b"\x00\x01\x02\xff")
    assert target.read_bytes() == b"\x00\x01\x02\xff"


def test_write_atomic_unicode(tmp_path: Path) -> None:
    target = tmp_path / "unicode.md"
    write_atomic(target, "engram — 你好 🧠")
    assert target.read_text(encoding="utf-8") == "engram — 你好 🧠"


def test_write_atomic_leaves_no_tmp_files_on_success(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    write_atomic(target, "x")
    names = {p.name for p in tmp_path.iterdir()}
    assert names == {"a.txt"}


def test_write_atomic_cleans_tmp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.txt"

    def boom(*_a: Any, **_kw: Any) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("engram.core.fs.os.replace", boom)

    with pytest.raises(OSError, match="simulated"):
        write_atomic(target, "content")

    # No target file, no leftover tmp file
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_atomic_preserves_old_content_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomicity guarantee: failed write must not clobber existing content."""
    target = tmp_path / "a.txt"
    target.write_text("original")

    def boom(*_a: Any, **_kw: Any) -> None:
        raise OSError("simulated")

    monkeypatch.setattr("engram.core.fs.os.replace", boom)

    with pytest.raises(OSError):
        write_atomic(target, "new content")

    assert target.read_text(encoding="utf-8") == "original"


# ------------------------------------------------------------------
# acquire_lock
# ------------------------------------------------------------------


def test_acquire_lock_yields_and_creates_lockfile(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with acquire_lock(lock):
        assert lock.exists()


def test_acquire_lock_creates_parent_dir(tmp_path: Path) -> None:
    lock = tmp_path / "nested" / "dir" / "x.lock"
    with acquire_lock(lock):
        assert lock.exists()


def test_acquire_lock_releases_on_exit(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with acquire_lock(lock):
        pass
    # Re-acquiring should not block or error.
    with acquire_lock(lock):
        pass


def test_acquire_lock_releases_on_exception(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with pytest.raises(RuntimeError, match="boom"):
        with acquire_lock(lock):
            raise RuntimeError("boom")
    # Lock is released even after exception.
    with acquire_lock(lock):
        pass


def test_acquire_lock_serializes_concurrent_holders(tmp_path: Path) -> None:
    """Two threads contending for the same lock must not overlap their critical sections."""
    lock = tmp_path / "serialize.lock"
    order: list[tuple[str, int]] = []
    order_lock = threading.Lock()

    def worker(i: int) -> None:
        with acquire_lock(lock):
            with order_lock:
                order.append(("enter", i))
            time.sleep(0.05)
            with order_lock:
                order.append(("exit", i))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(order) == 6
    # After each "enter i" the very next event must be "exit i".
    for pos in range(0, 6, 2):
        enter = order[pos]
        exit_ = order[pos + 1]
        assert enter[0] == "enter"
        assert exit_[0] == "exit"
        assert enter[1] == exit_[1]


# ------------------------------------------------------------------
# atomic_symlink
# ------------------------------------------------------------------


def test_atomic_symlink_creates_new(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("t")
    link = tmp_path / "link"
    atomic_symlink(target, link)
    assert link.is_symlink()
    assert link.resolve() == target.resolve()


def test_atomic_symlink_replaces_existing_symlink(tmp_path: Path) -> None:
    t1 = tmp_path / "t1"
    t1.write_text("1")
    t2 = tmp_path / "t2"
    t2.write_text("2")
    link = tmp_path / "link"

    atomic_symlink(t1, link)
    atomic_symlink(t2, link)

    assert link.resolve() == t2.resolve()


def test_atomic_symlink_replaces_broken_symlink(tmp_path: Path) -> None:
    link = tmp_path / "link"
    atomic_symlink(tmp_path / "nonexistent", link)
    assert link.is_symlink()
    assert not link.exists()  # broken — target missing

    real = tmp_path / "real"
    real.write_text("hi")
    atomic_symlink(real, link)

    assert link.exists()
    assert link.resolve() == real.resolve()


def test_atomic_symlink_relative_target(tmp_path: Path) -> None:
    """Workflow rev/current -> rN/ uses a relative target."""
    rev_dir = tmp_path / "rev" / "r1"
    rev_dir.mkdir(parents=True)
    link = tmp_path / "rev" / "current"

    atomic_symlink(Path("r1"), link)

    assert link.is_symlink()
    assert os.readlink(link) == "r1"


def test_atomic_symlink_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "deep" / "nested" / "link"
    atomic_symlink(target, link)
    assert link.is_symlink()


def test_atomic_symlink_accepts_string_target(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "link"
    atomic_symlink(str(target), link)
    assert link.resolve() == target.resolve()
