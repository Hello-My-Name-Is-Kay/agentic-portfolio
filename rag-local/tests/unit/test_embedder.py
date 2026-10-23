"""Unit tests for the embedding module."""

from __future__ import annotations

import pytest

from rag_local.embedder import SentenceTransformerEmbedder
from rag_local.errors import EmbeddingError


class TestSentenceTransformerEmbedder:
    """Tests for the embedding module using real model loading."""

    def test_embed_empty_text_raises(self) -> None:
        embedder = SentenceTransformerEmbedder()
        with pytest.raises(EmbeddingError, match="empty text"):
            embedder.embed("")

    def test_embed_blank_text_raises(self) -> None:
        embedder = SentenceTransformerEmbedder()
        with pytest.raises(EmbeddingError, match="empty text"):
            embedder.embed("   ")

    def test_empty_model_name_raises(self) -> None:
        with pytest.raises(ValueError, match="model_name must be non-empty"):
            SentenceTransformerEmbedder(model_name="")

    def test_embed_returns_expected_dimension(self) -> None:
        embedder = SentenceTransformerEmbedder()
        vec = embedder.embed("Hello world")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)
        assert embedder.dimension > 0

    def test_embed_many_returns_correct_count(self) -> None:
        embedder = SentenceTransformerEmbedder()
        texts = ["Hello", "World", "Test"]
        vectors = embedder.embed_many(texts)
        assert len(vectors) == 3
        for v in vectors:
            assert len(v) == embedder.dimension

    def test_embed_many_empty_returns_empty_list(self) -> None:
        embedder = SentenceTransformerEmbedder()
        assert embedder.embed_many([]) == []