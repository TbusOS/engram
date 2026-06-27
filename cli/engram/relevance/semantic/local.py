"""fastembed (ONNX) local Embedder + Reranker — no torch.

fastembed is imported lazily inside ``__init__`` so this module imports fine
without the ``engram[ml]`` extra; only instantiating a backend needs the
library. fastembed downloads + caches the ONNX model from the HuggingFace hub
on first use (opt-in, by model name); inference is offline thereafter.

The fastembed calls follow its documented API; they are exercised end-to-end by
the benchmark job (a model-available environment), not the unit suite, which
drives the gate with deterministic stub backends.
"""

from __future__ import annotations

ML_HINT = "local semantic backend needs fastembed — `pip install engram[ml]`"


def _missing_extra(exc: ImportError) -> bool:
    """True only when fastembed itself is absent — not a transitive failure.

    A broken transitive dependency (e.g. onnxruntime on an unsupported Python)
    raises ImportError too; reporting that as "extra absent" would mislead, so
    surface the real cause instead.
    """
    return exc.name == "fastembed"


class LocalEmbedder:
    """Dense embeddings via fastembed ``TextEmbedding`` (default ``bge-m3``)."""

    def __init__(self, model: str) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - exercised when extra absent
            if not _missing_extra(exc):
                raise
            raise ImportError(ML_HINT) from exc
        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vec] for vec in self._model.embed(texts)]


class LocalReranker:
    """Cross-encoder reranking via fastembed ``TextCrossEncoder`` (``bge-reranker-v2-m3``)."""

    def __init__(self, model: str) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:  # pragma: no cover - exercised when extra absent
            if not _missing_extra(exc):
                raise
            raise ImportError(ML_HINT) from exc
        self._model = TextCrossEncoder(model_name=model)

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        return [float(score) for score in self._model.rerank(query, docs)]
