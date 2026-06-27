"""``[relevance.semantic]`` config — backend selection + model ids.

Default ``backend = "none"`` keeps the zero-dependency BM25 path: no model
download, no surprise. ``local`` needs ``pip install engram[ml]``; ``remote``
lands in the design's §5 step 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_BACKENDS = ("none", "local", "remote")


@dataclass(frozen=True)
class SemanticConfig:
    backend: str = "none"
    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    # Reserved: the local fastembed backend pins via its own version (pyproject)
    # + the model name, so this is not plumbed to it. Kept for the remote
    # backend / future use.
    model_revision: str | None = None
    rerank_top_k: int = 20
    # remote backend (§5 step 5):
    embed_endpoint: str | None = None
    embed_api_model: str | None = None
    # repr=False: keys must never land in repr/logs/traceback locals.
    embed_api_key: str | None = field(default=None, repr=False)
    rerank_endpoint: str | None = None
    rerank_api_key: str | None = field(default=None, repr=False)


def _opt_str(raw: dict[str, Any], key: str) -> str | None:
    val = raw.get(key)
    return str(val) if val not in (None, "") else None


def parse_semantic_config(raw: dict[str, Any] | None) -> SemanticConfig:
    """Build a :class:`SemanticConfig` from a parsed ``[relevance.semantic]`` table."""
    if not raw:
        return SemanticConfig()

    backend = str(raw.get("backend", "none")).lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"[relevance.semantic] backend must be one of {VALID_BACKENDS}, got {backend!r}"
        )

    top_k = int(raw.get("rerank_top_k", 20))
    if top_k <= 0:
        raise ValueError(f"[relevance.semantic] rerank_top_k must be > 0, got {top_k}")

    return SemanticConfig(
        backend=backend,
        embed_model=str(raw.get("embed_model", "BAAI/bge-m3")),
        rerank_model=str(raw.get("rerank_model", "BAAI/bge-reranker-v2-m3")),
        model_revision=_opt_str(raw, "model_revision"),
        rerank_top_k=top_k,
        embed_endpoint=_opt_str(raw, "embed_endpoint"),
        embed_api_model=_opt_str(raw, "embed_api_model"),
        embed_api_key=_opt_str(raw, "embed_api_key"),
        rerank_endpoint=_opt_str(raw, "rerank_endpoint"),
        rerank_api_key=_opt_str(raw, "rerank_api_key"),
    )
