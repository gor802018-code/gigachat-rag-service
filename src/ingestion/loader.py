"""Load source documents from disk into LangChain ``Document`` objects."""

from pathlib import Path
from typing import Final

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_community.document_loaders.helpers import detect_file_encodings
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset({".txt", ".md", ".pdf", ".docx"})

TEXT_ENCODINGS: Final[tuple[str, ...]] = ("utf-8-sig", "utf-8")
FALLBACK_TEXT_ENCODING: Final[str] = "cp1251"

DEFAULT_LOADERS: Final[dict[str, type[BaseLoader]]] = {
    ".txt": TextLoader,
    ".md": TextLoader,
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
}


class UnsupportedFileTypeError(ValueError):
    """Raised when a file extension has no configured loader."""


class DocumentLoadError(RuntimeError):
    """Raised when a supported file cannot be read or contains no text."""


def detect_text_encoding(file_path: Path) -> str:
    """Decide how to decode a plain-text file.

    UTF-8 is tried first because statistical detectors regularly misread short
    Cyrillic UTF-8 files as windows-1251. Legacy encodings are detected only
    when UTF-8 decoding actually fails.
    """
    raw = file_path.read_bytes()
    for encoding in TEXT_ENCODINGS:
        try:
            raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding

    try:
        detected = detect_file_encodings(str(file_path))[0].encoding
    except Exception:
        detected = None
    return detected or FALLBACK_TEXT_ENCODING


class DocumentLoader:
    """Picks a LangChain document loader based on the file extension."""

    def __init__(self, loaders: dict[str, type[BaseLoader]] | None = None) -> None:
        self._loaders = dict(loaders or DEFAULT_LOADERS)

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset(self._loaders)

    def load(self, path: str | Path) -> list[Document]:
        """Load a single file and enrich its documents with source metadata."""
        file_path = Path(path)
        if not file_path.is_file():
            msg = f"Document not found: {file_path}"
            raise FileNotFoundError(msg)

        extension = file_path.suffix.lower()
        if extension not in self._loaders:
            msg = (
                f"Unsupported file type: '{extension or file_path.name}'. "
                f"Supported: {', '.join(sorted(self._loaders))}"
            )
            raise UnsupportedFileTypeError(msg)

        try:
            documents = self._build_loader(file_path, extension).load()
        except Exception as exc:
            msg = f"Failed to read {file_path.name}: {exc}"
            raise DocumentLoadError(msg) from exc

        documents = [document for document in documents if document.page_content.strip()]
        if not documents:
            msg = f"No extractable text in {file_path.name}"
            raise DocumentLoadError(msg)

        metadata = {
            "source": str(file_path),
            "file_name": file_path.name,
            "extension": extension,
            "file_size_bytes": file_path.stat().st_size,
        }
        for document in documents:
            document.metadata.update(metadata)

        return documents

    def _build_loader(self, file_path: Path, extension: str) -> BaseLoader:
        loader_cls = self._loaders[extension]
        if loader_cls is TextLoader:
            return TextLoader(str(file_path), encoding=detect_text_encoding(file_path))
        return loader_cls(str(file_path))
