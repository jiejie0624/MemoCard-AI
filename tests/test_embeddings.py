import unittest
from unittest.mock import patch

from backend.app.processing.embeddings import TextEmbedder


class FakeModel:
    def __init__(self) -> None:
        self.embed_inputs: list[list[str]] = []
        self.query_inputs: list[str] = []

    def embed(self, texts: list[str], batch_size: int | None = None):
        self.embed_inputs.append(texts)
        return iter([FakeVector([0.1, 0.2, 0.3])])

    def query_embed(self, query: str):
        self.query_inputs.append(query)
        return iter([FakeVector([0.1, 0.2, 0.3])])


class FakeVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class TextEmbedderTests(unittest.TestCase):
    def test_passages_and_queries_use_the_model_native_entry_points(self) -> None:
        model = FakeModel()
        embedder = TextEmbedder()
        with patch("backend.app.processing.embeddings._load_model", return_value=model):
            passage_vectors = embedder.embed_passages(["学习资料"])
            query_vector = embedder.embed_query("什么是间隔复习？")

        # The model applies its own query instruction, so neither side is prefixed here.
        self.assertEqual(model.embed_inputs, [["学习资料"]])
        self.assertEqual(model.query_inputs, ["什么是间隔复习？"])
        self.assertEqual(passage_vectors, [[0.1, 0.2, 0.3]])
        self.assertEqual(query_vector, [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
