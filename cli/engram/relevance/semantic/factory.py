"""Build the configured Embedder / Reranker, or ``None`` for BM25-only.

``backend = none`` -> ``None`` (the gate stays on BM25). ``local`` lazy-imports
the fastembed backend (an actionable ImportError if the ``engram[ml]`` extra is
missing). ``remote`` lands in the design's §5 step 5.

Each call constructs a fresh backend — for ``local`` that is a model load
(hundreds of MB). The consumer (the Relevance Gate, step 3) MUST build once and
reuse the backend across queries; never call the factory per query.
"""

from __future__ import annotations

from engram.relevance.semantic.base import Embedder, Reranker
from engram.relevance.semantic.config import SemanticConfig

_REMOTE_PENDING = "remote semantic backend lands in the retrieval-quality spec §5 step 5"


def build_embedder(cfg: SemanticConfig) -> Embedder | None:
    if cfg.backend == "none":
        return None
    if cfg.backend == "local":
        from engram.relevance.semantic.local import LocalEmbedder

        return LocalEmbedder(cfg.embed_model)
    if cfg.backend == "remote":
        raise NotImplementedError(_REMOTE_PENDING)
    raise ValueError(f"unknown semantic backend: {cfg.backend!r}")


def build_reranker(cfg: SemanticConfig) -> Reranker | None:
    if cfg.backend == "none":
        return None
    if cfg.backend == "local":
        from engram.relevance.semantic.local import LocalReranker

        return LocalReranker(cfg.rerank_model)
    if cfg.backend == "remote":
        raise NotImplementedError(_REMOTE_PENDING)
    raise ValueError(f"unknown semantic backend: {cfg.backend!r}")
