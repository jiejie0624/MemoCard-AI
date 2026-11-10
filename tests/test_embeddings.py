import unittest
from unittest.mock import patch

from backend.app.processing.embeddings import TextEmbedder


class FakeModel:
    def __init__(self) -> None:
        self.inputs: list[list[str]] = []

    def embed(self, texts: list[str], batch_size: int | None = None):
        self.inputs.append(texts)
        return iter([FakeVector([0.1, 0.2, 0.3])])


class FakeVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class TextEmbedderTests(unittest.TestCase):
    def test_passages_and_queries_use_e5_prefixes(self) -> None:
        model = FakeModel()
        embedder = TextEmbedder()
        with patch("backend.app.processing.embeddings._load_model", return_value=model):
            passage_vectors = embedder.embed_passages(["学习资料"])
            query_vector = embedder.embed_query("什么是间隔复习？")

        self.assertEqual(model.inputs, [["passage: 学习资料"], ["query: 什么是间隔复习？"]])
        self.assertEqual(passage_vectors, [[0.1, 0.2, 0.3]])
        self.assertEqual(query_vector, [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
