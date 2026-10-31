"""Split loaded documents into overlapping chunks."""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import Settings, get_settings


class DocumentSplitter:
    """Recursive character splitter tuned for Russian-language documents."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        if chunk_size <= 0:
            msg = "chunk_size must be positive"
            raise ValueError(msg)
        if not 0 <= chunk_overlap < chunk_size:
            msg = "chunk_overlap must be non-negative and smaller than chunk_size"
            raise ValueError(msg)

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
            add_start_index=True,
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "DocumentSplitter":
        settings = settings or get_settings()
        return cls(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def split(self, documents: list[Document]) -> list[Document]:
        """Split documents into chunks and number them sequentially."""
        chunks = self._splitter.split_documents(documents)
        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
        return chunks
