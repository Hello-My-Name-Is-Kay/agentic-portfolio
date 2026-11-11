"""ChromaVectorStore against a real Chroma index in a temp dir (embeddings are supplied, so no download)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rag_local.errors import StoreError
from rag_local.store import ChromaVectorStore

from .fakes import HashEmbedder

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(persist_dir=str(tmp_path), collection_name="test_policies", embedder=HashEmbedder())


def test_add_and_search_uses_cosine_distance(store: ChromaVectorStore) -> None:
    store.add(["fuel policy full tank", "pets allowed in cars"], metadatas=[{"f": "fuel.md"}, {"f": "pets.md"}])
    results = store.search(HashEmbedder().embed("fuel policy full tank"), top_k=2)
    assert results[0]["metadata"] == {"f": "fuel.md"}
    assert results[0]["distance"] == pytest.approx(0.0, abs=1e-5)  # identical text -> cosine distance 0
    assert 0.0 < results[1]["distance"] <= 1.0 + 1e-6


def test_upsert_with_ids_does_not_duplicate(store: ChromaVectorStore) -> None:
    store.add(["a text"], metadatas=[{"f": "a"}], ids=["a.md#0"])
    store.add(["a text updated"], metadatas=[{"f": "a"}], ids=["a.md#0"])
    assert store.count == 1
    assert store.search(HashEmbedder().embed("a text updated"), top_k=1)[0]["document"] == "a text updated"


def test_default_ids_and_no_metadata(store: ChromaVectorStore) -> None:
    store.add(["one"])
    store.add(["two"])
    assert store.count == 2


def test_clear(store: ChromaVectorStore) -> None:
    store.add(["one", "two"])
    store.clear()
    assert store.count == 0


def test_add_validation(tmp_path: Path) -> None:
    store = ChromaVectorStore(persist_dir=str(tmp_path), collection_name="no_embedder")
    store.add([])  # no-op
    with pytest.raises(StoreError, match="no embedder configured"):
        store.add(["x"])
    with pytest.raises(StoreError, match="does not match"):
        store.add(["x", "y"], embeddings=[[1.0, 0.0]])


def test_empty_query_embedding_rejected(store: ChromaVectorStore) -> None:
    with pytest.raises(StoreError, match="empty query embedding"):
        store.search([])


def test_dimension_mismatch_wrapped(store: ChromaVectorStore) -> None:
    store.add(["one"])
    with pytest.raises(StoreError, match="Search failed"):
        store.search([1.0, 0.0])


def test_invalid_collection_name_wrapped(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="Failed to open Chroma collection"):
        ChromaVectorStore(persist_dir=str(tmp_path), collection_name="x")
