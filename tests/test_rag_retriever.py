"""Tests for the retriever."""

from collections.abc import Callable, Sequence

import pytest

from src.core.config import Settings
from src.rag.retriever import Retriever
from src.repositories.vector_repository import SearchHit

HITS = [
    SearchHit(content="Кошки любят спать", metadata={"file_name": "pets.txt"}, score=0.9),
    SearchHit(content="FAISS хранит векторы", metadata={"file_name": "rag.txt"}, score=0.4),
]


class StubVectorRepository:
    def __init__(self, hits: Sequence[SearchHit]) -> None:
        self._hits = list(hits)
        self.calls: list[tuple[str, int, float | None]] = []

    def search(
        self,
        query: str,
        top_k: int = 4,
        *,
        min_score: float | None = None,
    ) -> list[SearchHit]:
        self.calls.append((query, top_k, min_score))
        return self._hits[:top_k]


def test_returns_matching_hits() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository)

    hits = retriever.retrieve("что едят кошки")

    assert hits == HITS
    assert repository.calls == [("что едят кошки", 4, None)]


def test_top_k_can_be_overridden() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository, default_top_k=5)

    hits = retriever.retrieve("кошки", top_k=1)

    assert len(hits) == 1
    assert repository.calls[0][1] == 1


def test_default_top_k_comes_from_settings(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(retriever_top_k=2)

    retriever = Retriever.from_settings(StubVectorRepository(HITS), settings)

    assert retriever.default_top_k == 2
    retriever.retrieve("кошки")
    assert retriever._repository.calls[0][1] == 2


def test_blank_query_is_rejected() -> None:
    retriever = Retriever(StubVectorRepository(HITS))

    with pytest.raises(ValueError, match="must not be empty"):
        retriever.retrieve("   ")


def test_invalid_top_k_is_rejected() -> None:
    retriever = Retriever(StubVectorRepository(HITS))

    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("кошки", top_k=0)


def test_invalid_default_top_k_is_rejected() -> None:
    with pytest.raises(ValueError, match="default_top_k"):
        Retriever(StubVectorRepository(HITS), default_top_k=0)


def test_empty_store_returns_no_hits() -> None:
    assert Retriever(StubVectorRepository([])).retrieve("кошки") == []
