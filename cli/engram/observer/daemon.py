"""Observer daemon — single-instance lockfile + processing loop.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §5.

This module provides three responsibilities:

1. :class:`SingletonLock` — fcntl.flock-based pid file under
   ``~/.engram/observer.pid`` so only one daemon instance per user runs.
   Stale (dead-PID) locks are stolen, not waited on; reclaimed queues
   are continued, not orphaned.

2. :func:`scan_pending_sessions` — find sessions with new events the
   daemon hasn't processed yet, plus sessions that have gone idle past
   the configured threshold.

3. :class:`ObserverDaemon` — the main loop that ties Tier 0 (T-202),
   Tier 1 (T-204), Tier 2 (T-208), Tier 3 (T-210) together as they
   land. The current skeleton wires Tier 0 only and leaves stub hooks
   for the higher tiers.

The daemon is intentionally POSIX-only and uses a polling loop rather
than inotify/FSEvents — those are reserved for the web UI watcher
(T-112) which has different invariants. A 2 s polling interval is
imperceptible and avoids platform-specific file-watch quirks.
"""

from __future__ import annotations

import fcntl
import os
import signal
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

from engram.core.paths import user_root
from engram.observer.paths import OBSERVER_PID_FILE, observe_queue_dir

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_SESSION_IDLE_THRESHOLD_SECONDS",
    "DaemonError",
    "ObserverDaemon",
    "PendingSession",
    "SingletonLock",
    "SingletonLockError",
    "scan_pending_sessions",
]


DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_SESSION_IDLE_THRESHOLD_SECONDS = 300.0  # 5 minutes


class DaemonError(RuntimeError):
    """Base class for daemon failures."""


class SingletonLockError(DaemonError):
    """Raised when the singleton lock cannot be acquired."""


# ----------------------------------------------------------------------
# Singleton lockfile
# ----------------------------------------------------------------------


