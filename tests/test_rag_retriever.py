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
        self.calls: list[tuple[str, int, float | None, str | None]] = []

    def search(
        self,
        query: str,
        top_k: int = 4,
        *,
        min_score: float | None = None,
        user_id: str | None = None,
    ) -> list[SearchHit]:
        self.calls.append((query, top_k, min_score, user_id))
        return self._hits[:top_k]


def test_returns_matching_hits() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository)

    hits = retriever.retrieve("что едят кошки")

    assert hits == HITS
    assert repository.calls == [("что едят кошки", 4, None, None)]


def test_top_k_can_be_overridden() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository, default_top_k=5)

    hits = retriever.retrieve("кошки", top_k=1)

    assert len(hits) == 1
    assert repository.calls[0][1] == 1


def test_settings_configure_top_k_and_score_floor(
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings(retriever_top_k=2, retriever_min_score=0.35)
    repository = StubVectorRepository(HITS)

    retriever = Retriever.from_settings(repository, settings)
    retriever.retrieve("кошки")

    assert retriever.default_top_k == 2
    assert repository.calls[0] == ("кошки", 2, 0.35, None)


def test_user_id_is_forwarded_to_the_store() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository)

    retriever.retrieve("кошки", user_id="user-42")

    assert repository.calls[0][3] == "user-42"


def test_min_score_from_constructor_is_forwarded() -> None:
    repository = StubVectorRepository(HITS)
    retriever = Retriever(repository, min_score=0.5)

    retriever.retrieve("кошки")

    assert repository.calls[0][2] == 0.5


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
