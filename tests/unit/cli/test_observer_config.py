"""T-204 tests for engram.observer.config — TOML loader + provider build."""

from __future__ import annotations

from pathlib import Path

import pytest

from engram.observer.config import (
    ObserverConfigError,
    TierConfig,
    load_tier_config,
    load_tier_provider,
    provider_from_tier_config,
)
from engram.observer.providers import MECHANICAL_MARKER


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ----------------------------------------------------------------------
# Missing config / sections
# ----------------------------------------------------------------------


def test_missing_file_returns_mechanical(tmp_path: Path) -> None:
    cfg = load_tier_config(1, config_path=tmp_path / "missing.toml")
    assert cfg.is_mechanical


def test_empty_file_returns_mechanical(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(f, "")
    cfg = load_tier_config(1, config_path=f)
    assert cfg.is_mechanical


def test_other_tier_does_not_leak(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier2]
provider = "ollama"
endpoint = "http://localhost:11434"
model = "qwen2.5:32b"
""",
    )
    cfg1 = load_tier_config(1, config_path=f)
    assert cfg1.is_mechanical
    cfg2 = load_tier_config(2, config_path=f)
    assert cfg2.provider == "ollama"


# ----------------------------------------------------------------------
# Provider selection
# ----------------------------------------------------------------------


def test_ollama_section_parsed(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier1]
provider = "ollama"
endpoint = "http://localhost:11434"
model = "qwen2.5:7b"
timeout_seconds = 30

[observer.compactor.tier1.options]
temperature = 0.2
""",
    )
    cfg = load_tier_config(1, config_path=f)
    assert cfg.provider == "ollama"
    assert cfg.endpoint == "http://localhost:11434"
    assert cfg.model == "qwen2.5:7b"
    assert cfg.timeout_seconds == 30
    assert cfg.options == {"temperature": 0.2}


def test_openai_section_parsed(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier3]
provider = "openai-compatible"
endpoint = "https://api.deepseek.com/v1"
model = "deepseek-chat"
api_key = "literal-key"
timeout_seconds = 300
""",
    )
    cfg = load_tier_config(3, config_path=f)
    assert cfg.provider == "openai-compatible"
    assert cfg.api_key == "literal-key"
    assert cfg.timeout_seconds == 300


# ----------------------------------------------------------------------
# Env-ref expansion
# ----------------------------------------------------------------------


def test_api_key_env_dollar_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret123")
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier1]
provider = "openai-compatible"
endpoint = "http://x"
model = "m"
api_key = "$MY_KEY"
""",
    )
    cfg = load_tier_config(1, config_path=f)
    assert cfg.api_key == "secret123"


def test_api_key_env_braces_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret456")
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier1]
provider = "openai-compatible"
endpoint = "http://x"
model = "m"
api_key = "${MY_KEY}"
""",
    )
    cfg = load_tier_config(1, config_path=f)
    assert cfg.api_key == "secret456"


def test_api_key_env_unset_yields_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier1]
provider = "openai-compatible"
endpoint = "http://x"
model = "m"
api_key = "$MISSING_KEY"
""",
    )
    cfg = load_tier_config(1, config_path=f)
    assert cfg.api_key is None


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


def test_invalid_toml_raises(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(f, "not = [valid toml")
    with pytest.raises(ObserverConfigError):
        load_tier_config(1, config_path=f)


def test_unknown_provider_raises_on_build() -> None:
    cfg = TierConfig(provider="telepathy", endpoint="x", model="y")
    with pytest.raises(ObserverConfigError):
        provider_from_tier_config(cfg)


def test_ollama_missing_model_raises() -> None:
    cfg = TierConfig(provider="ollama", endpoint="http://x", model=None)
    with pytest.raises(ObserverConfigError):
        provider_from_tier_config(cfg)


def test_openai_missing_endpoint_raises() -> None:
    cfg = TierConfig(provider="openai-compatible", endpoint=None, model="m")
    with pytest.raises(ObserverConfigError):
        provider_from_tier_config(cfg)


# ----------------------------------------------------------------------
# load_tier_provider end-to-end
# ----------------------------------------------------------------------


def test_load_tier_provider_returns_mechanical_when_missing(tmp_path: Path) -> None:
    p = load_tier_provider(1, config_path=tmp_path / "missing.toml")
    assert p("anything") == MECHANICAL_MARKER


def test_load_tier_provider_with_section(tmp_path: Path) -> None:
    f = tmp_path / "config.toml"
    _write(
        f,
        """
[observer.compactor.tier1]
provider = "mechanical"
""",
    )
    p = load_tier_provider(1, config_path=f)
    assert p("anything") == MECHANICAL_MARKER
