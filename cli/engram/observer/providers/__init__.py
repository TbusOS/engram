"""Pluggable LLM providers for the observer's Tier 1/2/3 compactors.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2 + §11.5.

Engram's compactor is **provider-agnostic by design** — Tier 1 may run
on a local 7B model via ollama, Tier 2 on a 32B model, Tier 3 on a
hosted model, or **everything may degrade to mechanical-only** if the
user has not configured an LLM at all. Each tier picks its own
provider via ``~/.engram/config.toml [observer.compactor.tier_n]``.

Public surface:

- :class:`Provider` — minimal callable protocol (prompt → narrative).
- :class:`ProviderError` — base error so callers can catch one type.
- :func:`make_ollama_provider` — POST /api/generate to a local ollama.
- :func:`make_openai_compatible_provider` — POST /v1/chat/completions
  to any endpoint that speaks the Chat Completions wire shape (OpenAI,
  DeepSeek, vLLM, llama.cpp server, ollama's OpenAI shim, ...).
- :func:`mechanical_provider` — no-LLM fallback that returns a marker;
  callers detect this and route to the Tier 0 narrative renderer.

The providers are deliberately tiny — anything more sophisticated
(streaming, function calling, JSON mode) should live in a separate
module so this layer stays testable without spinning up real models.
"""

from __future__ import annotations

from engram.observer.providers.base import (
    MECHANICAL_MARKER,
    Provider,
    ProviderError,
    ProviderTimeout,
    mechanical_provider,
)
from engram.observer.providers.ollama import make_ollama_provider
from engram.observer.providers.openai_compatible import make_openai_compatible_provider

__all__ = [
    "MECHANICAL_MARKER",
    "Provider",
    "ProviderError",
    "ProviderTimeout",
    "make_ollama_provider",
    "make_openai_compatible_provider",
    "mechanical_provider",
]
