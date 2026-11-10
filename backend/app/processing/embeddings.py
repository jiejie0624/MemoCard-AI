"""Local, multilingual embeddings used by the PostgreSQL vector index."""

from __future__ import annotations

from functools import lru_cache


MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 8


class TextEmbedder:
    """Generate E5 passage embeddings without sending document text to an API."""

    def embed_passages(self, passages: list[str]) -> list[list[float]]:
        if not passages:
            return []
        model = _load_model()
        # E5 uses separate prefixes so document and query vectors share a space.
        return [
            vector.tolist()
            for vector in model.embed(
                [f"passage: {text}" for text in passages],
                batch_size=EMBEDDING_BATCH_SIZE,
            )
        ]

    def embed_query(self, query: str) -> list[float]:
        model = _load_model()
        return next(model.embed([f"query: {query}"])).tolist()


@lru_cache(maxsize=1)
def _load_model():
    # FastEmbed does not bundle this multilingual model, so register the pinned
    # model metadata explicitly and let its cache manage the ONNX download.
    from fastembed import TextEmbedding as FastTextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    FastTextEmbedding.add_custom_model(
        model=MODEL_NAME,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=MODEL_NAME),
        dim=EMBEDDING_DIMENSIONS,
        model_file="onnx/model.onnx",
    )
    # Limit ONNX Runtime worker threads on Render's small free instances.
    return FastTextEmbedding(model_name=MODEL_NAME, threads=1)
