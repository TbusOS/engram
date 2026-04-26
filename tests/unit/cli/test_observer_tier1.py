"""T-204 tests for engram.observer.tier1 — narrative + Session asset writer."""

from __future__ import annotations

from pathlib import Path

from engram.observer.protocol import parse_event
from engram.observer.providers import (
    ProviderError,
    mechanical_provider,
)
from engram.observer.queue import enqueue
from engram.observer.session import parse_session_file
from engram.observer.tier0 import compact_session
from engram.observer.tier1 import (
    DEFAULT_PROMPT_HEADER,
    Tier1Result,
    build_prompt,
    compact_to_narrative,
    compact_to_session_asset,
    summarize_timeline,
)


def _write_timeline(tmp_path: Path, *events) -> Path:
    """Build a fixture session: enqueue events → run Tier 0 → return timeline path."""
    base = tmp_path
    for evt in events:
        e = parse_event(
            evt,
            session_id="sess_abc",
            client="claude-code",
            now=evt.get("_t", "2026-04-26T14:00:00.000Z"),
        )
        enqueue(e, base=base)
    queue_path = base / "observe-queue" / "sess_abc.jsonl"
    sessions_dir = base / "timelines"
    compact_session("sess_abc", queue_path=queue_path, sessions_dir=sessions_dir)
    return sessions_dir / "sess_abc.timeline.jsonl"


# ----------------------------------------------------------------------
# summarize_timeline
# ----------------------------------------------------------------------


def test_summarize_empty_when_missing(tmp_path: Path) -> None:
    s = summarize_timeline(tmp_path / "nope.jsonl")
    assert s.tool_calls == 0
    assert s.files_touched == []
    assert s.outcome == "unknown"


def test_summarize_aggregates_tool_counts(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        {"event": "tool_use", "tool": "Read", "files": ["b.py"]},
        {"event": "tool_use", "tool": "Edit", "files": ["a.py"]},
    )
    s = summarize_timeline(timeline)
    assert s.tool_counts == {"Read": 2, "Edit": 1}
    assert s.files_touched == ["a.py", "b.py"]
    assert s.tool_calls == 3


def test_summarize_captures_errors_and_outcome(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Bash"},
        {"event": "error", "stderr_first_line": "ImportError: foo"},
        {"event": "session_end", "outcome": "completed"},
    )
    s = summarize_timeline(timeline)
    assert s.errors == ["ImportError: foo"]
    assert s.outcome == "completed"


def test_summarize_user_prompt_count(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "user_prompt", "prompt_chars": 50},
        {"event": "user_prompt", "prompt_chars": 30},
    )
    s = summarize_timeline(timeline)
    assert s.user_prompts == 2


def test_summarize_started_ended_inferred(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "_t": "2026-04-26T14:00:00.000Z"},
        {"event": "session_end", "outcome": "completed", "_t": "2026-04-26T15:00:00.000Z"},
    )
    s = summarize_timeline(timeline)
    assert s.started_at is not None
    assert s.ended_at is not None
    assert s.ended_at > s.started_at


# ----------------------------------------------------------------------
# build_prompt
# ----------------------------------------------------------------------


def test_prompt_contains_header_and_facts(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]}
    )
    s = summarize_timeline(timeline)
    p = build_prompt(s)
    assert DEFAULT_PROMPT_HEADER.split("\n")[0] in p
    assert "## Facts" in p
    assert "Tool calls: 1" in p
    assert "`a.py`" in p


def test_prompt_omits_empty_sections(tmp_path: Path) -> None:
    timeline = _write_timeline(tmp_path, {"event": "user_prompt", "prompt_chars": 10})
    s = summarize_timeline(timeline)
    p = build_prompt(s)
    assert "Files touched" not in p
    assert "Tools used" not in p


# ----------------------------------------------------------------------
# compact_to_narrative
# ----------------------------------------------------------------------


def test_narrative_with_real_provider_uses_response(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]}
    )

    def fake_provider(_prompt: str) -> str:
        return "## Investigated\n- bespoke narrative\n"

    out = compact_to_narrative(timeline, provider=fake_provider)
    assert "bespoke narrative" in out


def test_narrative_falls_back_on_provider_error(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]}
    )

    def boom(_prompt: str) -> str:
        raise ProviderError("LLM dead")

    out = compact_to_narrative(timeline, provider=boom)
    # Mechanical narrative has the deterministic header.
    assert "# Narrative (mechanical)" in out
    assert "`Read`: 1" in out


