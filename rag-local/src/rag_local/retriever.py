"""Retrieval pipeline: embed query → search store → score results.

Includes a confidence guardrail: chunks whose cosine similarity to the
query is below ``min_relevance_score`` are dropped, and if none remain the
retriever raises NoRelevantDocumentsError so the pipeline can refuse to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rag_local.errors import NoRelevantDocumentsError, RetrievalError
from rag_local.logging import get_logger

if TYPE_CHECKING:
    from rag_local.embedder import Embedder
    from rag_local.store import VectorStore

log = get_logger(__name__)


class RetrievedChunk:
    """A single retrieved chunk with relevance information."""

    def __init__(self, text: str, metadata: dict[str, Any], score: float, distance: float) -> None:
        """Store the chunk, its cosine similarity (``score``) and cosine distance."""
        self.text = text
        self.metadata = metadata
        self.score = score
        self.distance = distance

    def __repr__(self) -> str:
        """Return a short summary with score and source."""
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
        """Configure the retriever.

        Args:
            embedder: Embeds the query (must match the embedder used at ingest).
            store: Vector store using cosine distance.
            top_k: Default number of chunks to fetch.
            min_relevance_score: Minimum cosine similarity (0-1) for a chunk to count.
        """
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
            NoRelevantDocumentsError: If no documents score above the threshold.
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
            distance = float(result.get("distance", 1.0))
            score = max(0.0, 1.0 - distance)  # cosine distance -> cosine similarity

            chunks.append(
                RetrievedChunk(
                    text=result.get("document", ""),
                    metadata=result.get("metadata", {}),
                    score=score,
                    distance=distance,
                )
            )

        chunks.sort(key=lambda c: c.score, reverse=True)
        relevant = [c for c in chunks if c.score >= self._min_relevance_score]

        if not relevant:
            best = chunks[0].score if chunks else 0.0
            log.warning("retriever.no_relevant", threshold=self._min_relevance_score, best_score=round(best, 3))
            if not chunks:
                raise NoRelevantDocumentsError("No documents found at all.")
            raise NoRelevantDocumentsError(
                f"No documents scored above relevance threshold {self._min_relevance_score:.2f}. Best score: {best:.3f}"
            )

        return relevant
