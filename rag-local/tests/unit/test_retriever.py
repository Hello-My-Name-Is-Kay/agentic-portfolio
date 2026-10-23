"""Unit tests for the retriever module."""

from __future__ import annotations

import pytest

from rag_local.errors import NoRelevantDocuments, RetrievalError
from rag_local.retriever import Retriever


class FakeEmbedder:
    """A fake embedder that returns a fixed-dimension vector."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        return [0.1] * self._dim

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self._dim for _ in texts]


class FakeStore:
    """A fake vector store with controllable results."""

    def __init__(self) -> None:
        self._results: list[dict] = []
        self._count = 0

    def seed(self, results: list[dict]) -> None:
        self._results = results
        self._count = len(results)

    @property
    def count(self) -> int:
        return self._count

    def add(self, texts: list[str], embeddings: list[list[float]] | None = None, metadatas: list[dict] | None = None) -> None:
        self._count += len(texts)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        return self._results[:top_k]


class TestRetriever:
    """Tests for the Retriever class."""

    def test_retrieve_returns_chunks(self) -> None:
        embedder = FakeEmbedder()
        store = FakeStore()
        store.seed([
            {"id": "1", "document": "Fuel policy content.", "metadata": {"source": "fuel.md"}, "distance": 0.2},
            {"id": "2", "document": "Insurance policy content.", "metadata": {"source": "insurance.md"}, "distance": 0.3},
        ])

        retriever = Retriever(embedder, store, min_relevance_score=0.5)
        chunks = retriever.retrieve("What is the fuel policy?")
        assert len(chunks) == 2
        assert chunks[0].score >= 0.5  # distance 0.2 → score 0.8

    def test_no_relevant_docs_raises(self) -> None:
        embedder = FakeEmbedder()
        store = FakeStore()
        store.seed([
            {"id": "1", "document": "Irrelevant content.", "metadata": {"source": "other.md"}, "distance": 0.9},
        ])

        retriever = Retriever(embedder, store, min_relevance_score=0.5)
        with pytest.raises(NoRelevantDocuments):
            retriever.retrieve("What is the fuel policy?")

    def test_empty_query_raises(self) -> None:
        embedder = FakeEmbedder()
        store = FakeStore()
        retriever = Retriever(embedder, store)
        with pytest.raises(RetrievalError, match="empty query"):
            retriever.retrieve("")

    def test_top_k_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            Retriever(FakeEmbedder(), FakeStore(), top_k=0)

    def test_min_score_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            Retriever(FakeEmbedder(), FakeStore(), min_relevance_score=-0.1)
        with pytest.raises(ValueError):
            Retriever(FakeEmbedder(), FakeStore(), min_relevance_score=1.5)

    def test_empty_store_no_results(self) -> None:
        embedder = FakeEmbedder()
        store = FakeStore()
        store.seed([])

        retriever = Retriever(embedder, store, min_relevance_score=0.0)
        with pytest.raises(NoRelevantDocuments):
            retriever.retrieve("anything")