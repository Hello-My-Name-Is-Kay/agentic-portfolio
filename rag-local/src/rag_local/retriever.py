"""Retrieval pipeline: embed query → search store → score results.

Includes confidence-based guardrails: if the top result's distance
exceeds a threshold, the pipeline returns empty to prevent hallucination.
"""

from __future__ import annotations

from rag_local.logging import get_logger
from typing import Protocol

from rag_local.embedder import Embedder
from rag_local.errors import NoRelevantDocuments, RetrievalError
from rag_local.store import VectorStore

log = get_logger(__name__)


class RetrievedChunk:
    """A single retrieved chunk with relevance information."""

    def __init__(self, text: str, metadata: dict, score: float, distance: float) -> None:
        self.text = text
        self.metadata = metadata
        self.score = score  # similarity score (1 - distance for cosine)
        self.distance = distance

    def __repr__(self) -> str:
        return f"RetrievedChunk(score={self.score:.3f}, source={self.metadata.get('source', 'unknown')})"


class Retriever:
    """Retrieves relevant document chunks for a given query.

    Embeds the query, searches the vector store, filters by relevance
    threshold, and returns scored results.
    """

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        top_k: int = 5,
        min_relevance_score: float = 0.35,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not 0.0 <= min_relevance_score <= 1.0:
            raise ValueError("min_relevance_score must be between 0 and 1")

        self._embedder = embedder
        self._store = store
        self._top_k = top_k
        self._min_relevance_score = min_relevance_score

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Retrieve chunks relevant to the query.

        Args:
            query: The user's question.
            top_k: Override the default top_k for this call.

        Returns:
            List of RetrievedChunk objects sorted by relevance (highest first).

        Raises:
            NoRelevantDocuments: If no documents score above the threshold.
            RetrievalError: If embedding or search fails.
        """
        if not query or not query.strip():
            raise RetrievalError("Cannot retrieve with empty query")

        k = top_k or self._top_k

        try:
            query_embedding = self._embedder.embed(query)
        except Exception as exc:
            raise RetrievalError(f"Failed to embed query: {exc}") from exc

        try:
            raw_results = self._store.search(query_embedding, top_k=k)
        except Exception as exc:
            raise RetrievalError(f"Failed to search vector store: {exc}") from exc

        chunks: list[RetrievedChunk] = []
        for result in raw_results:
            distance = result.get("distance", 1.0)
            # Chroma returns L2 distance by default; convert to similarity score
            # For cosine distance: score = 1 - distance (if using cosine, distance is in [0,2])
            # For L2: score = 1 / (1 + distance) -> simpler: use normalized score
            score = max(0.0, 1.0 - distance)

            chunks.append(
                RetrievedChunk(
                    text=result.get("document", ""),
                    metadata=result.get("metadata", {}),
                    score=score,
                    distance=distance,
                )
            )

        # Filter by relevance threshold
        relevant = [c for c in chunks if c.score >= self._min_relevance_score]

        if not relevant:
            log.warning(
                "No relevant documents above threshold %.2f (best score: %.3f)",
                self._min_relevance_score,
                chunks[0].score if chunks else 0.0,
            )
            raise NoRelevantDocuments(
                f"No documents scored above relevance threshold {self._min_relevance_score:.2f}. "
                f"Best score: {chunks[0].score:.3f}" if chunks else "No documents found at all."
            )

        return relevant