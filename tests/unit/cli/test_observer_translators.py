"""T-205 tests for engram.observer.translators — host hook payload mappers."""

from __future__ import annotations


from engram.observer.translators import (
    KNOWN_TRANSLATORS,
    translate,
    translate_claude_code,
    translate_codex,
)


# ----------------------------------------------------------------------
# Claude Code translator
# ----------------------------------------------------------------------


def test_claude_code_minimal_tool_use() -> None:
    out = translate_claude_code({"tool_name": "Read"})
    assert out == {"event": "tool_use", "tool": "Read"}


def test_claude_code_extracts_file_path() -> None:
    out = translate_claude_code(
        {"tool_name": "Read", "tool_input": {"file_path": "src/foo.ts"}}
    )
    assert out is not None
    assert out["files"] == ["src/foo.ts"]


def test_claude_code_extracts_paths_list() -> None:
    out = translate_claude_code(
        {"tool_name": "Edit", "tool_input": {"file_paths": ["a.py", "b.py"]}}
    )
    assert out is not None
    assert out["files"] == ["a.py", "b.py"]


def test_claude_code_dedupes_files() -> None:
    out = translate_claude_code(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "a.py", "files": ["a.py", "b.py"]},
        }
    )
    assert out is not None
    assert out["files"] == ["a.py", "b.py"]


def test_claude_code_records_result_chars_string() -> None:
    out = translate_claude_code({"tool_name": "Read", "tool_response": "hello"})
    assert out is not None
    assert out["result_chars"] == 5


def test_claude_code_records_result_chars_dict() -> None:
    out = translate_claude_code(
        {"tool_name": "Read", "tool_response": {"content": "hi"}}
    )
    assert out is not None
    # JSON serialisation length: {"content":"hi"} = 16 chars
    assert out["result_chars"] > 0


def test_claude_code_returns_none_without_tool_name() -> None:
    assert translate_claude_code({"foo": "bar"}) is None


def test_claude_code_returns_none_with_non_string_tool_name() -> None:
    assert translate_claude_code({"tool_name": 123}) is None


def test_claude_code_ignores_non_dict_tool_input() -> None:
    out = translate_claude_code({"tool_name": "Read", "tool_input": "string"})
    assert out is not None
    assert "files" not in out


# ----------------------------------------------------------------------
# Codex translator
# ----------------------------------------------------------------------


def test_codex_falls_through_to_claude_code() -> None:
    out = translate_codex(
        {"tool_name": "Read", "tool_input": {"file_path": "src/foo.ts"}}
    )
    assert out is not None
    assert out["files"] == ["src/foo.ts"]


def test_codex_uses_function_name_fallback() -> None:
    out = translate_codex({"function_name": "exec_bash"})
    assert out == {"event": "tool_use", "tool": "exec_bash"}


def test_codex_uses_name_fallback() -> None:
    out = translate_codex({"name": "my_tool"})
    assert out == {"event": "tool_use", "tool": "my_tool"}


def test_codex_returns_none_when_no_signal() -> None:
    assert translate_codex({"foo": "bar"}) is None


# ----------------------------------------------------------------------
# Dispatch table
# ----------------------------------------------------------------------


def test_known_translators_keys() -> None:
    assert "claude-code" in KNOWN_TRANSLATORS
    assert "codex" in KNOWN_TRANSLATORS


def test_translate_dispatches_correctly() -> None:
    out = translate("claude-code", {"tool_name": "Read"})
    assert out == {"event": "tool_use", "tool": "Read"}


def test_translate_unknown_returns_none() -> None:
    assert translate("nonexistent", {"tool_name": "Read"}) is None
