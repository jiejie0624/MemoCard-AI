"""Local, multilingual embeddings used by the PostgreSQL vector index."""

from __future__ import annotations

from functools import lru_cache


MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 8
# The repository publishes several ONNX graphs for the same weights. The fp32 graph
# (448 MB) and the ORT-optimised fp32 graph (224 MB) both exhausted a 512 MB hosting
# instance: ONNX Runtime needs roughly double the weight file on top of the graph and
# the tokenizer. The int8 graph is 113 MB and yields the same 384-dimension vectors,
# so stored vectors and the retrieval code are unaffected by the choice.
MODEL_FILE = "onnx/model_qint8_avx512_vnni.onnx"


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
        model_file=MODEL_FILE,
    )
    # Two memory controls for a 512 MB instance: one worker thread keeps the runtime's
    # thread-local buffers small, and disabling the CPU memory arena stops ONNX Runtime
    # from reserving a large block up front that is never actually needed here.
    return FastTextEmbedding(model_name=MODEL_NAME, threads=1, enable_cpu_mem_arena=False)
