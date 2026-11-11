"""Unit tests for the embedding wrapper. The sentence-transformers model is replaced by a fake."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

import rag_local.embedder as embedder_module
from rag_local.embedder import SentenceTransformerEmbedder
from rag_local.errors import EmbeddingError


class FakeModel:
    def __init__(self, name: str, device: str) -> None:
        self.name, self.device = name, device
        self.calls: list[dict[str, Any]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode(self, texts: str | list[str], **kwargs: Any) -> np.ndarray:
        self.calls.append(kwargs)
        if texts == "boom":
            raise RuntimeError("encode failed")
        if isinstance(texts, str):
            return np.array([1.0, 0.0, 0.0])
        return np.array([[1.0, 0.0, 0.0]] * len(texts))


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> SentenceTransformerEmbedder:
    monkeypatch.setattr(embedder_module, "SentenceTransformer", FakeModel)
    return SentenceTransformerEmbedder(model_name="fake-model", device="cpu")


def test_embed_returns_floats_and_normalises(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.embed("Hello world") == [1.0, 0.0, 0.0]
    assert embedder.dimension == 3
    assert embedder._model.calls[0]["normalize_embeddings"] is True  # type: ignore[attr-defined]


def test_embed_many(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.embed_many(["a", "b"]) == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert embedder.embed_many([]) == []


@pytest.mark.parametrize("text", ["", "   "])
def test_embed_empty_text_raises(embedder: SentenceTransformerEmbedder, text: str) -> None:
    with pytest.raises(EmbeddingError, match="empty text"):
        embedder.embed(text)


def test_encode_failure_wrapped(embedder: SentenceTransformerEmbedder) -> None:
    with pytest.raises(EmbeddingError, match="encode failed"):
        embedder.embed("boom")


def test_batch_failure_wrapped(embedder: SentenceTransformerEmbedder, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("oom")

    monkeypatch.setattr(embedder._model, "encode", fail)
    with pytest.raises(EmbeddingError, match="Batch embedding failed for 2 texts"):
        embedder.embed_many(["a", "b"])


def test_empty_model_name_raises() -> None:
    with pytest.raises(ValueError, match="model_name must be non-empty"):
        SentenceTransformerEmbedder(model_name="")


def test_model_load_failure_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("not found on hub")

    monkeypatch.setattr(embedder_module, "SentenceTransformer", fail)
    with pytest.raises(EmbeddingError, match="Failed to load embedding model"):
        SentenceTransformerEmbedder(model_name="missing")
