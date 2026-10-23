"""Vector store abstraction over ChromaDB.

Provides a uniform interface for creating, persisting, and querying
the Chroma vector store used by the RAG pipeline.
"""

from __future__ import annotations

from rag_local.logging import get_logger
from pathlib import Path
from typing import Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings

from rag_local.embedder import Embedder
from rag_local.errors import StoreError

log = get_logger(__name__)


class VectorStore(Protocol):
    """Protocol for vector stores."""

    def add(self, texts: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None: ...

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]: ...

    @property
    def count(self) -> int: ...


class ChromaVectorStore:
    """ChromaDB-backed vector store.

    Creates or opens a persistent Chroma collection for storing and
    retrieving document embeddings.
    """

    def __init__(
        self,
        persist_dir: str = "./data/vectorstore",
        collection_name: str = "rental_policies",
        embedder: Embedder | None = None,
    ) -> None:
        self._persist_dir = str(Path(persist_dir).resolve())
        self._collection_name = collection_name

        log.info("store.opening", persist_dir=self._persist_dir, collection=collection_name)

        try:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise StoreError(f"Failed to create Chroma client at {persist_dir}: {exc}") from exc

        try:
            self._collection = self._client.get_or_create_collection(name=collection_name)
        except Exception as exc:
            raise StoreError(f"Failed to get or create collection {collection_name}: {exc}") from exc

        self._embedder = embedder

    @property
    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception as exc:
            raise StoreError(f"Failed to count collection: {exc}") from exc

    def add(self, texts: list[str], embeddings: list[list[float]] | None = None, metadatas: list[dict] | None = None) -> None:
        """Add documents to the store.

        Args:
            texts: Document text strings.
            embeddings: Pre-computed embeddings. If None and embedder is set, computed automatically.
            metadatas: Per-document metadata dicts.

        Raises:
            StoreError: If the add operation fails.
        """
        if not texts:
            log.warning("add called with empty texts list — nothing to do")
            return

        if embeddings is None and self._embedder is not None:
            log.info("store.embedding", count=len(texts))
            embeddings = self._embedder.embed_many(texts)

        if embeddings is None:
            raise StoreError("Cannot add documents: no embeddings provided and no embedder configured")
        if len(texts) != len(embeddings):
            raise StoreError(f"Text count ({len(texts)}) does not match embedding count ({len(embeddings)})")

        if metadatas is None:
            metadatas = [{}] * len(texts)

        ids = [f"doc_{i}" for i in range(self.count, self.count + len(texts))]

        try:
            self._collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise StoreError(f"Failed to add {len(texts)} documents to store: {exc}") from exc

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """Search the store for the nearest neighbors of a query embedding.

        Args:
            query_embedding: The embedding vector to query with.
            top_k: Number of results to return.

        Returns:
            List of result dicts with keys: id, document, metadata, distance.

        Raises:
            StoreError: If the search operation fails.
        """
        if not query_embedding:
            raise StoreError("Cannot search with empty query embedding")

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise StoreError(f"Search failed: {exc}") from exc

        return [
            {
                "id": results["ids"][0][i] if results["ids"] else None,
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
            }
            for i in range(len(results["ids"][0]))
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