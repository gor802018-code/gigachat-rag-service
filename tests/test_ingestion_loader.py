"""Tests for the document loader."""

import zipfile
from pathlib import Path

import pytest
from langchain_core.documents import Document

from src.ingestion.loader import (
    SUPPORTED_EXTENSIONS,
    DocumentLoader,
    DocumentLoadError,
    UnsupportedFileTypeError,
)

TEXT_CONTENT = "Первый абзац про RAG.\n\nВторой абзац про FAISS."

MINIMAL_DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Договор поставки</w:t></w:r></w:p>
    <w:p><w:r><w:t>Срок оплаты 30 дней.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""


@pytest.fixture
def text_file(tmp_path: Path) -> Path:
    path = tmp_path / "notes.txt"
    path.write_text(TEXT_CONTENT, encoding="utf-8")
    return path


def test_supported_extensions_cover_declared_types() -> None:
    assert DocumentLoader().supported_extensions == SUPPORTED_EXTENSIONS
    assert {".txt", ".md", ".pdf", ".docx"} <= SUPPORTED_EXTENSIONS


def test_loads_txt_file_with_metadata(text_file: Path) -> None:
    documents = DocumentLoader().load(text_file)

    assert len(documents) == 1
    document = documents[0]
    assert isinstance(document, Document)
    assert "про RAG" in document.page_content
    assert document.metadata["file_name"] == "notes.txt"
    assert document.metadata["extension"] == ".txt"
    assert document.metadata["file_size_bytes"] == text_file.stat().st_size
    assert document.metadata["source"].endswith("notes.txt")


def test_loads_markdown_file(tmp_path: Path) -> None:
    path = tmp_path / "readme.md"
    path.write_text("# Заголовок\n\nТекст документа.", encoding="utf-8")

    documents = DocumentLoader().load(path)

    assert documents[0].metadata["extension"] == ".md"


def test_loads_cp1251_file_without_mojibake(tmp_path: Path) -> None:
    path = tmp_path / "legacy.txt"
    path.write_bytes("Договор аренды помещения".encode("cp1251"))

    documents = DocumentLoader().load(path)

    assert documents[0].page_content == "Договор аренды помещения"


def test_utf8_bom_is_stripped(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes("\ufeffТекст с BOM".encode("utf-8"))

    documents = DocumentLoader().load(path)

    assert documents[0].page_content.startswith("Текст с BOM")


def test_loads_docx_file(tmp_path: Path) -> None:
    path = tmp_path / "contract.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", MINIMAL_DOCX_XML)

    documents = DocumentLoader().load(path)

    content = " ".join(document.page_content for document in documents)
    assert "Договор поставки" in content
    assert "Срок оплаты 30 дней." in content


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DocumentLoader().load(tmp_path / "missing.txt")


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "table.xlsx"
    path.write_bytes(b"not a document")

    with pytest.raises(UnsupportedFileTypeError, match="Unsupported file type"):
        DocumentLoader().load(path)


def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n  ", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="No extractable text"):
        DocumentLoader().load(path)


def test_whitespace_only_documents_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "mixed.txt"
    path.write_text("placeholder", encoding="utf-8")

    class StubLoader:
        def __init__(self, file_path: str) -> None:
            self.file_path = file_path

        def load(self) -> list[Document]:
            return [
                Document(page_content="   \n "),
                Document(page_content="Полезный текст"),
            ]

    documents = DocumentLoader(loaders={".txt": StubLoader}).load(path)

    assert [document.page_content for document in documents] == ["Полезный текст"]
    assert documents[0].metadata["file_name"] == "mixed.txt"
