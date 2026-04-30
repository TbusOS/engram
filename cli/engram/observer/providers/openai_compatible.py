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

Security hardening (security reviewer F2, 2026-04-30):

- ``endpoint`` MUST start with ``http://`` or ``https://``; the file
  scheme and other bizarre URLs are rejected up-front.
- The default opener strips the ``Authorization`` header on cross-host
  redirects so a poisoned 302 cannot exfiltrate the API key to an
  unrelated host.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from engram.observer.providers.base import (
    Provider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeout,
    ProviderUnavailable,
)

__all__ = ["make_openai_compatible_provider"]


DEFAULT_TIMEOUT_SECONDS = 60.0


_ALLOWED_SCHEMES = {"http", "https"}


class _NoCrossHostAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Drop the Authorization header on redirects that change host.

    Security reviewer F2 — without this, a 302 to attacker.example
    receives our ``Bearer <api_key>``. Same-host redirects keep the
    header so legitimate API surface migrations still work.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        old_host = urllib.parse.urlparse(req.full_url).netloc
        new_host = urllib.parse.urlparse(newurl).netloc
        if old_host != new_host:
            for header_name in ("Authorization", "Auth"):
                # urllib.Request stores headers case-insensitively under
                # ``unredirected_hdrs`` and ``headers``; clear both.
                new_req.unredirected_hdrs.pop(header_name, None)
                new_req.headers.pop(header_name, None)
        return new_req


def _safe_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoCrossHostAuthRedirect)


def _validate_endpoint(endpoint: str) -> None:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        raise ProviderError(
            f"openai-compatible endpoint must be http(s)://; got {endpoint!r}"
        )


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
    _validate_endpoint(endpoint)
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
                resp = _safe_opener().open(req, timeout=timeout_seconds)
        except urllib.error.HTTPError as exc:
            # Code reviewer C3 — distinguish auth / rate-limit / 5xx so
            # the daemon journal records useful context instead of a
            # generic "ProviderError".
            if exc.code in (401, 403):
                raise ProviderAuthError(
                    f"OpenAI-compat auth failure (HTTP {exc.code}): {exc.reason}"
                ) from exc
            if exc.code == 429:
                raise ProviderRateLimitError(
                    f"OpenAI-compat rate limited (HTTP 429): {exc.reason}"
                ) from exc
            if 500 <= exc.code < 600:
                raise ProviderUnavailable(
                    f"OpenAI-compat server error (HTTP {exc.code}): {exc.reason}"
                ) from exc
            raise ProviderError(
                f"OpenAI-compat HTTP {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                raise ProviderTimeout(
                    f"OpenAI-compat call timed out after {timeout_seconds}s: {exc}"
                ) from exc
            raise ProviderUnavailable(
                f"OpenAI-compat unreachable: {exc}"
            ) from exc
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