class SingletonLock:
    """Process-local context manager around ``observer.pid``.

    Use as::

        with SingletonLock(base=...) as lock:
            # safe to run; another daemon will see us alive
            ...

    The lock acquires an exclusive ``fcntl.flock`` on the pid file. If
    the lock is held by a process that is no longer running, the new
    daemon steals it (claude-mem's "worker_pid claim" pattern, ported
    to a single shared lockfile rather than per-row claims).
    """

    def __init__(self, *, base: Path | None = None) -> None:
        self._base = base if base is not None else user_root()
        self._path = self._base / OBSERVER_PID_FILE
        self._fd: int | None = None
        self._stolen: bool = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def stolen(self) -> bool:
        """True when this lock was reclaimed from a dead PID."""
        return self._stolen

    def __enter__(self) -> SingletonLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Open r/w; create if missing.
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        # Snapshot whatever PID lived in the file before we touch flock.
        # A stale value here (file present but flock free) = previous
        # daemon died without unlinking the file; we are reclaiming.
        prior_pid = _read_pid_from_fd(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Lock currently held — see if the holder is still alive.
            existing_pid = prior_pid
            if existing_pid is not None and _process_alive(existing_pid):
                os.close(fd)
                raise SingletonLockError(
                    f"observer daemon already running as PID {existing_pid}"
                ) from None
            # Stale flock (very rare on POSIX since kernel drops flocks on
            # process death, but possible on some filesystems). Try once
            # more after the holder evaporates.
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._stolen = True
            except BlockingIOError:
                os.close(fd)
                raise SingletonLockError(
                    "observer daemon lock held but flock unavailable; "
                    "investigate ~/.engram/observer.pid"
                ) from None

        # Lock held. If a different PID was sitting in the file when we
        # opened it, treat this as a stolen / reclaimed lock so the
        # daemon can decide to recover any orphaned queue state.
        if prior_pid is not None and prior_pid != os.getpid():
            self._stolen = True

        os.lseek(fd, 0, 0)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
        # Best-effort cleanup; another daemon may already be re-creating it.
        with suppress(FileNotFoundError):
            self._path.unlink()


def _read_pid_from_fd(fd: int) -> int | None:
    try:
        os.lseek(fd, 0, 0)
        data = os.read(fd, 32).decode("ascii", errors="replace").strip()
    except OSError:
        return None
    if not data:
        return None
    try:
        return int(data.split()[0])
    except (ValueError, IndexError):
        return None


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists; we just don't have permission to signal it.
        return True
    return True


# ----------------------------------------------------------------------
# Pending-session scan
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class PendingSession:
    """A session with queued events the daemon hasn't yet processed."""

    session_id: str
    queue_path: Path
    queue_size_bytes: int
    last_modified: float

    def is_idle(self, *, now: float, threshold_seconds: float) -> bool:
        """True if the session has gone quiet long enough to flush."""
        return (now - self.last_modified) >= threshold_seconds


def scan_pending_sessions(*, base: Path | None = None) -> Iterator[PendingSession]:
    """Yield every session with a non-empty queue file.

    Iteration order: ascending by ``last_modified`` so older queues get
    processed first — operators see consistent throughput when many
    clients write at once.
    """
    qdir = observe_queue_dir(base=base)
    if not qdir.is_dir():
        return iter(())

    entries: list[PendingSession] = []
    for child in qdir.iterdir():
        if not child.is_file() or child.suffix != ".jsonl":
            continue
        try:
            stat = child.stat()
        except FileNotFoundError:
            continue
        if stat.st_size == 0:
            continue
        session_id = child.stem
        entries.append(
            PendingSession(
                session_id=session_id,
                queue_path=child,
                queue_size_bytes=stat.st_size,
                last_modified=stat.st_mtime,
            )
        )
    entries.sort(key=lambda p: p.last_modified)
    return iter(entries)


# ----------------------------------------------------------------------
# Daemon main loop
# ----------------------------------------------------------------------


@dataclass
class DaemonConfig:
    """Tunable parameters for :class:`ObserverDaemon`."""

    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    session_idle_threshold_seconds: float = DEFAULT_SESSION_IDLE_THRESHOLD_SECONDS
    max_iterations: int | None = None  # for tests; None = run forever


@dataclass
class DaemonStats:
    """Counters surfaced by ``engram observer status``."""

    iterations: int = 0
    pending_sessions_seen: int = 0
    tier0_invocations: int = 0
    tier1_invocations: int = 0
    tier0_errors: int = 0
    tier1_errors: int = 0
    last_error: str | None = None
    last_error_at: str | None = None
    started_at: float = field(default_factory=time.time)


class ObserverDaemon:
    """Foreground-runnable processing loop.

    Dependency injection:

    - ``tier0_runner`` — callable invoked for every pending session each tick.
    - ``tier1_runner`` — callable invoked when a session is idle past
      ``session_idle_threshold_seconds``.

    Both default to no-ops so the skeleton can land before T-202 / T-204
    without breaking tests; later tasks wire the real compactors here.
    """

    def __init__(
        self,
        *,
        config: DaemonConfig | None = None,
        base: Path | None = None,
        tier0_runner: Callable[[PendingSession], None] | None = None,
        tier1_runner: Callable[[PendingSession], None] | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or DaemonConfig()
        self.base = base
        self.tier0_runner = tier0_runner or (lambda _ps: None)
        self.tier1_runner = tier1_runner or (lambda _ps: None)
        self.clock = clock
        self.sleeper = sleeper
        self.stats = DaemonStats(started_at=self.clock())
        self._stop_requested = False

    def request_stop(self) -> None:
        """Signal the loop to exit at the next tick boundary."""
        self._stop_requested = True

    def _install_signal_handlers(self) -> None:
        def _on_signal(
            signum: int, _frame: object
        ) -> None:  # pragma: no cover — wired via OS signals
            self.request_stop()

        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)

    def run_forever(self, *, install_signals: bool = True) -> DaemonStats:
        """Run the processing loop until stopped or ``max_iterations`` hits.

        Returns the final stats so callers (and tests) can assert on
        them without extra plumbing.
        """
        if install_signals:
            self._install_signal_handlers()

        while not self._stop_requested:
            if (
                self.config.max_iterations is not None
                and self.stats.iterations >= self.config.max_iterations
            ):
                break
            self.tick()
            self.sleeper(self.config.poll_interval_seconds)
        return self.stats

    def tick(self) -> None:
        """Run one iteration: scan pending sessions, dispatch tiers."""
        self.stats.iterations += 1
        now = self.clock()

        for pending in scan_pending_sessions(base=self.base):
            if self._stop_requested:
                # Code reviewer C6 — honour SIGTERM mid-tick instead of
                # waiting for the whole pending-session list to drain.
                return
            self.stats.pending_sessions_seen += 1
            try:
                self.tier0_runner(pending)
                self.stats.tier0_invocations += 1
            except Exception as exc:
                # Code reviewer C1 — never silently swallow. Append a
                # diagnostic line to ``~/.engram/journal/observer.jsonl``
                # so operators can see what went wrong; counters surface
                # in ``engram observer status``.
                self.stats.tier0_errors += 1
                self._log_error("tier0", pending.session_id, exc)
                continue

            if pending.is_idle(
                now=now,
                threshold_seconds=self.config.session_idle_threshold_seconds,
            ):
                try:
                    self.tier1_runner(pending)
                    self.stats.tier1_invocations += 1
                except Exception as exc:
                    self.stats.tier1_errors += 1
                    self._log_error("tier1", pending.session_id, exc)
                    continue

    def _log_error(self, tier: str, session_id: str, exc: Exception) -> None:
        """Record a tier exception to the daemon journal + stats.

        Best-effort: a failure here MUST NOT abort the tick. The journal
        path is derived from ``base`` so tests can isolate it via the
        ``--base`` flag without touching ``~/.engram/``.
        """
        from datetime import datetime, timezone

        now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")
        message = f"{type(exc).__name__}: {exc}"
        self.stats.last_error = f"{tier}/{session_id}: {message}"
        self.stats.last_error_at = now_iso
        try:
            from engram.core.journal import append_event

            base = self.base if self.base is not None else user_root()
            path = base / "journal" / "observer.jsonl"
            append_event(
                path,
                {
                    "t": now_iso,
                    "tier": tier,
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1024],
                },
            )
        except Exception:
            # Last-ditch: never let a logging failure mask the original
            # exception. Stats already capture the latest error.
            return


@contextmanager
def daemon_singleton(*, base: Path | None = None) -> Iterator[SingletonLock]:
    """Context manager bundling :class:`SingletonLock` for daemon entrypoints."""
    lock = SingletonLock(base=base)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()
