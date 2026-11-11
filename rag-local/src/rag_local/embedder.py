"""Embedding generation using sentence-transformers.

Wraps a local embedding model to produce vector representations of
text chunks for similarity search in Chroma.
"""

from __future__ import annotations

from typing import Protocol

from sentence_transformers import SentenceTransformer

from rag_local.errors import EmbeddingError
from rag_local.logging import get_logger

log = get_logger(__name__)


class Embedder(Protocol):
    """Protocol for text embedders."""

    @property
    def dimension(self) -> int:
        """Length of each embedding vector."""
        ...

    def embed(self, text: str) -> list[float]:
        """Embed one text."""
        ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed several texts."""
        ...


class SentenceTransformerEmbedder:
    """Embedder wrapping a sentence-transformers model. Vectors are L2-normalised."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", device: str = "cpu") -> None:
        """Load the model (downloaded from Hugging Face on first use, then cached)."""
        if not model_name:
            raise ValueError("model_name must be non-empty")

        log.info("embedder.loading", model_name=model_name, device=device)
        try:
            self._model = SentenceTransformer(model_name, device=device)
        except Exception as exc:
            raise EmbeddingError(f"Failed to load embedding model {model_name}: {exc}") from exc

    @property
    def dimension(self) -> int:
        """Length of each embedding vector."""
        return int(self._model.get_sentence_embedding_dimension() or 0)

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Input text.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If the model fails to produce embeddings.
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        try:
            vector: list[float] = self._model.encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()
            return vector
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed for text of length {len(text)}: {exc}") from exc

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings in batch.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors.

        Raises:
            EmbeddingError: If batch embedding fails.
        """
        if not texts:
            return []

        try:
            vectors: list[list[float]] = self._model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            ).tolist()
            return vectors
        except Exception as exc:
            raise EmbeddingError(f"Batch embedding failed for {len(texts)} texts: {exc}") from exc
