"""Vector store abstraction over ChromaDB.

The collection uses cosine distance, so ``1 - distance`` is the cosine
similarity between query and chunk.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings

from rag_local.errors import StoreError
from rag_local.logging import get_logger

if TYPE_CHECKING:
    from rag_local.embedder import Embedder

log = get_logger(__name__)


class VectorStore(Protocol):
    """Protocol for vector stores."""

    def add(
        self,
        texts: list[str],
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Add or replace documents."""
        ...

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Return the nearest documents with their cosine distance."""
        ...

    @property
    def count(self) -> int:
        """Number of stored documents."""
        ...


class ChromaVectorStore:
    """ChromaDB-backed vector store (persistent, cosine distance)."""

    def __init__(
        self,
        persist_dir: str = "./data/vectorstore",
        collection_name: str = "rental_policies",
        embedder: Embedder | None = None,
    ) -> None:
        """Open or create the persistent collection.

        A collection created before the switch to cosine distance keeps its old
        metric; delete the persist directory and re-ingest in that case.
        """
        self._persist_dir = str(Path(persist_dir).resolve())
        self._collection_name = collection_name

        log.info("store.opening", persist_dir=self._persist_dir, collection=collection_name)

        try:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=collection_name, metadata={"hnsw:space": "cosine"}
            )
        except Exception as exc:
            raise StoreError(f"Failed to open Chroma collection {collection_name} at {persist_dir}: {exc}") from exc

        if (self._collection.metadata or {}).get("hnsw:space") != "cosine":
            log.warning("store.not_cosine", collection=collection_name, metadata=self._collection.metadata)

        self._embedder = embedder

    @property
    def count(self) -> int:
        """Number of stored documents."""
        try:
            return int(self._collection.count())
        except Exception as exc:
            raise StoreError(f"Failed to count collection: {exc}") from exc

    def add(
        self,
        texts: list[str],
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Add documents, replacing any with the same IDs.

        Args:
            texts: Document text strings.
            embeddings: Pre-computed embeddings. If None and an embedder is set, computed automatically.
            metadatas: Per-document metadata dicts (non-empty, as Chroma requires).
            ids: Stable document IDs. Re-adding the same IDs updates instead of duplicating.
                Defaults to ``doc_<n>`` numbered after the current count.

        Raises:
            StoreError: If the inputs do not line up or the write fails.
        """
        if not texts:
            log.warning("store.add_empty")
            return

        if embeddings is None and self._embedder is not None:
            log.info("store.embedding", count=len(texts))
            embeddings = self._embedder.embed_many(texts)

        if embeddings is None:
            raise StoreError("Cannot add documents: no embeddings provided and no embedder configured")
        if len(texts) != len(embeddings):
            raise StoreError(f"Text count ({len(texts)}) does not match embedding count ({len(embeddings)})")

        if ids is None:
            start = self.count
            ids = [f"doc_{i}" for i in range(start, start + len(texts))]

        try:
            self._collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,  # type: ignore[arg-type]
                metadatas=metadatas,  # type: ignore[arg-type]
            )
        except Exception as exc:
            raise StoreError(f"Failed to add {len(texts)} documents to store: {exc}") from exc

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search for the nearest neighbours of a query embedding.

        Returns:
            Result dicts with keys id, document, metadata, distance (cosine distance, 0 = identical).

        Raises:
            StoreError: If the search fails.
        """
        if not query_embedding:
            raise StoreError("Cannot search with empty query embedding")

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],  # type: ignore[arg-type]
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise StoreError(f"Search failed: {exc}") from exc

        ids = results["ids"][0]
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        return [
            {
                "id": ids[i],
                "document": documents[i] if i < len(documents) else "",
                "metadata": dict(metadatas[i] or {}) if i < len(metadatas) else {},
                "distance": float(distances[i]) if i < len(distances) else 1.0,
            }
            for i in range(len(ids))
        ]

    def clear(self) -> None:
        """Delete all documents from the collection."""
        try:
            all_ids = self._collection.get()["ids"]
            if all_ids:
                self._collection.delete(ids=all_ids)
                log.info("store.cleared", count=len(all_ids))
        except Exception as exc:
            raise StoreError(f"Failed to clear collection: {exc}") from exc
