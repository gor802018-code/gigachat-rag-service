"""Semantic retrieval over the vector store."""

from src.core.config import Settings, get_settings
from src.repositories.vector_repository import SearchHit, VectorRepository


class Retriever:
    """Thin, testable wrapper around ``VectorRepository.search``."""

    def __init__(
        self,
        vector_repository: VectorRepository,
        *,
        default_top_k: int = 4,
        min_score: float | None = None,
    ) -> None:
        if default_top_k <= 0:
            msg = "default_top_k must be positive"
            raise ValueError(msg)

        self._repository = vector_repository
        self._default_top_k = default_top_k
        self._min_score = min_score

    @classmethod
    def from_settings(
        cls,
        vector_repository: VectorRepository,
        settings: Settings | None = None,
    ) -> "Retriever":
        settings = settings or get_settings()
        return cls(
            vector_repository,
            default_top_k=settings.retriever_top_k,
            min_score=settings.retriever_min_score,
        )

    @property
    def default_top_k(self) -> int:
        return self._default_top_k

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        *,
        user_id: str | None = None,
    ) -> list[SearchHit]:
        """Return the most relevant chunks for a question.

        ``user_id`` scopes the search to the caller's own documents.
        """
        cleaned = query.strip()
        if not cleaned:
            msg = "Query must not be empty"
            raise ValueError(msg)

        limit = self._default_top_k if top_k is None else top_k
        if limit <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)

        return self._repository.search(
            cleaned,
            top_k=limit,
            min_score=self._min_score,
            user_id=user_id,
        )
