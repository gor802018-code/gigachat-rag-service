"""Tests for the document splitter."""

from collections.abc import Callable

import pytest
from langchain_core.documents import Document

from src.core.config import Settings
from src.ingestion.splitter import DocumentSplitter

LONG_TEXT = " ".join(f"Предложение номер {index} про векторный поиск." for index in range(120))


def make_document(content: str = LONG_TEXT) -> Document:
    return Document(
        page_content=content,
        metadata={"source": "notes.txt", "file_name": "notes.txt"},
    )


def test_short_text_produces_single_chunk() -> None:
    splitter = DocumentSplitter(chunk_size=1000, chunk_overlap=200)

    chunks = splitter.split([make_document("Короткий текст.")])

    assert len(chunks) == 1
    assert chunks[0].page_content == "Короткий текст."
    assert chunks[0].metadata["chunk_index"] == 0


def test_long_text_produces_multiple_chunks_within_size() -> None:
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=50)

    chunks = splitter.split([make_document()])

    assert len(chunks) > 1
    assert all(len(chunk.page_content) <= 200 for chunk in chunks)
    assert chunks[0].page_content.startswith("Предложение номер 0")


def test_chunks_overlap() -> None:
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=50)

    chunks = splitter.split([make_document()])

    assert chunks[0].page_content[-20:] in chunks[1].page_content


def test_chunk_indices_are_sequential_and_metadata_preserved() -> None:
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=50)

    chunks = splitter.split([make_document(), make_document()])

    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.metadata["source"] == "notes.txt" for chunk in chunks)
    assert all("start_index" in chunk.metadata for chunk in chunks)


def test_empty_document_list_produces_no_chunks() -> None:
    assert DocumentSplitter().split([]) == []


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (100, 100), (100, 150), (100, -1)],
)
def test_invalid_configuration_is_rejected(chunk_size: int, chunk_overlap: int) -> None:
    with pytest.raises(ValueError, match="chunk_"):
        DocumentSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def test_from_settings_uses_application_config(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(chunk_size=300, chunk_overlap=30)

    splitter = DocumentSplitter.from_settings(settings)

    assert splitter.chunk_size == 300
    assert splitter.chunk_overlap == 30
