"""OpenAI-compatible Chat Completions provider.

POST ``<endpoint>/chat/completions`` (or ``<endpoint>`` if it already
ends in ``chat/completions``). Works against any server that speaks
the OpenAI Chat Completions wire format: OpenAI itself, DeepSeek,
vLLM, llama.cpp's HTTP server, ollama's OpenAI shim, etc.

The body is the bare minimum:

    {"model": "...", "messages": [{"role": "user", "content": prompt}]}

Tier 1's prompt is one self-contained block that includes both system
instructions and the timeline facts. We do not split it into separate
``system`` / ``user`` messages — every model in the wild understands
"long user message", but interpretation of the ``system`` role differs
across providers in surprising ways.
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

__all__ = ["make_openai_compatible_provider"]


DEFAULT_TIMEOUT_SECONDS = 60.0


def make_openai_compatible_provider(
    *,
    endpoint: str,
    model: str,
    api_key: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    extra_headers: dict[str, str] | None = None,
    opener: Any | None = None,
) -> Provider:
    """Return a :class:`Provider` that POSTs to a Chat Completions endpoint.

    ``endpoint`` examples:

    - ``http://localhost:11434/v1`` (ollama OpenAI shim)
    - ``https://api.deepseek.com/v1``
    - ``https://api.openai.com/v1``

    The trailing ``/chat/completions`` is appended automatically; if
    the user supplies it, we leave it alone.
    """
    if endpoint.rstrip("/").endswith("chat/completions"):
        url = endpoint
    else:
        url = endpoint.rstrip("/") + "/chat/completions"

    def _call(prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            if opener is not None:
                resp = opener(req, timeout=timeout_seconds)
            else:
                resp = urllib.request.urlopen(req, timeout=timeout_seconds)
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                raise ProviderTimeout(
                    f"OpenAI-compat call timed out after {timeout_seconds}s: {exc}"
                ) from exc
            raise ProviderError(f"OpenAI-compat HTTP error: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"OpenAI-compat call timed out after {timeout_seconds}s: {exc}"
            ) from exc

        with resp:
            try:
                data = json.loads(resp.read().decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"OpenAI-compat returned invalid JSON: {exc}"
                ) from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"OpenAI-compat response missing choices[0].message.content: {data!r}"
            ) from exc

        if not isinstance(text, str):
            raise ProviderError(
                f"OpenAI-compat content is not a string: {type(text).__name__}"
            )
        return text

    return _call
