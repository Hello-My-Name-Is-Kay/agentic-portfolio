"""Unit tests for the RAG chunker."""

from __future__ import annotations

import pytest

from rag_local.chunker import Document, RecursiveCharacterChunker


class TestRecursiveCharacterChunker:
    """Tests for the chunker module."""

    def test_empty_documents_returns_empty_list(self) -> None:
        chunker = RecursiveCharacterChunker()
        assert chunker.chunk([]) == []

    def test_single_short_document_returns_one_chunk(self) -> None:
        chunker = RecursiveCharacterChunker(chunk_size=100, chunk_overlap=10)
        doc = Document(page_content="Hello world. This is a test.", metadata={"source": "test.md"})
        chunks = chunker.chunk([doc])
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world. This is a test."
        assert chunks[0].metadata["source"] == "test.md"
        assert chunks[0].chunk_id == 0

    def test_long_document_split_into_multiple_chunks(self) -> None:
        chunker = RecursiveCharacterChunker(chunk_size=50, chunk_overlap=10)
        text = " ".join(["word"] * 100)  # ~600 chars
        doc = Document(page_content=text, metadata={})
        chunks = chunker.chunk([doc])
        assert len(chunks) > 1

    def test_chunk_overlap_less_than_chunk_size(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            RecursiveCharacterChunker(chunk_size=100, chunk_overlap=200)

    def test_negative_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            RecursiveCharacterChunker(chunk_size=100, chunk_overlap=-1)

    def test_non_positive_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            RecursiveCharacterChunker(chunk_size=0, chunk_overlap=0)

    def test_empty_document_skipped(self) -> None:
        chunker = RecursiveCharacterChunker()
        doc = Document(page_content="   ", metadata={})
        chunks = chunker.chunk([doc])
        assert len(chunks) == 0

    def test_chunk_metadata_inherits_source(self) -> None:
        chunker = RecursiveCharacterChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 200
        doc = Document(page_content=text, metadata={"source": "test.md", "author": "me"})
        chunks = chunker.chunk([doc])
        for c in chunks:
            assert c.metadata["source"] == "test.md"
            assert c.metadata["author"] == "me"
            assert "doc_index" in c.metadata