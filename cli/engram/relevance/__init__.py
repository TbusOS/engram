"""engram Relevance Gate (DESIGN §5.1).

The Relevance Gate is the Layer 3 "Intelligence" component that turns a
user task description into a ranked, token-budgeted context pack. Its
full 7-stage pipeline (prefilter → scope filter → BM25 → vector recall →
temporal boost → enforcement weight → budget pack) lands across T-40~T-45.

This module is intentionally empty — the sub-modules ``bm25``, ``temporal``,
``embedder``, and ``gate`` carry the implementation.
"""
