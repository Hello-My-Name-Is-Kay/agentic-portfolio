"""Document chunking with configurable size and overlap.

Splits documents into overlapping chunks suitable for embedding and retrieval.
Uses a simple recursive character splitter to avoid over-engineering.
"""

from __future__ import annotations

from rag_local.logging import get_logger
from typing import Protocol

from pydantic import BaseModel, Field

log = get_logger(__name__)


class Document(BaseModel):
    """A single document with metadata."""

    page_content: str = Field(..., description="Document text content")
    metadata: dict = Field(default_factory=dict, description="Arbitrary metadata (source, page, etc.)")


class Chunk(BaseModel):
    """A chunk produced from a document."""

    text: str = Field(..., description="Chunk text content")
    metadata: dict = Field(default_factory=dict, description="Inherited metadata from source document")
    chunk_id: int | None = Field(default=None, description="Index within the source document")


class ChunkingStrategy(Protocol):
    """Protocol for chunking strategies."""

    def chunk(self, documents: list[Document]) -> list[Chunk]: ...


class RecursiveCharacterChunker:
    """Splits documents into chunks of a target size with configurable overlap.

    Uses a simple recursive split on paragraph, then sentence, then word boundaries.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, documents: list[Document]) -> list[Chunk]:
        """Split documents into chunks.

        Args:
            documents: List of documents to chunk.

        Returns:
            List of chunks with metadata inherited from source documents.

        Raises:
            ValueError: If input documents are empty or invalid.
        """
        if not documents:
            return []

        chunks: list[Chunk] = []
        for doc_idx, doc in enumerate(documents):
            text = doc.page_content
            if not text or not text.strip():
                log.warning("chunker.empty_document", doc_index=doc_idx)
                continue

            doc_chunks = self._split_document(text, doc.metadata, doc_idx)
            chunks.extend(doc_chunks)

        return chunks

    def _split_document(self, text: str, metadata: dict, doc_idx: int) -> list[Chunk]:
        """Split a single document's text into chunks."""
        separators = ["\n\n", "\n", ". ", " "]
        chunks: list[Chunk] = []

        current = text
        while current:
            if len(current) <= self.chunk_size:
                chunks.append(
                    Chunk(
                        text=current.strip(),
                        metadata={**metadata, "doc_index": doc_idx},
                        chunk_id=len(chunks),
                    )
                )
                break

            # Find the best split point
            split_at = self._find_split_point(current[: self.chunk_size], separators)
            if split_at <= 0:
                split_at = self.chunk_size  # hard break if no good separator found

            chunks.append(
                Chunk(
                    text=current[:split_at].strip(),
                    metadata={**metadata, "doc_index": doc_idx},
                    chunk_id=len(chunks),
                )
            )

            # Advance with overlap
            overlap_start = max(0, split_at - self.chunk_overlap)
            current = current[overlap_start:]

        return chunks

    @staticmethod
    def _find_split_point(text_segment: str, separators: list[str]) -> int:
        """Find the best split point in a text segment using the given separators."""
        best = -1
        for sep in separators:
            pos = text_segment.rfind(sep)
            if pos > best:
                best = pos + len(sep)
        return best