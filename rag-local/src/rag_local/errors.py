"""Application-specific typed exception hierarchy.

Every error in the application is raised as one of these types.
Never raise bare Exception or use blanket except blocks without logging.
"""

from __future__ import annotations


class RagError(Exception):
    """Base for all RAG application errors."""


class ConfigError(RagError):
    """Invalid or missing configuration."""


class EmbeddingError(RagError):
    """Failure during text embedding generation."""


class RetrievalError(RagError):
    """Failure during document retrieval from the vector store."""


class GenerationError(RagError):
    """Failure during LLM response generation."""


class ValidationError(RagError):
    """Input validation failure."""


class StoreError(RagError):
    """Vector store operation failure."""


class NoRelevantDocuments(RetrievalError):
    """Retrieval returned no documents above the relevance threshold."""


class DocumentIngestionError(RagError):
    """Failure during document loading or chunking."""