"""Embedder + Reranker interfaces for the relevance semantic layer.

Structural protocols, like the observer's ``Provider``: any object with the
right method satisfies them, so a fastembed local backend, a remote-API
backend, or a deterministic test stub are interchangeable. The Relevance Gate
consumes these; ``None`` means "no semantic signal — stay on BM25".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Map texts to dense vectors (same dimensionality for query and docs)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class Reranker(Protocol):
    """Score each doc's relevance to the query — higher is more relevant."""

    def rerank(self, query: str, docs: list[str]) -> list[float]: ...
