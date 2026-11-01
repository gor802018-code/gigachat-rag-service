"""Tests for the RAG service."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from src.rag.llm_client import LLMGenerationError, LLMResponse
from src.repositories.vector_repository import SearchHit
from src.services.rag_service import NO_CONTEXT_ANSWER, RAGService

USER_ID = "user-1"

CHUNKS = [
    Document(page_content="Срок оплаты — 30 дней.", metadata={"chunk_index": 0}),
    Document(page_content="Неустойка — 0,1% в день.", metadata={"chunk_index": 1}),
    Document(page_content="Предоплата 50%.", metadata={"chunk_index": 2}),
]

HITS = [
    SearchHit(
        content="Срок оплаты — 30 дней.",
        metadata={"file_name": "contract.pdf", "chunk_index": 0, "chunk_id": "doc:0"},
        score=0.92,
    ),
    SearchHit(
        content="Неустойка — 0,1% в день.",
        metadata={"file_name": "contract.pdf", "chunk_index": 1, "chunk_id": "doc:1"},
        score=0.71,
    ),
]


@pytest.fixture
def dependencies() -> dict[str, MagicMock]:
    loader = MagicMock()
    loader.load.return_value = [Document(page_content="Договор", metadata={})]

    splitter = MagicMock()
    splitter.split.return_value = CHUNKS

    vectors = MagicMock()
    vectors.add_documents.return_value = ["doc:0", "doc:1", "doc:2"]

    retriever = MagicMock()
    retriever.retrieve.return_value = HITS

    prompt_builder = MagicMock()
    prompt_builder.build.return_value = [
        SystemMessage(content="system"),
        HumanMessage(content="human"),
    ]

    llm = MagicMock()
    llm.model_name = "GigaChat"
    llm.agenerate = AsyncMock(
        return_value=LLMResponse(
            content="Оплата в течение 30 дней [1].",
            model="GigaChat",
            usage={"total_tokens": 42},
        )
    )

    return {
        "loader": loader,
        "splitter": splitter,
        "vector_repository": vectors,
        "retriever": retriever,
        "prompt_builder": prompt_builder,
        "llm_client": llm,
    }


@pytest.fixture
def service(dependencies: dict[str, MagicMock]) -> RAGService:
    return RAGService(**dependencies)


async def test_ingest_splits_and_stores_chunks(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = await service.ingest(
        Path("contracts/contract.pdf"),
        document_id="doc",
        user_id=USER_ID,
    )

    assert result.document_id == "doc"
    assert result.file_name == "contract.pdf"
    assert result.chunks == 3
    dependencies["vector_repository"].add_documents.assert_called_once_with(
        CHUNKS,
        document_id="doc",
        user_id=USER_ID,
    )


async def test_ingest_generates_document_id(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    result = await service.ingest(Path("contract.pdf"), user_id=USER_ID)

    assert len(result.document_id) == 32
    _, kwargs = dependencies["vector_repository"].add_documents.call_args
    assert kwargs["document_id"] == result.document_id
    assert kwargs["user_id"] == USER_ID


async def test_ingest_rejects_document_without_chunks(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["splitter"].split.return_value = []

    with pytest.raises(ValueError, match="no chunks"):
        await service.ingest(Path("empty.txt"), user_id=USER_ID)


async def test_ask_returns_answer_with_sources(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    answer = await service.ask("Какой срок оплаты?", user_id=USER_ID)

    assert answer.answer == "Оплата в течение 30 дней [1]."
    assert answer.model == "GigaChat"
    assert answer.usage == {"total_tokens": 42}
    assert [source.file_name for source in answer.sources] == [
        "contract.pdf",
        "contract.pdf",
    ]
    assert [source.chunk_id for source in answer.sources] == ["doc:0", "doc:1"]
    assert answer.sources[0].score == pytest.approx(0.92)
    assert answer.sources[0].page is None
    dependencies["retriever"].retrieve.assert_called_once_with(
        "Какой срок оплаты?",
        None,
        user_id=USER_ID,
    )
    dependencies["llm_client"].agenerate.assert_awaited_once()


async def test_ask_passes_top_k_and_user_to_retriever(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    await service.ask("Какой срок оплаты?", top_k=1, user_id=USER_ID)

    dependencies["retriever"].retrieve.assert_called_once_with(
        "Какой срок оплаты?",
        1,
        user_id=USER_ID,
    )


async def test_ask_without_context_skips_llm(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["retriever"].retrieve.return_value = []

    answer = await service.ask("Есть ли скидки?", user_id=USER_ID)

    assert answer.answer == NO_CONTEXT_ANSWER
    assert answer.sources == []
    dependencies["llm_client"].agenerate.assert_not_awaited()


async def test_blank_question_is_rejected(service: RAGService) -> None:
    with pytest.raises(ValueError, match="Question"):
        await service.ask("   ", user_id=USER_ID)


async def test_llm_failure_is_propagated(
    service: RAGService,
    dependencies: dict[str, MagicMock],
) -> None:
    dependencies["llm_client"].agenerate.side_effect = LLMGenerationError("quota exceeded")

    with pytest.raises(LLMGenerationError, match="quota"):
        await service.ask("Какой срок оплаты?", user_id=USER_ID)
