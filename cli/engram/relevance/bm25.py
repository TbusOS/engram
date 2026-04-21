"""Okapi-BM25 scorer + 32-term stop word list (T-42).

Per DESIGN §5.1 Stage 3 / §17:

- Stop words from the 32-term list are stripped from queries and
  documents before keyword extraction. The list is deliberately short
  and common-word-only so that technical terms like ``kernel``, ``mm``,
  ``k8s`` never leak into it.
- Keywords must be ≥3 characters long. Shorter tokens are almost always
  low-signal for ranking (``i``, ``x``, ``m3``) and inflate the
  document-frequency counters without helping retrieval.
- BM25 uses the Okapi parameterization with ``k1=1.5`` and ``b=0.75``,
  the MemPalace baseline. These are tunable but the defaults have
  shipped well in comparable systems.

This module supersedes the internal BM25 helper in
``engram.commands.memory``. That helper is preserved as a thin
compatibility re-export so existing tests and the M2 search subcommand
continue to work without churn. Once M4 lands the full Relevance Gate
(T-40), the search subcommand routes through the Gate instead.
"""

from __future__ import annotations

import math
import re
from collections import Counter

__all__ = [
    "MIN_TOKEN_LENGTH",
    "STOP_WORDS",
    "bm25_scores",
    "tokenize",
]


# The 32-term stop word list. DESIGN §17 mandates the count; the exact
# terms are chosen here to cover the highest-frequency English words
# that carry no topic signal, while deliberately avoiding any word that
# could appear as a technical term in a memory corpus (no "has", no
# "run", no "one"). Keep this list in lockstep with the test expectation.
STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "that",
        "you",
        "for",
        "are",
        "with",
        "this",
        "they",
        "from",
        "but",
        "not",
        "which",
        "their",
        "would",
        "there",
        "what",
        "about",
        "when",
        "your",
        "will",
        "can",
        "could",
        "should",
        "may",
        "might",
        "into",
        "onto",
        "than",
        "then",
        "been",
        "being",
    }
)

MIN_TOKEN_LENGTH: int = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase → split on non-alphanumeric → drop stop words and short tokens."""
    if not text:
        return []
    raw = _TOKEN_RE.findall(text.lower())
    return [t for t in raw if len(t) >= MIN_TOKEN_LENGTH and t not in STOP_WORDS]


def bm25_scores(
    query: str,
    documents: list[tuple[str, str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    """Pure-Python Okapi-BM25. Returns ``[(doc_id, score)]`` sorted desc.

    Documents with a zero score (no query term matches) are dropped
    rather than appended with score=0. Callers therefore can't tell
    "scored 0" from "not scored at all" — which matches the Relevance
    Gate's intent of suppressing candidates that carry no signal for
    the current query.
    """
    q_tokens = tokenize(query)
    doc_tokens = [(did, tokenize(text)) for did, text in documents]
    n = len(doc_tokens)
    if n == 0 or not q_tokens:
        return []

    avg_dl = sum(len(t) for _, t in doc_tokens) / n
    df: Counter[str] = Counter()
    for _, toks in doc_tokens:
        for w in set(toks):
            df[w] += 1

    scored: list[tuple[str, float]] = []
    for did, toks in doc_tokens:
        tf = Counter(toks)
        dl = len(toks)
        score = 0.0
        for w in q_tokens:
            if w not in df:
                continue
            idf = math.log((n - df[w] + 0.5) / (df[w] + 0.5) + 1.0)
            f = tf.get(w, 0)
            denom = f + k1 * (1 - b + b * dl / avg_dl) if avg_dl else 1.0
            norm = f * (k1 + 1) / denom if denom else 0.0
            score += idf * norm
        if score > 0:
            scored.append((did, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
