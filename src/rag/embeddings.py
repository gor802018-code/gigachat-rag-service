"""Text embeddings based on sentence-transformers."""

from collections.abc import Sequence
from threading import Lock
from typing import Any, Protocol, runtime_checkable

import numpy as np

from src.core.config import Settings, get_settings


@runtime_checkable
class Embedder(Protocol):
    """Interface every embedding backend must implement."""

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """Return a ``(len(texts), dim)`` float32 matrix."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """Return a ``(dim,)`` float32 vector."""
        ...


class SentenceTransformerEmbedder:
    """Lazy wrapper around a sentence-transformers bi-encoder.

    The model is loaded on the first call so that importing the API module and
    running unit tests do not download weights or initialise torch.
    """

    def __init__(
        self,
        model_name: str,
        *,
        device: str | None = None,
        batch_size: int = 32,
        normalize: bool = True,
    ) -> None:
        if not model_name.strip():
            msg = "model_name must not be empty"
            raise ValueError(msg)
        if batch_size <= 0:
            msg = "batch_size must be positive"
            raise ValueError(msg)

        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.normalize = normalize
        self._model: Any = None
        self._lock = Lock()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SentenceTransformerEmbedder":
        settings = settings or get_settings()
        return cls(model_name=settings.embedding_model_name)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        return int(self._ensure_model().get_sentence_embedding_dimension())

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        model = self._ensure_model()
        vectors = model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        if not text.strip():
            msg = "Query text must not be empty"
            raise ValueError(msg)
        return self.embed_documents([text])[0]

    def _ensure_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model
