"""Tests for engram.relevance.semantic — interfaces, factory, config, fallback.

These exercise the engram-side contract without the model: backend=none, the
missing-``engram[ml]`` actionable error, the protocol contract via stubs, and
config parsing. The real fastembed backend is exercised by the benchmark job.
"""

from __future__ import annotations

import importlib.util

import pytest

from engram.relevance.semantic import (
    Embedder,
    Reranker,
    SemanticConfig,
    build_embedder,
    build_reranker,
    parse_semantic_config,
)


def test_backend_none_returns_none() -> None:
    cfg = SemanticConfig(backend="none")
    assert build_embedder(cfg) is None
    assert build_reranker(cfg) is None


def test_local_without_fastembed_raises_actionable() -> None:
    if importlib.util.find_spec("fastembed") is not None:
        pytest.skip("fastembed installed; this test asserts the missing-extra path")
    with pytest.raises(ImportError, match=r"engram\[ml\]"):
        build_embedder(SemanticConfig(backend="local"))
    with pytest.raises(ImportError, match=r"engram\[ml\]"):
        build_reranker(SemanticConfig(backend="local"))


def test_remote_not_yet_implemented() -> None:
    with pytest.raises(NotImplementedError):
        build_embedder(SemanticConfig(backend="remote"))
    with pytest.raises(NotImplementedError):
        build_reranker(SemanticConfig(backend="remote"))


def test_stub_backends_satisfy_protocols() -> None:
    class StubEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0, 0.0] for _ in texts]

    class StubReranker:
        def rerank(self, query: str, docs: list[str]) -> list[float]:
            return [0.0 for _ in docs]

    assert isinstance(StubEmbedder(), Embedder)
    assert isinstance(StubReranker(), Reranker)


def test_parse_defaults() -> None:
    assert parse_semantic_config(None) == SemanticConfig()
    assert parse_semantic_config({}).backend == "none"


def test_parse_local_overrides() -> None:
    cfg = parse_semantic_config(
        {"backend": "LOCAL", "rerank_top_k": 30, "embed_model": "x"}
    )
    assert cfg.backend == "local"  # lower-cased
    assert cfg.rerank_top_k == 30
    assert cfg.embed_model == "x"


def test_parse_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="backend must be one of"):
        parse_semantic_config({"backend": "bogus"})


def test_parse_rejects_nonpositive_top_k() -> None:
    with pytest.raises(ValueError, match="rerank_top_k"):
        parse_semantic_config({"backend": "local", "rerank_top_k": 0})


def test_api_keys_never_in_repr() -> None:
    cfg = SemanticConfig(
        backend="remote", embed_api_key="SECRET-EMBED", rerank_api_key="SECRET-RERANK"
    )
    rendered = repr(cfg)
    assert "SECRET-EMBED" not in rendered
    assert "SECRET-RERANK" not in rendered
