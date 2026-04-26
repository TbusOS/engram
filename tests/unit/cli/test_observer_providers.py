"""T-204 tests for engram.observer.providers — ollama / openai-compat / mechanical."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from engram.observer.providers import (
    MECHANICAL_MARKER,
    ProviderError,
    make_ollama_provider,
    make_openai_compatible_provider,
    mechanical_provider,
)


# ----------------------------------------------------------------------
# Mechanical sentinel
# ----------------------------------------------------------------------


def test_mechanical_provider_returns_marker() -> None:
    assert mechanical_provider("anything") == MECHANICAL_MARKER


def test_marker_is_stable_string() -> None:
    """The sentinel must be a stable, recognizable string."""
    # NUL-bracketed so it cannot collide with any plausible model output.
    assert "engram-mechanical-narrative" in MECHANICAL_MARKER
    assert MECHANICAL_MARKER.startswith("\x00")
    assert MECHANICAL_MARKER.endswith("\x00")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))
        self.status = status

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_: Any) -> None:
        self._buf.close()


def _fake_opener(payload: dict[str, Any]) -> Any:
    captured: dict[str, Any] = {}

    def _opener(req: Any, timeout: float = 0) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8")) if req.data else None
        captured["headers"] = dict(req.headers.items())
        captured["timeout"] = timeout
        return _FakeResponse(payload)

    _opener.captured = captured  # type: ignore[attr-defined]
    return _opener


# ----------------------------------------------------------------------
# Ollama provider
# ----------------------------------------------------------------------


def test_ollama_returns_response_string() -> None:
    opener = _fake_opener({"response": "## Investigated\n- did stuff", "done": True})
    p = make_ollama_provider(
        endpoint="http://localhost:11434", model="qwen2.5:7b", opener=opener
    )
    out = p("hello")
    assert "did stuff" in out


def test_ollama_posts_to_api_generate() -> None:
    opener = _fake_opener({"response": "ok"})
    p = make_ollama_provider(endpoint="http://localhost:11434", model="x", opener=opener)
    p("hi")
    assert opener.captured["url"] == "http://localhost:11434/api/generate"  # type: ignore[attr-defined]


def test_ollama_disables_streaming() -> None:
    opener = _fake_opener({"response": "ok"})
    p = make_ollama_provider(endpoint="http://localhost:11434", model="x", opener=opener)
    p("hi")
    assert opener.captured["body"]["stream"] is False  # type: ignore[attr-defined]


def test_ollama_passes_options_when_set() -> None:
    opener = _fake_opener({"response": "ok"})
    p = make_ollama_provider(
        endpoint="http://localhost:11434",
        model="x",
        opener=opener,
        options={"temperature": 0.2},
    )
    p("hi")
    assert opener.captured["body"]["options"] == {"temperature": 0.2}  # type: ignore[attr-defined]


def test_ollama_invalid_json_raises_provider_error() -> None:
    class _BadResp:
        status = 200

        def read(self) -> bytes:
            return b"not json"

        def __enter__(self) -> _BadResp:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    def opener(req: Any, timeout: float = 0) -> _BadResp:
        return _BadResp()

    p = make_ollama_provider(endpoint="http://x", model="y", opener=opener)
    with pytest.raises(ProviderError):
        p("hi")


def test_ollama_missing_response_field_raises() -> None:
    opener = _fake_opener({"done": True})  # no "response"
    p = make_ollama_provider(endpoint="http://x", model="y", opener=opener)
    with pytest.raises(ProviderError):
        p("hi")


# ----------------------------------------------------------------------
# OpenAI-compatible provider
# ----------------------------------------------------------------------


def test_openai_compat_extracts_choices_content() -> None:
    opener = _fake_opener(
        {"choices": [{"message": {"role": "assistant", "content": "## answer"}}]}
    )
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1", model="m", opener=opener
    )
    assert p("hi") == "## answer"


def test_openai_compat_appends_chat_completions() -> None:
    opener = _fake_opener({"choices": [{"message": {"content": "ok"}}]})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1", model="m", opener=opener
    )
    p("hi")
    assert (
        opener.captured["url"]  # type: ignore[attr-defined]
        == "https://api.example.com/v1/chat/completions"
    )


def test_openai_compat_does_not_double_append() -> None:
    opener = _fake_opener({"choices": [{"message": {"content": "ok"}}]})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1/chat/completions", model="m", opener=opener
    )
    p("hi")
    assert (
        opener.captured["url"]  # type: ignore[attr-defined]
        == "https://api.example.com/v1/chat/completions"
    )


def test_openai_compat_sends_authorization_when_api_key_provided() -> None:
    opener = _fake_opener({"choices": [{"message": {"content": "ok"}}]})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1", model="m", api_key="sk-test", opener=opener
    )
    p("hi")
    headers = opener.captured["headers"]  # type: ignore[attr-defined]
    # urllib lowercases header names in Request; check both cases.
    auth = headers.get("Authorization") or headers.get("authorization")
    assert auth == "Bearer sk-test"


def test_openai_compat_omits_authorization_when_no_api_key() -> None:
    opener = _fake_opener({"choices": [{"message": {"content": "ok"}}]})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1", model="m", opener=opener
    )
    p("hi")
    headers = opener.captured["headers"]  # type: ignore[attr-defined]
    assert "Authorization" not in headers and "authorization" not in headers


def test_openai_compat_missing_choices_raises() -> None:
    opener = _fake_opener({"error": {"message": "bad"}})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1", model="m", opener=opener
    )
    with pytest.raises(ProviderError):
        p("hi")


def test_openai_compat_extra_headers_merged() -> None:
    opener = _fake_opener({"choices": [{"message": {"content": "ok"}}]})
    p = make_openai_compatible_provider(
        endpoint="https://api.example.com/v1",
        model="m",
        opener=opener,
        extra_headers={"X-Trace-Id": "abc"},
    )
    p("hi")
    headers = opener.captured["headers"]  # type: ignore[attr-defined]
    trace = headers.get("X-Trace-Id") or headers.get("X-trace-id")
    assert trace == "abc"
