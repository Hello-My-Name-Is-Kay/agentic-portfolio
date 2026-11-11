"""Unit tests for the retriever module."""

from __future__ import annotations

from typing import Any

import pytest

from rag_local.errors import NoRelevantDocumentsError, RetrievalError
from rag_local.retriever import Retriever

from .fakes import HashEmbedder


class FakeStore:
    """A vector store returning canned results."""

    def __init__(self, results: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        self._results = results or []
        self._fail = fail

    @property
    def count(self) -> int:
        return len(self._results)

    def add(self, texts: list[str], embeddings: Any = None, metadatas: Any = None, ids: Any = None) -> None:
        raise NotImplementedError

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:  # noqa: ARG002
        if self._fail:
            raise RuntimeError("index offline")
        return self._results[:top_k]


def _result(source: str, distance: float) -> dict[str, Any]:
    return {"id": source, "document": f"{source} content", "metadata": {"source": source}, "distance": distance}


class TestRetriever:
    def test_scores_are_cosine_similarity_sorted_and_filtered(self) -> None:
        store = FakeStore([_result("insurance.md", 0.4), _result("fuel.md", 0.2), _result("other.md", 0.7)])
        chunks = Retriever(HashEmbedder(), store, min_relevance_score=0.5).retrieve("fuel?")
        assert [c.metadata["source"] for c in chunks] == ["fuel.md", "insurance.md"]
        assert [c.score for c in chunks] == pytest.approx([0.8, 0.6])
        assert "fuel.md" in repr(chunks[0])

    def test_top_k_override(self) -> None:
        store = FakeStore([_result("a.md", 0.1), _result("b.md", 0.2), _result("c.md", 0.3)])
        retriever = Retriever(HashEmbedder(), store, top_k=3, min_relevance_score=0.0)
        assert len(retriever.retrieve("q", top_k=1)) == 1
        assert len(retriever.retrieve("q")) == 3

    def test_no_relevant_docs_raises_with_best_score(self) -> None:
        store = FakeStore([_result("other.md", 0.9)])
        with pytest.raises(NoRelevantDocumentsError, match=r"Best score: 0\.100"):
            Retriever(HashEmbedder(), store, min_relevance_score=0.5).retrieve("What is the fuel policy?")

    def test_empty_store_raises(self) -> None:
        with pytest.raises(NoRelevantDocumentsError, match="No documents found"):
            Retriever(HashEmbedder(), FakeStore(), min_relevance_score=0.0).retrieve("anything")

    def test_empty_query_raises(self) -> None:
        with pytest.raises(RetrievalError, match="empty query"):
            Retriever(HashEmbedder(), FakeStore()).retrieve("")

    def test_store_failure_wrapped(self) -> None:
        with pytest.raises(RetrievalError, match="index offline"):
            Retriever(HashEmbedder(), FakeStore(fail=True)).retrieve("q")

    def test_embed_failure_wrapped(self) -> None:
        class Broken(HashEmbedder):
            def embed(self, _text: str) -> list[float]:
                raise RuntimeError("model gone")

        with pytest.raises(RetrievalError, match="model gone"):
            Retriever(Broken(), FakeStore()).retrieve("q")

    def test_top_k_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            Retriever(HashEmbedder(), FakeStore(), top_k=0)

    @pytest.mark.parametrize("score", [-0.1, 1.5])
    def test_min_score_out_of_range_raises(self, score: float) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            Retriever(HashEmbedder(), FakeStore(), min_relevance_score=score)
