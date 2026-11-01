"""Document ingestion and question answering business logic."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.core.config import Settings, get_settings
from src.ingestion.loader import DocumentLoader
from src.ingestion.splitter import DocumentSplitter
from src.rag.llm_client import LLMClient
from src.rag.prompt_builder import PromptBuilder
from src.rag.retriever import Retriever
from src.repositories.vector_repository import SearchHit, VectorRepository

NO_CONTEXT_ANSWER = "В загруженных документах нет ответа на этот вопрос."


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Summary of a processed document."""

    document_id: str
    file_name: str
    chunks: int


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Reference to a chunk used to build the answer."""

    file_name: str
    chunk_index: int | None
    chunk_id: str | None
    score: float
    page: int | None = None


@dataclass(frozen=True, slots=True)
class RAGAnswer:
    """Answer returned to the caller."""

    answer: str
    sources: list[SourceRef]
    model: str
    usage: dict[str, Any] | None = None


class RAGService:
    """Orchestrates ingestion and retrieval-augmented generation."""

    def __init__(
        self,
        *,
        loader: DocumentLoader,
        splitter: DocumentSplitter,
        vector_repository: VectorRepository,
        retriever: Retriever,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
    ) -> None:
        self._loader = loader
        self._splitter = splitter
        self._vectors = vector_repository
        self._retriever = retriever
        self._prompt_builder = prompt_builder
        self._llm = llm_client

    @classmethod
    def from_settings(
        cls,
        *,
        vector_repository: VectorRepository,
        llm_client: LLMClient,
        settings: Settings | None = None,
    ) -> "RAGService":
        settings = settings or get_settings()
        return cls(
            loader=DocumentLoader(),
            splitter=DocumentSplitter.from_settings(settings),
            vector_repository=vector_repository,
            retriever=Retriever.from_settings(vector_repository, settings),
            prompt_builder=PromptBuilder(),
            llm_client=llm_client,
        )

    async def ingest(
        self,
        file_path: str | Path,
        document_id: str | None = None,
        *,
        user_id: str,
    ) -> IngestResult:
        """Load, split and index a document owned by ``user_id``."""
        path = Path(file_path)
        documents = await asyncio.to_thread(self._loader.load, path)
        chunks = await asyncio.to_thread(self._splitter.split, documents)
        if not chunks:
            msg = f"Document produced no chunks: {path.name}"
            raise ValueError(msg)

        resolved_id = document_id or uuid4().hex
        await asyncio.to_thread(
            self._vectors.add_documents,
            chunks,
            document_id=resolved_id,
            user_id=user_id,
        )
        return IngestResult(document_id=resolved_id, file_name=path.name, chunks=len(chunks))

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        *,
        user_id: str,
    ) -> RAGAnswer:
        """Retrieve the caller's own chunks and answer strictly from them."""
        cleaned = question.strip()
        if not cleaned:
            msg = "Question must not be empty"
            raise ValueError(msg)

        hits = await asyncio.to_thread(
            self._retriever.retrieve,
            cleaned,
            top_k,
            user_id=user_id,
        )
        if not hits:
            return RAGAnswer(answer=NO_CONTEXT_ANSWER, sources=[], model=self._model_name)

        messages = self._prompt_builder.build(cleaned, hits)
        response = await self._llm.agenerate(messages)

        return RAGAnswer(
            answer=response.content,
            sources=self._to_sources(hits),
            model=response.model,
            usage=response.usage,
        )

    @property
    def _model_name(self) -> str:
        return getattr(self._llm, "model_name", "unknown")

    @staticmethod
    def _to_sources(hits: list[SearchHit]) -> list[SourceRef]:
        return [
            SourceRef(
                file_name=str(hit.metadata.get("file_name", "unknown")),
                chunk_index=hit.metadata.get("chunk_index"),
                chunk_id=hit.metadata.get("chunk_id"),
                score=hit.score,
                page=hit.metadata.get("page"),
            )
            for hit in hits
        ]
