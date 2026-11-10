"""Local embeddings used by the PostgreSQL vector index.

The encoder is deliberately small and English-only. It keeps the 384-dimension
contract that the stored vectors already depend on, while fitting the 512 MB
instance: the multilingual E5 model could not be loaded there at any precision
(448 MB fp32, 224 MB optimised, 113 MB int8 all exhausted the instance).
"""

from __future__ import annotations

from functools import lru_cache


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 8


class TextEmbedder:
    """Generate embeddings without sending document text to an API."""

    def embed_passages(self, passages: list[str]) -> list[list[float]]:
        if not passages:
            return []
        model = _load_model()
        return [
            vector.tolist()
            for vector in model.embed(passages, batch_size=EMBEDDING_BATCH_SIZE)
        ]

    def embed_query(self, query: str) -> list[float]:
        model = _load_model()
        # query_embed applies the model's own retrieval instruction (BGE expects one
        # for questions but not for passages), so no prefix is added by hand here.
        return next(model.query_embed(query)).tolist()


@lru_cache(maxsize=1)
def _load_model():
    # The model ships in FastEmbed's own registry, so no custom registration is
    # needed. One worker thread and no CPU memory arena keep the runtime's peak
    # allocation low on a 512 MB host.
    from fastembed import TextEmbedding as FastTextEmbedding

    return FastTextEmbedding(model_name=MODEL_NAME, threads=1, enable_cpu_mem_arena=False)
