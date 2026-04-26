"""Observer config — read ``[observer.compactor.tier_n]`` from TOML.

Spec ``docs/superpowers/specs/2026-04-26-auto-continuation.md`` §2.2.

The observer config lives at ``~/.engram/config.toml`` (or any path the
caller passes for tests). Each tier is independently configured:

    [observer.compactor.tier1]
    provider = "ollama"
    endpoint = "http://localhost:11434"
    model = "qwen2.5:7b"
    timeout_seconds = 30

    [observer.compactor.tier2]
    provider = "openai-compatible"
    endpoint = "http://localhost:11434/v1"
    model = "qwen2.5:32b"
    timeout_seconds = 120

    [observer.compactor.tier3]
    provider = "openai-compatible"
    endpoint = "https://api.deepseek.com/v1"
    model = "deepseek-chat"
    api_key = "$DEEPSEEK_API_KEY"
    timeout_seconds = 300

If the section is missing, :func:`load_tier_provider` returns the
mechanical fallback. **engram is always usable**, even with no LLM
config and no network — Tier 0 + mechanical-only Tier 1 is the floor.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import tomli

from engram.core.paths import user_root
from engram.observer.providers import (
    Provider,
    make_ollama_provider,
    make_openai_compatible_provider,
    mechanical_provider,
)

__all__ = [
    "DEFAULT_CONFIG_FILENAME",
    "ObserverConfigError",
    "TierConfig",
    "load_tier_config",
    "load_tier_provider",
    "provider_from_tier_config",
]


DEFAULT_CONFIG_FILENAME = "config.toml"


class ObserverConfigError(ValueError):
    """Raised when the observer config has an invalid value."""


class TierConfig:
    """Parsed tier configuration. Empty / missing → mechanical fallback."""

    __slots__ = (
        "api_key",
        "endpoint",
        "extra_headers",
        "model",
        "options",
        "provider",
        "timeout_seconds",
    )

    def __init__(
        self,
        *,
        provider: str = "mechanical",
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        options: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.options = options or {}
        self.extra_headers = extra_headers or {}

    @property
    def is_mechanical(self) -> bool:
        return self.provider == "mechanical"


def _resolve_env_ref(value: str | None) -> str | None:
    """Expand ``$VAR`` and ``${VAR}`` env refs, returning None if unset.

    A literal value with no ``$`` prefix passes through verbatim. This
    keeps secrets out of the config file while letting users hardcode
    values when they want.
    """
    if value is None:
        return None
    s = value.strip()
    if s.startswith("${") and s.endswith("}"):
        return os.environ.get(s[2:-1])
    if s.startswith("$"):
        return os.environ.get(s[1:])
    return s or None


def load_tier_config(
    tier: int,
    *,
    config_path: Path | None = None,
) -> TierConfig:
    """Read ``[observer.compactor.tier_<n>]`` from ``config.toml``.

    Returns a :class:`TierConfig` with ``provider="mechanical"`` if the
    section is missing or the file does not exist.
    """
    if config_path is None:
        config_path = user_root() / DEFAULT_CONFIG_FILENAME
    if not config_path.exists():
        return TierConfig(provider="mechanical")

    try:
        data = tomli.loads(config_path.read_text(encoding="utf-8"))
    except tomli.TOMLDecodeError as exc:
        raise ObserverConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    section = (
        data.get("observer", {})
        .get("compactor", {})
        .get(f"tier{tier}", None)
    )
    if not section:
        return TierConfig(provider="mechanical")

    if not isinstance(section, dict):
        raise ObserverConfigError(
            f"observer.compactor.tier{tier} must be a table, got {type(section).__name__}"
        )

    provider = section.get("provider", "mechanical")
    if not isinstance(provider, str):
        raise ObserverConfigError(
            f"observer.compactor.tier{tier}.provider must be a string"
        )

    return TierConfig(
        provider=provider,
        endpoint=section.get("endpoint"),
        model=section.get("model"),
        api_key=_resolve_env_ref(section.get("api_key")),
        timeout_seconds=section.get("timeout_seconds"),
        options=section.get("options"),
        extra_headers=section.get("extra_headers"),
    )


def provider_from_tier_config(cfg: TierConfig) -> Provider:
    """Build a callable :class:`Provider` from a parsed :class:`TierConfig`."""
    if cfg.is_mechanical:
        return mechanical_provider

    if cfg.provider == "ollama":
        if not cfg.endpoint or not cfg.model:
            raise ObserverConfigError(
                "ollama provider requires endpoint + model"
            )
        kwargs: dict[str, Any] = {
            "endpoint": cfg.endpoint,
            "model": cfg.model,
        }
        if cfg.timeout_seconds is not None:
            kwargs["timeout_seconds"] = cfg.timeout_seconds
        if cfg.options:
            kwargs["options"] = cfg.options
        return make_ollama_provider(**kwargs)

    if cfg.provider == "openai-compatible":
        if not cfg.endpoint or not cfg.model:
            raise ObserverConfigError(
                "openai-compatible provider requires endpoint + model"
            )
        kwargs = {
            "endpoint": cfg.endpoint,
            "model": cfg.model,
        }
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        if cfg.timeout_seconds is not None:
            kwargs["timeout_seconds"] = cfg.timeout_seconds
        if cfg.extra_headers:
            kwargs["extra_headers"] = cfg.extra_headers
        return make_openai_compatible_provider(**kwargs)

    raise ObserverConfigError(
        f"unknown provider {cfg.provider!r} (allowed: mechanical, ollama, openai-compatible)"
    )


def load_tier_provider(
    tier: int,
    *,
    config_path: Path | None = None,
) -> Provider:
    """One-call helper: read the tier config and return a Provider."""
    return provider_from_tier_config(load_tier_config(tier, config_path=config_path))
