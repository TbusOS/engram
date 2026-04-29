"""T-211 tests for wisdom curves C7 (continuation hit) + C8 (distillation yield)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engram.observer.session import (
    SessionConfidence,
    SessionFrontmatter,
    render_session_file,
    session_path,
)
from engram.wisdom import compute_wisdom_report


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated user_root + project root for wisdom report runs."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "proj"
    (project / ".memory" / "sessions").mkdir(parents=True)
    return project


def _write_session(
    project: Path,
    *,
    sid: str,
    ended: datetime,
    exposure_count: int = 0,
    distilled_into: tuple[str, ...] = (),
) -> Path:
    fm = SessionFrontmatter(
        type="session",
        session_id=sid,
        client="claude-code",
        started_at=ended - timedelta(hours=1),
        ended_at=ended,
        confidence=SessionConfidence(exposure_count=exposure_count),
        distilled_into=distilled_into,
    )
    p = session_path(sid, started_at=fm.started_at, memory_dir=project / ".memory")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, "body\n"))
    return p


# ----------------------------------------------------------------------
# Curve presence
# ----------------------------------------------------------------------


def test_report_includes_c7_c8(store: Path) -> None:
    report = compute_wisdom_report(store)
    ids = [c.id for c in report.curves]
    assert "C7" in ids
    assert "C8" in ids


def test_c7_empty_when_no_sessions(store: Path) -> None:
    report = compute_wisdom_report(store)
    c7 = next(c for c in report.curves if c.id == "C7")
    assert c7.insufficient is True


def test_c8_empty_when_no_sessions(store: Path) -> None:
    report = compute_wisdom_report(store)
    c8 = next(c for c in report.curves if c.id == "C8")
    assert c8.insufficient is True


# ----------------------------------------------------------------------
# C7 — continuation hit rate
# ----------------------------------------------------------------------


def test_c7_hit_when_exposure_positive(store: Path) -> None:
    today_dt = datetime.now(tz=timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    _write_session(store, sid="hit", ended=today_dt, exposure_count=3)
    _write_session(store, sid="miss", ended=today_dt, exposure_count=0)
    report = compute_wisdom_report(store)
    c7 = next(c for c in report.curves if c.id == "C7")
    assert c7.insufficient is False
    # 1 of 2 sessions had exposure > 0 → ratio = 0.5 today
    last = c7.samples[-1].value
    assert last == 0.5


def test_c7_full_hit(store: Path) -> None:
    today_dt = datetime.now(tz=timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    _write_session(store, sid="a", ended=today_dt, exposure_count=1)
    _write_session(store, sid="b", ended=today_dt, exposure_count=2)
    report = compute_wisdom_report(store)
    c7 = next(c for c in report.curves if c.id == "C7")
    assert c7.samples[-1].value == 1.0


# ----------------------------------------------------------------------
# C8 — distillation yield
# ----------------------------------------------------------------------


def test_c8_yield_when_distilled_into_non_empty(store: Path) -> None:
    today_dt = datetime.now(tz=timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    _write_session(
        store, sid="promoted", ended=today_dt, distilled_into=("auth-jwt",)
    )
    _write_session(store, sid="not-promoted", ended=today_dt)
    report = compute_wisdom_report(store)
    c8 = next(c for c in report.curves if c.id == "C8")
    assert c8.insufficient is False
    assert c8.samples[-1].value == 0.5


def test_c8_zero_when_nothing_promoted(store: Path) -> None:
    today_dt = datetime.now(tz=timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    _write_session(store, sid="a", ended=today_dt)
    _write_session(store, sid="b", ended=today_dt)
    report = compute_wisdom_report(store)
    c8 = next(c for c in report.curves if c.id == "C8")
    assert c8.samples[-1].value == 0.0
