"""T-208 tests for engram.observer.tier2 — semantic distiller."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from engram.observer.providers import ProviderError
from engram.observer.session import (
    SessionFrontmatter,
    render_session_file,
    session_path,
)
from engram.observer.tier2 import (
    DEFAULT_TIER2_MIN_SESSIONS,
    DistillResult,
    DistilledCandidate,
    SessionForDistill,
    build_distill_prompt,
    distill_sessions,
    distilled_dir,
    load_session_for_distill,
    render_proposed_file,
    run_tier2,
    select_sessions_for_distill,
    slugify_topic,
)


def _sfd(
    sid: str,
    *,
    files: tuple[str, ...] = (),
    body: str = "## Investigated\n- did stuff\n",
    outcome: str = "completed",
    th: str | None = None,
) -> SessionForDistill:
    return SessionForDistill(
        session_id=sid,
        task_hash=th,
        files_touched=files,
        outcome=outcome,
        body=body,
    )


# ----------------------------------------------------------------------
# slugify
# ----------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert slugify_topic("Auth Middleware Uses JWT") == "auth-middleware-uses-jwt"


def test_slugify_strips_edges() -> None:
    assert slugify_topic("---hello---") == "hello"


def test_slugify_empty_falls_back() -> None:
    assert slugify_topic("!!!") == "untitled"


def test_slugify_truncates_at_96() -> None:
    long = "a" * 200
    assert len(slugify_topic(long)) == 96


# ----------------------------------------------------------------------
# select_sessions_for_distill
# ----------------------------------------------------------------------


def test_below_threshold_yields_empty() -> None:
    sessions = [_sfd(f"s{i}") for i in range(3)]
    assert select_sessions_for_distill(sessions, min_sessions=5) == ()


def test_at_threshold_yields_all() -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    out = select_sessions_for_distill(sessions, min_sessions=5)
    assert len(out) == 5


def test_default_threshold_is_five() -> None:
    assert DEFAULT_TIER2_MIN_SESSIONS == 5


# ----------------------------------------------------------------------
# build_distill_prompt
# ----------------------------------------------------------------------


def test_prompt_lists_each_session() -> None:
    sessions = [_sfd("a"), _sfd("b")]
    p = build_distill_prompt(sessions)
    assert "## Sessions" in p
    assert "### a" in p
    assert "### b" in p


def test_prompt_includes_files_and_task_hash() -> None:
    sessions = [_sfd("a", files=("src/foo.ts",), th="task1")]
    p = build_distill_prompt(sessions)
    assert "`src/foo.ts`" in p
    assert "task1" in p


def test_prompt_warns_against_buzzwords() -> None:
    p = build_distill_prompt([])
    assert "buzzword" in p.lower() or "synergy" in p


# ----------------------------------------------------------------------
# Candidate parsing (private, exercised through distill_sessions)
# ----------------------------------------------------------------------


def test_distill_parses_json_array(tmp_path: Path) -> None:
    sessions = [
        _sfd(f"s{i}", files=("src/foo.ts",)) for i in range(5)
    ]

    response = json.dumps(
        [
            {
                "name": "Auth Middleware Uses JWT",
                "description": "JWT signed with HS256.",
                "body": "- token from header\n- HS256 signing\n",
                "source_sessions": ["s0", "s1"],
            }
        ]
    )
    result = distill_sessions(
        sessions,
        memory_dir=tmp_path,
        provider=lambda _p: response,
    )
    assert isinstance(result, DistillResult)
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.name == "auth-middleware-uses-jwt"
    assert c.source_sessions == ("s0", "s1")
    assert result.used_mechanical_fallback is False


def test_distill_strips_markdown_fences(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    fenced = "```json\n" + json.dumps(
        [{"name": "a", "description": "d", "body": "x"}]
    ) + "\n```"
    result = distill_sessions(
        sessions, memory_dir=tmp_path, provider=lambda _p: fenced
    )
    assert len(result.candidates) == 1


def test_distill_invalid_json_falls_back(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}", files=("src/a.py",)) for i in range(5)]
    result = distill_sessions(
        sessions,
        memory_dir=tmp_path,
        provider=lambda _p: "not json at all",
    )
    assert result.used_mechanical_fallback is True
    # mechanical fallback emits one candidate based on repeated files
    assert len(result.candidates) == 1
    assert result.candidates[0].name == "recurring-files"


def test_distill_provider_error_falls_back(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}", files=("src/a.py",)) for i in range(5)]

    def boom(_p: str) -> str:
        raise ProviderError("LLM dead")

    result = distill_sessions(sessions, memory_dir=tmp_path, provider=boom)
    assert result.used_mechanical_fallback is True


def test_distill_skips_malformed_candidates(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    response = json.dumps(
        [
            {"name": "ok", "description": "d", "body": "x"},  # valid
            {"name": "missing-body", "description": "d"},  # invalid: no body
            {"name": "", "description": "d", "body": "x"},  # invalid: empty
            {"name": "ok-too", "description": "d", "body": "y"},  # valid
        ]
    )
    result = distill_sessions(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    names = sorted(c.name for c in result.candidates)
    assert names == ["ok", "ok-too"]


def test_distill_caps_at_six(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    response = json.dumps(
        [
            {"name": f"name-{i}", "description": "d", "body": "x"}
            for i in range(20)
        ]
    )
    result = distill_sessions(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.candidates) == 6


def test_distill_dedupes_by_slug(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    response = json.dumps(
        [
            {"name": "Auth", "description": "d", "body": "x"},
            {"name": "auth", "description": "d", "body": "x"},  # same slug
        ]
    )
    result = distill_sessions(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.candidates) == 1


# ----------------------------------------------------------------------
# Mechanical fallback content
# ----------------------------------------------------------------------


def test_mechanical_picks_recurring_files(tmp_path: Path) -> None:
    sessions = [
        _sfd("s1", files=("a.py", "b.py")),
        _sfd("s2", files=("a.py", "c.py")),
        _sfd("s3", files=("a.py",)),
        _sfd("s4", files=("b.py", "d.py")),
        _sfd("s5", files=("e.py",)),
    ]
    result = distill_sessions(sessions, memory_dir=tmp_path)
    assert result.used_mechanical_fallback is True
    assert len(result.candidates) == 1
    body = result.candidates[0].body
    # a.py appears in 3 sessions, b.py in 2 — both qualify.
    assert "`a.py`" in body
    assert "`b.py`" in body
    assert "`c.py`" not in body  # only 1 session


def test_mechanical_no_recurring_files_yields_no_candidates(tmp_path: Path) -> None:
    sessions = [
        _sfd("s1", files=("a.py",)),
        _sfd("s2", files=("b.py",)),
        _sfd("s3", files=("c.py",)),
        _sfd("s4", files=("d.py",)),
        _sfd("s5", files=("e.py",)),
    ]
    result = distill_sessions(sessions, memory_dir=tmp_path)
    assert result.candidates == ()


# ----------------------------------------------------------------------
# Below threshold
# ----------------------------------------------------------------------


def test_below_threshold_short_circuits(tmp_path: Path) -> None:
    sessions = [_sfd("s1"), _sfd("s2")]
    result = distill_sessions(sessions, memory_dir=tmp_path, min_sessions=5)
    assert result.candidates == ()
    assert not (tmp_path / "distilled").exists()


# ----------------------------------------------------------------------
# Render proposed file
# ----------------------------------------------------------------------


def test_render_includes_required_frontmatter() -> None:
    c = DistilledCandidate(
        name="auth-jwt",
        description="JWT signed with HS256.",
        body="- token from header\n",
        source_sessions=("s0", "s1"),
    )
    text = render_proposed_file(c, today=date(2026, 4, 28))
    assert "type: agent" in text
    assert "scope: project" in text
    assert "enforcement: hint" in text
    assert "name: auth-jwt" in text
    assert "source_sessions:" in text


# ----------------------------------------------------------------------
# Files written to disk
# ----------------------------------------------------------------------


def test_distill_writes_proposed_files(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    response = json.dumps(
        [{"name": "auth", "description": "d", "body": "- bullet\n"}]
    )
    result = distill_sessions(
        sessions, memory_dir=tmp_path, provider=lambda _p: response
    )
    assert len(result.written_paths) == 1
    p = result.written_paths[0]
    assert p.is_relative_to(distilled_dir(memory_dir=tmp_path))
    assert p.name == "auth.proposed.md"
    text = p.read_text()
    assert "type: agent" in text


def test_distill_overwrites_existing(tmp_path: Path) -> None:
    sessions = [_sfd(f"s{i}") for i in range(5)]
    distill_sessions(
        sessions,
        memory_dir=tmp_path,
        provider=lambda _p: json.dumps(
            [{"name": "auth", "description": "v1", "body": "old\n"}]
        ),
    )
    distill_sessions(
        sessions,
        memory_dir=tmp_path,
        provider=lambda _p: json.dumps(
            [{"name": "auth", "description": "v2", "body": "new\n"}]
        ),
    )
    p = tmp_path / "distilled" / "auth.proposed.md"
    text = p.read_text()
    assert "v2" in text
    assert "v1" not in text


# ----------------------------------------------------------------------
# load_session_for_distill / run_tier2 integration
# ----------------------------------------------------------------------


def test_load_session_for_distill(tmp_path: Path) -> None:
    fm = SessionFrontmatter(
        type="session",
        session_id="abc",
        client="claude-code",
        started_at=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
        task_hash="t1",
        files_touched=("src/a.py",),
        outcome="completed",
    )
    p = session_path(
        "abc",
        started_at=fm.started_at,
        memory_dir=tmp_path,
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_session_file(fm, "## Investigated\n- ok\n"))

    sfd = load_session_for_distill(p)
    assert sfd is not None
    assert sfd.session_id == "abc"
    assert sfd.task_hash == "t1"
    assert sfd.files_touched == ("src/a.py",)
    assert "Investigated" in sfd.body


def test_load_session_returns_none_for_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("not yaml")
    assert load_session_for_distill(bad) is None


def test_run_tier2_end_to_end(tmp_path: Path) -> None:
    # 5 session files on disk → run_tier2 reads + distills.
    sessions_data = [("a", ("src/x.py",)), ("b", ("src/x.py",)), ("c", ("src/y.py",)), ("d", ("src/x.py",)), ("e", ("src/z.py",))]
    paths: list[Path] = []
    for sid, files in sessions_data:
        fm = SessionFrontmatter(
            type="session",
            session_id=sid,
            client="claude-code",
            started_at=datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 26, 15, 0, tzinfo=timezone.utc),
            task_hash="t1",
            files_touched=files,
            outcome="completed",
        )
        p = session_path(sid, started_at=fm.started_at, memory_dir=tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_session_file(fm, "narrative\n"))
        paths.append(p)

    result = run_tier2(sessions_paths=paths, memory_dir=tmp_path)
    assert result.used_mechanical_fallback is True
    # x.py appears in 3 sessions → recurring-files fires.
    assert len(result.candidates) == 1
