"""Tests for the FAISS vector repository."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from langchain_core.documents import Document

from src.repositories.vector_repository import SearchHit, VectorIndexError, VectorRepository

KEYWORDS = ("кошк", "собак", "faiss", "вектор")


class KeywordEmbedder:
    """Deterministic bag-of-keywords embedder for retrieval tests."""

    def __init__(self, keywords: Sequence[str] = KEYWORDS) -> None:
        self._keywords = tuple(keywords)

    def _vector(self, text: str) -> np.ndarray:
        lowered = text.lower()
        return np.array([lowered.count(keyword) for keyword in self._keywords], dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        return np.vstack([self._vector(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


def make_documents() -> list[Document]:
    return [
        Document(page_content="Кошки любят спать", metadata={"chunk_index": 0}),
        Document(page_content="FAISS хранит векторы", metadata={"chunk_index": 1}),
    ]


@pytest.fixture
def repository(tmp_path: Path) -> VectorRepository:
    return VectorRepository(KeywordEmbedder(), tmp_path / "index")


def test_empty_store_returns_nothing(repository: VectorRepository) -> None:
    assert repository.count == 0
    assert repository.search("кошка") == []


def test_most_relevant_chunk_comes_first(repository: VectorRepository) -> None:
    repository.add_documents(make_documents())

    hits = repository.search("что известно про кошку")

    assert [hit.content for hit in hits] == ["Кошки любят спать", "FAISS хранит векторы"]
    assert isinstance(hits[0], SearchHit)
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(0.0)


def test_chunk_ids_and_metadata_are_stored(repository: VectorRepository) -> None:
    chunk_ids = repository.add_documents(make_documents(), document_id="doc-1")

    assert chunk_ids == ["doc-1:0", "doc-1:1"]
    assert repository.count == 2

    hits = repository.search("векторы")
    assert hits[0].metadata["chunk_id"] == "doc-1:1"
    assert hits[0].metadata["chunk_index"] == 1


def test_generated_chunk_ids_are_unique(repository: VectorRepository) -> None:
    first = repository.add_documents(make_documents())
    second = repository.add_documents(make_documents())

    assert len(set(first + second)) == 4


def test_top_k_limits_results(repository: VectorRepository) -> None:
    repository.add_documents(make_documents())

    hits = repository.search("кошка faiss", top_k=1)

    assert len(hits) == 1


def test_min_score_filters_results(repository: VectorRepository) -> None:
    repository.add_documents(make_documents())

    hits = repository.search("кошка", min_score=0.5)

    assert [hit.content for hit in hits] == ["Кошки любят спать"]


@pytest.mark.parametrize(("query", "top_k"), [("кошка", 0), ("", 3), ("   ", 3)])
def test_invalid_search_arguments_are_rejected(
    repository: VectorRepository,
    query: str,
    top_k: int,
) -> None:
    repository.add_documents(make_documents())

    with pytest.raises(ValueError):
        repository.search(query, top_k=top_k)


def test_store_is_persisted_and_reloaded(tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    repository = VectorRepository(KeywordEmbedder(), index_path)
    repository.add_documents(make_documents())

    reloaded = VectorRepository(KeywordEmbedder(), index_path)

    assert reloaded.count == 2
    assert reloaded.dimension == len(KEYWORDS)
    assert reloaded.search("faiss")[0].content == "FAISS хранит векторы"
    assert repository.index_file.is_file()
    assert repository.records_file.is_file()


def test_dimension_change_is_detected_on_search(tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    VectorRepository(KeywordEmbedder(), index_path).add_documents(make_documents())
    other = VectorRepository(KeywordEmbedder(("кошк", "собак", "faiss")), index_path)

    with pytest.raises(ValueError, match="dimension"):
        other.search("кошка")


def test_inconsistent_store_raises(tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    repository = VectorRepository(KeywordEmbedder(), index_path)
    repository.add_documents(make_documents())
    repository.records_file.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(VectorIndexError, match="corrupted"):
        VectorRepository(KeywordEmbedder(), index_path)


def test_reset_removes_everything(repository: VectorRepository) -> None:
    repository.add_documents(make_documents())

    repository.reset()

    assert repository.count == 0
    assert repository.dimension is None
    assert not repository.index_file.exists()
    assert not repository.records_file.exists()
    assert repository.search("кошка") == []
