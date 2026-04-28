"""T-206 tests for Stage 0 session continuation in the Relevance Gate."""

from __future__ import annotations

from datetime import date

from engram.relevance.gate import (
    Asset,
    RelevanceRequest,
    SessionContinuation,
    select_session_continuations,
    run_relevance_gate,
)


def _session(
    *,
    sid: str,
    th: str,
    ended: date | None,
    body: str = "narrative body",
) -> SessionContinuation:
    return SessionContinuation(
        session_id=sid,
        task_hash=th,
        body=body,
        size_bytes=len(body),
        ended_at=ended,
    )


# ----------------------------------------------------------------------
# select_session_continuations
# ----------------------------------------------------------------------


def test_no_task_hash_returns_empty() -> None:
    sessions = [_session(sid="a", th="x", ended=date(2026, 4, 26))]
    picked, spent = select_session_continuations(
        task_hash=None, sessions=sessions, budget_tokens=8000
    )
    assert picked == ()
    assert spent == 0


def test_no_match_returns_empty() -> None:
    sessions = [_session(sid="a", th="x", ended=date(2026, 4, 26))]
    picked, _ = select_session_continuations(
        task_hash="nope", sessions=sessions, budget_tokens=8000
    )
    assert picked == ()


def test_matches_filtered_to_task_hash() -> None:
    sessions = [
        _session(sid="a", th="x", ended=date(2026, 4, 25)),
        _session(sid="b", th="x", ended=date(2026, 4, 26)),
        _session(sid="c", th="other", ended=date(2026, 4, 26)),
    ]
    picked, _ = select_session_continuations(
        task_hash="x", sessions=sessions, budget_tokens=8000
    )
    ids = [s.session_id for s in picked]
    assert "c" not in ids
    assert "a" in ids and "b" in ids


def test_capped_at_max_count() -> None:
    sessions = [
        _session(sid=str(i), th="x", ended=date(2026, 4, 20 + i)) for i in range(10)
    ]
    picked, _ = select_session_continuations(
        task_hash="x", sessions=sessions, budget_tokens=8000, max_count=3
    )
    assert len(picked) == 3
    # Most recent first.
    assert picked[0].session_id == "9"


def test_budget_fraction_caps_total_tokens() -> None:
    # body of 10000 chars * 0.25 = 2500 tokens per session.
    sessions = [
        _session(sid=str(i), th="x", ended=date(2026, 4, 20 + i), body="x" * 10000)
        for i in range(5)
    ]
    picked, spent = select_session_continuations(
        task_hash="x",
        sessions=sessions,
        budget_tokens=8000,
        budget_fraction=0.25,  # cap = 2000 tokens
    )
    # At 2500 tokens each, only 0 fit under a 2000 cap.
    assert len(picked) == 0
    assert spent == 0


def test_budget_fraction_allows_one() -> None:
    sessions = [
        _session(sid=str(i), th="x", ended=date(2026, 4, 20 + i), body="x" * 4000)
        for i in range(5)
    ]
    # 4000 chars * 0.25 = 1000 tokens; 25% of 8000 = 2000 cap → 2 fit (2000 tokens).
    picked, spent = select_session_continuations(
        task_hash="x",
        sessions=sessions,
        budget_tokens=8000,
        budget_fraction=0.25,
    )
    assert len(picked) == 2
    assert spent == 2000


def test_unended_sessions_sort_after_ended() -> None:
    sessions = [
        _session(sid="ended", th="x", ended=date(2026, 4, 25)),
        _session(sid="unended", th="x", ended=None),
    ]
    picked, _ = select_session_continuations(
        task_hash="x", sessions=sessions, budget_tokens=8000
    )
    # The ended session is preferred — picks first.
    assert picked[0].session_id == "ended"


# ----------------------------------------------------------------------
# Integration with run_relevance_gate
# ----------------------------------------------------------------------


def test_gate_returns_sessions_when_task_hash_set() -> None:
    sessions = [
        _session(sid="a", th="x", ended=date(2026, 4, 25)),
        _session(sid="b", th="x", ended=date(2026, 4, 26)),
    ]
    request = RelevanceRequest(
        query="hello",
        assets=[],
        budget_tokens=8000,
        task_hash="x",
        sessions=sessions,
    )
    result = run_relevance_gate(request)
    assert len(result.sessions) == 2
    assert result.sessions_tokens > 0


def test_gate_no_task_hash_keeps_existing_behavior() -> None:
    """Stage 0 with no task_hash must not alter the existing pipeline."""
    asset = Asset(
        id="m1",
        scope="project",
        enforcement="default",
        subscribed_at=None,
        body="some text about hello world",
        updated=date(2026, 4, 26),
        size_bytes=100,
    )
    request = RelevanceRequest(
        query="hello", assets=[asset], budget_tokens=8000, now=date(2026, 4, 26)
    )
    result = run_relevance_gate(request)
    assert result.sessions == ()
    assert result.sessions_tokens == 0


def test_gate_sessions_do_not_affect_asset_budget() -> None:
    """Stage 0 budget cap is independent of the regular asset budget."""
    sessions = [_session(sid="s1", th="x", ended=date(2026, 4, 26), body="x" * 1000)]
    asset = Asset(
        id="m1",
        scope="project",
        enforcement="default",
        subscribed_at=None,
        body="some text about hello world",
        updated=date(2026, 4, 26),
        size_bytes=100,
    )
    request = RelevanceRequest(
        query="hello",
        assets=[asset],
        budget_tokens=8000,
        now=date(2026, 4, 26),
        task_hash="x",
        sessions=sessions,
    )
    result = run_relevance_gate(request)
    # Asset budget consumption is unaffected by the session injection.
    assert len(result.included) >= 1
    # Session was selected.
    assert len(result.sessions) == 1
