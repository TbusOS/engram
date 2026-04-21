"""T-42 tests: engram/relevance/bm25.py — Okapi-BM25 + 32-term stop word list.

Covers:

- SPEC §17 / DESIGN §5.1 "stop words from the 32-term list … keywords ≥3
  characters" token filter.
- BM25 correctness on tiny documents (k1=1.5, b=0.75 defaults).
- Public surface (`STOP_WORDS`, `MIN_TOKEN_LENGTH`, `tokenize`,
  `bm25_scores`) — these are the symbols the Relevance Gate (T-40) will
  import once the orchestrator lands.
"""

from __future__ import annotations

from engram.relevance.bm25 import (
    MIN_TOKEN_LENGTH,
    STOP_WORDS,
    bm25_scores,
    tokenize,
)


# ------------------------------------------------------------------
# Stop-word / tokenization contract
# ------------------------------------------------------------------


def test_stop_words_has_exactly_32_terms() -> None:
    assert len(STOP_WORDS) == 32


def test_stop_words_are_lowercase() -> None:
    for w in STOP_WORDS:
        assert w == w.lower()
        assert w.isalpha()


def test_stop_words_are_frozenset() -> None:
    """Immutable so downstream callers can't mutate it by accident."""
    assert isinstance(STOP_WORDS, frozenset)


def test_min_token_length_is_three() -> None:
    assert MIN_TOKEN_LENGTH == 3


def test_tokenize_lowercases() -> None:
    assert tokenize("Kubernetes Deployment") == ["kubernetes", "deployment"]


def test_tokenize_drops_stop_words() -> None:
    toks = tokenize("the kernel is a complex system")
    for banned in STOP_WORDS:
        assert banned not in toks


def test_tokenize_drops_tokens_shorter_than_min() -> None:
    assert tokenize("ab abc abcd") == ["abc", "abcd"]


def test_tokenize_splits_on_non_alphanumeric() -> None:
    assert tokenize("feedback/push-to-main") == ["feedback", "push", "main"]


def test_tokenize_handles_empty_string() -> None:
    assert tokenize("") == []


def test_tokenize_preserves_digits() -> None:
    assert "k8s" in tokenize("the k8s migration project")


# ------------------------------------------------------------------
# BM25 behaviour
# ------------------------------------------------------------------


def test_bm25_empty_inputs_return_empty() -> None:
    assert bm25_scores("kernel", []) == []
    assert bm25_scores("", [("a", "kernel")]) == []


def test_bm25_ranks_matching_doc_above_unrelated() -> None:
    docs = [
        ("kernel-asset", "kernel mm fs kernel patch"),
        ("unrelated", "bake cake sugar flour"),
    ]
    ranked = bm25_scores("kernel patch", docs)
    assert ranked[0][0] == "kernel-asset"
    # The unrelated doc must not appear since it has zero query-term matches.
    assert all(doc_id != "unrelated" for doc_id, _ in ranked)


def test_bm25_higher_term_frequency_raises_score() -> None:
    docs = [
        ("many", "kernel kernel kernel kernel kernel"),
        ("few", "kernel"),
    ]
    ranked = bm25_scores("kernel", docs)
    # Both match, but the many-mention asset must rank higher.
    assert ranked[0][0] == "many"


def test_bm25_stop_words_in_query_do_not_influence_score() -> None:
    """A query entirely composed of stop-words yields zero results."""
    docs = [("any", "the kernel and the module")]
    assert bm25_scores("the and", docs) == []


def test_bm25_ignores_case() -> None:
    docs = [("a", "Kubernetes Deployment Nginx")]
    ranked = bm25_scores("kubernetes", docs)
    assert ranked[0][0] == "a"


def test_bm25_output_sorted_descending() -> None:
    docs = [
        ("high", "kernel kernel kernel"),
        ("mid", "kernel also mm"),
        ("low", "kernel"),
    ]
    ranked = bm25_scores("kernel", docs)
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1]
