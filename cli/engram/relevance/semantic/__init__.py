"""Pluggable semantic layer for the Relevance Gate.

``Embedder`` / ``Reranker`` interfaces (:mod:`~engram.relevance.semantic.base`),
config (:mod:`~engram.relevance.semantic.config`), and a factory
(:mod:`~engram.relevance.semantic.factory`) that returns the configured backend
or ``None`` for BM25-only. The local fastembed backend
(:mod:`~engram.relevance.semantic.local`) is opt-in via the ``engram[ml]`` extra.

See ``docs/superpowers/specs/2026-06-27-retrieval-quality-design.md`` §4.1.
"""

from __future__ import annotations

from engram.relevance.semantic.base import Embedder, Reranker
from engram.relevance.semantic.config import SemanticConfig, parse_semantic_config
from engram.relevance.semantic.factory import build_embedder, build_reranker

__all__ = [
    "Embedder",
    "Reranker",
    "SemanticConfig",
    "build_embedder",
    "build_reranker",
    "parse_semantic_config",
]
