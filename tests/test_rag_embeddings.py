"""Tests for the sentence-transformers embedder."""

from typing import ClassVar
from unittest.mock import patch

import numpy as np
import pytest

from src.core.config import Settings
from src.rag.embeddings import Embedder, SentenceTransformerEmbedder

DIMENSION = 3


class FakeSentenceTransformer:
    """Stands in for a real model without downloading weights."""

    instances: ClassVar[list["FakeSentenceTransformer"]] = []

    def __init__(self, model_name: str, device: str | None = None) -> None:
        self.model_name = model_name
        self.device = device
        self.calls: list[int] = []
        self.encoded_texts: list[list[str]] = []
        FakeSentenceTransformer.instances.append(self)

    def get_sentence_embedding_dimension(self) -> int:
        return DIMENSION

    def encode(self, texts: list[str], **_: object) -> np.ndarray:
        self.calls.append(len(texts))
        self.encoded_texts.append(list(texts))
        return np.array([[float(len(text)), 1.0, 0.5] for text in texts], dtype=np.float32)


@pytest.fixture(autouse=True)
def reset_fake_model() -> None:
    FakeSentenceTransformer.instances.clear()


def test_model_is_not_loaded_on_construction() -> None:
    embedder = SentenceTransformerEmbedder("fake-model")

    assert embedder.is_loaded is False


def test_model_is_loaded_lazily_and_only_once() -> None:
    with patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer):
        embedder = SentenceTransformerEmbedder("fake-model")
        embedder.embed_documents(["первый", "второй"])
        embedder.embed_query("третий")

    assert embedder.is_loaded is True
    assert len(FakeSentenceTransformer.instances) == 1
    assert FakeSentenceTransformer.instances[0].calls == [2, 1]


def test_embedding_shapes_and_dtype() -> None:
    with patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer):
        embedder = SentenceTransformerEmbedder("fake-model")

        matrix = embedder.embed_documents(["a", "bb"])
        vector = embedder.embed_query("ccc")

    assert matrix.shape == (2, DIMENSION)
    assert matrix.dtype == np.float32
    assert vector.shape == (DIMENSION,)
    assert vector.dtype == np.float32


def test_empty_input_returns_empty_matrix() -> None:
    with patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer):
        embedder = SentenceTransformerEmbedder("fake-model")

        matrix = embedder.embed_documents([])

    assert matrix.size == 0
    assert embedder.is_loaded is False


def test_blank_query_is_rejected() -> None:
    with patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer):
        embedder = SentenceTransformerEmbedder("fake-model")

        with pytest.raises(ValueError, match="must not be empty"):
            embedder.embed_query("   ")


@pytest.mark.parametrize(("model_name", "batch_size"), [("", 32), ("model", 0)])
def test_invalid_parameters_are_rejected(model_name: str, batch_size: int) -> None:
    with pytest.raises(ValueError):
        SentenceTransformerEmbedder(model_name, batch_size=batch_size)


def test_from_settings_uses_configured_model(make_settings: "Settings") -> None:
    settings = make_settings(embedding_model_name="custom/model")

    embedder = SentenceTransformerEmbedder.from_settings(settings)

    assert embedder.model_name == "custom/model"
    assert embedder.query_prefix == "query: "
    assert embedder.passage_prefix == "passage: "


def test_prefixes_are_applied_to_passages_and_queries() -> None:
    with patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer):
        embedder = SentenceTransformerEmbedder(
            "fake-model",
            query_prefix="query: ",
            passage_prefix="passage: ",
        )
        embedder.embed_documents(["договор поставки"])
        embedder.embed_query("какой срок оплаты")

    assert FakeSentenceTransformer.instances[0].encoded_texts == [
        ["passage: договор поставки"],
        ["query: какой срок оплаты"],
    ]


def test_embedder_protocol_is_implemented() -> None:
    assert isinstance(SentenceTransformerEmbedder("fake-model"), Embedder)
