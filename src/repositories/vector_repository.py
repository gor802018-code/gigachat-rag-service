"""FAISS-backed vector storage with on-disk persistence."""

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import faiss
import numpy as np
from langchain_core.documents import Document

from src.rag.embeddings import Embedder

INDEX_FILE_NAME = "index.faiss"
RECORDS_FILE_NAME = "records.json"
DEFAULT_TOP_K = 4


class VectorIndexError(RuntimeError):
    """Raised when the persisted index and its records are inconsistent."""


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single retrieval result."""

    content: str
    metadata: dict[str, Any]
    score: float


class VectorRepository:
    """Stores chunk embeddings in FAISS (cosine similarity) and keeps metadata.

    Vectors are L2-normalised before insertion, so the inner-product index
    returns cosine similarity in ``[-1, 1]``. Records are persisted next to the
    index in a JSON sidecar, which keeps the two files in sync.
    """

    def __init__(self, embedder: Embedder, index_path: str | Path) -> None:
        self._embedder = embedder
        self._index_path = Path(index_path)
        self._index: faiss.Index | None = None
        self._records: list[dict[str, Any]] = []
        self._lock = Lock()
        self._load()

    @property
    def index_file(self) -> Path:
        return self._index_path / INDEX_FILE_NAME

    @property
    def records_file(self) -> Path:
        return self._index_path / RECORDS_FILE_NAME

    @property
    def count(self) -> int:
        return len(self._records)

    @property
    def dimension(self) -> int | None:
        return None if self._index is None else int(self._index.d)

    def add_documents(
        self,
        documents: list[Document],
        *,
        document_id: str | None = None,
        user_id: str | None = None,
    ) -> list[str]:
        """Embed, normalise and store chunks. Returns the generated chunk ids."""
        if not documents:
            return []

        contents = [document.page_content for document in documents]
        vectors = self._prepare_vectors(self._embedder.embed_documents(contents))

        chunk_ids: list[str] = []
        with self._lock:
            self._ensure_index(vectors.shape[1])
            assert self._index is not None
            self._index.add(vectors)

            for offset, document in enumerate(documents):
                chunk_id = (
                    f"{document_id}:{document.metadata.get('chunk_index', offset)}"
                    if document_id
                    else uuid4().hex
                )
                metadata = {**document.metadata, "chunk_id": chunk_id}
                self._records.append(
                    {
                        "id": chunk_id,
                        "content": document.page_content,
                        "metadata": metadata,
                        "user_id": user_id,
                    }
                )
                chunk_ids.append(chunk_id)

        self.save()
        return chunk_ids

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        *,
        min_score: float | None = None,
        user_id: str | None = None,
    ) -> list[SearchHit]:
        """Return the ``top_k`` most similar chunks for ``query``.

        When ``user_id`` is provided only chunks that belong to that user are
        returned. ``IndexFlatIP`` scans every vector anyway, so the index is
        queried for the full result set and filtered afterwards; a filtered
        approximate index (pgvector/Qdrant) would push this down to the store.
        """
        if top_k <= 0:
            msg = "top_k must be positive"
            raise ValueError(msg)
        if not query.strip():
            msg = "Query must not be empty"
            raise ValueError(msg)

        # Embedding is CPU-heavy; keep it outside the lock so reads and writes
        # do not block each other.
        vector = self._prepare_vectors(np.atleast_2d(self._embedder.embed_query(query)))

        with self._lock:
            if self._index is None or not self._records:
                return []
            if vector.shape[1] != self._index.d:
                msg = (
                    f"Query embedding has dimension {vector.shape[1]}, "
                    f"index expects {self._index.d}"
                )
                raise ValueError(msg)

            fetch_k = len(self._records) if user_id is not None else min(top_k, len(self._records))
            scores, indices = self._index.search(vector, fetch_k)

            hits: list[SearchHit] = []
            for score, index in zip(scores[0], indices[0], strict=True):
                if index < 0:
                    continue
                record = self._records[int(index)]
                if user_id is not None and record.get("user_id") != user_id:
                    continue
                if min_score is not None and float(score) < min_score:
                    continue
                hits.append(
                    SearchHit(
                        content=record["content"],
                        metadata=dict(record["metadata"]),
                        score=float(score),
                    )
                )
                if len(hits) == top_k:
                    break
            return hits

    def save(self) -> None:
        """Atomically persist the index and its records."""
        with self._lock:
            if self._index is None:
                return
            self._index_path.mkdir(parents=True, exist_ok=True)
            self._atomic_write_bytes(
                self.index_file,
                faiss.serialize_index(self._index),
            )
            self._atomic_write_bytes(
                self.records_file,
                json.dumps(self._records, ensure_ascii=False).encode("utf-8"),
            )

    def reset(self) -> None:
        """Drop all vectors and remove persisted files."""
        with self._lock:
            self._index = None
            self._records = []
            for path in (self.index_file, self.records_file):
                path.unlink(missing_ok=True)

    def _load(self) -> None:
        if not self.index_file.is_file() or not self.records_file.is_file():
            return

        index = faiss.deserialize_index(np.fromfile(self.index_file, dtype=np.uint8))
        records = json.loads(self.records_file.read_text(encoding="utf-8"))
        if index.ntotal != len(records):
            msg = (
                f"Vector store is corrupted: {index.ntotal} vectors "
                f"vs {len(records)} records in {self._index_path}"
            )
            raise VectorIndexError(msg)

        self._index = index
        self._records = records

    def _ensure_index(self, dimension: int) -> None:
        if self._index is None:
            self._index = faiss.IndexFlatIP(dimension)
        elif self._index.d != dimension:
            msg = f"Embedding dimension changed: index expects {self._index.d}, got {dimension}"
            raise ValueError(msg)

    @staticmethod
    def _prepare_vectors(vectors: np.ndarray) -> np.ndarray:
        matrix = np.ascontiguousarray(np.atleast_2d(vectors), dtype=np.float32)
        if matrix.size == 0:
            return matrix
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return np.ascontiguousarray(matrix / norms, dtype=np.float32)

    @staticmethod
    def _atomic_write_bytes(path: Path, payload: bytes) -> None:
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_bytes(payload)
        tmp_path.replace(path)