def test_narrative_falls_back_on_marker(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]}
    )
    out = compact_to_narrative(timeline, provider=mechanical_provider)
    assert "# Narrative (mechanical)" in out


def test_narrative_falls_back_on_empty_response(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read"}
    )

    def empty(_prompt: str) -> str:
        return "   \n  "

    out = compact_to_narrative(timeline, provider=empty)
    assert "# Narrative (mechanical)" in out


def test_narrative_default_provider_is_mechanical(tmp_path: Path) -> None:
    """Calling with provider=None should never call the network."""
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read"}
    )
    out = compact_to_narrative(timeline)
    assert "# Narrative (mechanical)" in out


# ----------------------------------------------------------------------
# compact_to_session_asset
# ----------------------------------------------------------------------


def test_asset_written_to_user_global(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
        {"event": "session_end", "outcome": "completed"},
    )
    monkey_user_root = tmp_path / "engram-home"
    # Patch user_root via tier1's import surface.
    from engram.observer import tier1 as tier1_mod

    orig_user_root = tier1_mod.user_root

    def _user_root() -> Path:
        return monkey_user_root

    tier1_mod.user_root = _user_root  # type: ignore[assignment]
    try:
        result = compact_to_session_asset(
            "sess_abc",
            timeline_path=timeline,
            client="claude-code",
            project_root=None,
            provider=lambda _p: "## Investigated\n- did the thing\n",
        )
    finally:
        tier1_mod.user_root = orig_user_root  # type: ignore[assignment]

    assert isinstance(result, Tier1Result)
    assert result.used_mechanical_fallback is False
    assert result.asset_path.exists()
    assert result.asset_path.is_relative_to(monkey_user_root / "sessions")
    fm, body = parse_session_file(result.asset_path)
    assert fm.session_id == "sess_abc"
    assert fm.client == "claude-code"
    assert "did the thing" in body


def test_asset_written_under_project_root(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Read", "files": ["a.py"]},
    )
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    result = compact_to_session_asset(
        "sess_abc",
        timeline_path=timeline,
        client="codex",
        project_root=project,
        provider=lambda _p: "## Investigated\n- ok\n",
    )
    assert result.asset_path.is_relative_to(project / ".memory" / "sessions")
    fm, _ = parse_session_file(result.asset_path)
    assert fm.client == "codex"


def test_asset_uses_mechanical_when_provider_errors(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read", "files": ["a.py"]}
    )
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)

    def boom(_p: str) -> str:
        raise ProviderError("nope")

    result = compact_to_session_asset(
        "sess_abc",
        timeline_path=timeline,
        client="manual",
        project_root=project,
        provider=boom,
    )
    assert result.used_mechanical_fallback is True
    fm, body = parse_session_file(result.asset_path)
    assert "# Narrative (mechanical)" in body
    assert fm.tool_calls == 1


def test_asset_frontmatter_records_outcome(tmp_path: Path) -> None:
    timeline = _write_timeline(
        tmp_path,
        {"event": "tool_use", "tool": "Read"},
        {"event": "session_end", "outcome": "completed"},
    )
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)
    result = compact_to_session_asset(
        "sess_abc",
        timeline_path=timeline,
        client="claude-code",
        project_root=project,
        provider=lambda _p: "## Investigated\n- ok\n",
    )
    fm, _ = parse_session_file(result.asset_path)
    assert fm.outcome == "completed"


def test_asset_overwrite_on_rerun(tmp_path: Path) -> None:
    """Tier 1 is idempotent: re-running rewrites the same asset path."""
    timeline = _write_timeline(
        tmp_path, {"event": "tool_use", "tool": "Read"}
    )
    project = tmp_path / "proj"
    (project / ".memory").mkdir(parents=True)

    r1 = compact_to_session_asset(
        "sess_abc",
        timeline_path=timeline,
        client="claude-code",
        project_root=project,
        provider=lambda _p: "## first\n- v1\n",
    )
    r2 = compact_to_session_asset(
        "sess_abc",
        timeline_path=timeline,
        client="claude-code",
        project_root=project,
        provider=lambda _p: "## second\n- v2\n",
    )
    assert r1.asset_path == r2.asset_path
    body = r2.asset_path.read_text()
    assert "v2" in body
    assert "v1" not in body
