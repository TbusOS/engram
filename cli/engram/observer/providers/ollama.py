"""Ollama HTTP provider.

POST /api/generate against a local ollama daemon. Streaming disabled so
the call is one synchronous round-trip.

Why a dedicated module instead of "just use openai-compatible against
ollama's OpenAI shim?" — ollama's native API is **always** available
on a fresh install; the OpenAI shim requires the user to run ``ollama
serve`` with the right flags. We default to native here so a brand-new
install needs zero configuration beyond ``ollama pull <model>``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from engram.observer.providers.base import (
    Provider,
    ProviderError,
    ProviderTimeout,
)

__all__ = ["make_ollama_provider"]


DEFAULT_TIMEOUT_SECONDS = 30.0


def make_ollama_provider(
    *,
    endpoint: str = "http://localhost:11434",
    model: str = "qwen2.5:7b",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    options: dict[str, Any] | None = None,
    opener: Any | None = None,
) -> Provider:
    """Return a :class:`Provider` that calls ollama's ``/api/generate``.

    ``opener`` is a hook for tests to inject a fake urllib opener. In
    production it stays ``None`` and we use ``urllib.request.urlopen``
    directly.
    """
    url = endpoint.rstrip("/") + "/api/generate"

    def _call(prompt: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            if opener is not None:
                resp = opener(req, timeout=timeout_seconds)
            else:
                resp = urllib.request.urlopen(req, timeout=timeout_seconds)
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                raise ProviderTimeout(
                    f"ollama call timed out after {timeout_seconds}s: {exc}"
                ) from exc
            raise ProviderError(f"ollama HTTP error: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"ollama call timed out after {timeout_seconds}s: {exc}"
            ) from exc

        with resp:
            try:
                data = json.loads(resp.read().decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ProviderError(f"ollama returned invalid JSON: {exc}") from exc

        text = data.get("response")
        if not isinstance(text, str):
            raise ProviderError(
                f"ollama response missing 'response' string: keys={sorted(data)}"
            )
        return text

    return _call
