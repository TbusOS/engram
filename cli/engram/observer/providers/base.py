"""Provider protocol + mechanical fallback.

The provider contract is intentionally one method:

    def __call__(self, prompt: str) -> str: ...

That keeps unit tests trivial (lambda for "what would the model say?")
and lets us swap implementations without touching Tier 1 logic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

__all__ = [
    "MECHANICAL_MARKER",
    "Provider",
    "ProviderError",
    "ProviderTimeout",
    "mechanical_provider",
]


# When the caller asked for a mechanical-only narrative (no LLM
# configured), the provider returns this exact string. Callers detect
# it and substitute :func:`engram.observer.tier0.render_narrative_from_timeline`.
# Using a sentinel rather than ``None`` keeps the type signature flat
# and avoids ``Optional[str]`` flowing through the rest of Tier 1.
MECHANICAL_MARKER = "\x00engram-mechanical-narrative\x00"


# Provider is "any callable mapping a prompt to a string". Modelled as
# a TypeAlias rather than a Protocol so plain ``def`` and ``lambda``
# pass mypy strict mode without needing a manual ``cast(Provider, fn)``.
Provider: TypeAlias = Callable[[str], str]


class ProviderError(RuntimeError):
    """Base class for provider failures (HTTP, parsing, model error)."""


class ProviderTimeout(ProviderError):
    """Raised when an LLM call exceeded the configured timeout."""


def mechanical_provider(_prompt: str) -> str:
    """No-LLM fallback. Returns the sentinel; caller renders mechanically."""
    return MECHANICAL_MARKER
