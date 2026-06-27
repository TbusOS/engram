"""Retrieval benchmark harness.

Measures the Relevance Gate against a labeled gold-set (query -> relevant
asset ids) so retrieval quality is a number, not a vibe — the foundation of
the only-improve ratchet (see
``docs/superpowers/specs/2026-06-27-retrieval-quality-design.md`` §4.3).

Pure stdlib: :mod:`~engram.benchmark.metrics` has no engram dependency;
:mod:`~engram.benchmark.runner` drives the gate over a fixture store.
"""

from __future__ import annotations

from engram.benchmark.metrics import mrr_at_k, ndcg_at_k, recall_at_k

__all__ = ["mrr_at_k", "ndcg_at_k", "recall_at_k"]
