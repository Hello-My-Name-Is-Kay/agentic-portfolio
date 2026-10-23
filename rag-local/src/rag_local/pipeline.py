"""RAG pipeline: orchestrates retrieval + generation.

The main RAG class coordinates the full pipeline:
1. Retrieve relevant documents.
2. Build a prompt with context and citations.
3. Generate an answer using the LLM.
4. Validate the output and return with metadata.
"""

from __future__ import annotations

from rag_local.logging import get_logger
from dataclasses import dataclass, field

from rag_local.chunker import Document
from rag_local.config import Settings
from rag_local.embedder import SentenceTransformerEmbedder
from rag_local.errors import GenerationError, NoRelevantDocuments, RagError
from rag_local.generator import OllamaGenerator
from rag_local.retriever import Retriever, RetrievedChunk
from rag_local.store import ChromaVectorStore

log = get_logger(__name__)


@dataclass
class RagResult:
    """Result of a RAG query."""

    question: str
    answer: str
    citations: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    model: str = ""
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


def _build_rag_prompt(question: str, contexts: list[RetrievedChunk]) -> str:
    """Build a prompt that grounds the LLM in retrieved context."""
    context_parts = []
    for i, chunk in enumerate(contexts, 1):
        source = chunk.metadata.get("source", "unknown")
        context_parts.append(f"--- Document {i} (source: {source}) ---\n{chunk.text}")

    context_block = "\n\n".join(context_parts)

    prompt = (
        "You are a helpful rental-car policy assistant. Answer the customer's question "
        "based ONLY on the provided policy documents. If the answer cannot be found in the "
        "documents, say 'I don't know' — do not make up information.\n\n"
        "For each fact you include, cite the source document in brackets like [Document 1].\n\n"
        "=== Policy Documents ===\n"
        f"{context_block}\n\n"
        "=== Question ===\n"
        f"{question}\n\n"
        "=== Answer (with citations) ==="
    )
    return prompt


class RagPipeline:
    """Orchestrates retrieval-augmented generation.

    Usage:
        pipeline = RagPipeline()
        result = pipeline.query("What is the fuel policy?")
        print(result.answer)
        for c in result.citations:
            print(f"  [{c.metadata.get('source')}] score={c.score:.2f}")
    """

    def __init__(self, settings: Settings | None = None) -> None:
        config = settings or Settings()

        self._embedder = SentenceTransformerEmbedder(
            model_name=config.embedding_model_name,
            device=config.embedding_device,
        )

        self._store = ChromaVectorStore(
            persist_dir=config.chroma_persist_dir,
            collection_name=config.collection_name,
            embedder=self._embedder,
        )

        self._retriever = Retriever(
            embedder=self._embedder,
            store=self._store,
            top_k=config.top_k,
            min_relevance_score=config.min_relevance_score,
        )

        self._generator = OllamaGenerator(config)

        self._config = config

    def query(self, question: str, top_k: int | None = None) -> RagResult:
        """Run the full RAG pipeline: retrieve → generate.

        Args:
            question: The user's question.
            top_k: Override number of documents to retrieve.

        Returns:
            RagResult with answer, citations, and metadata.

        Raises:
            NoRelevantDocuments: If no documents are relevant to the question.
            GenerationError: If the LLM fails.
        """
        if not question or not question.strip():
            raise RagError("Cannot query with empty question")

        # Step 1: Retrieve
        try:
            chunks = self._retriever.retrieve(question, top_k=top_k or self._config.top_k)
        except NoRelevantDocuments:
            raise
        except Exception as exc:
            raise RagError(f"Retrieval failed: {exc}") from exc

        confidence = max(c.score for c in chunks) if chunks else 0.0

        # Step 2: Generate
        prompt = _build_rag_prompt(question, chunks)
        system_prompt = (
            "You are a precise rental-car policy assistant. "
            "Answer only from the provided documents. "
            "Cite sources using [Document N] format. "
            "If the documents don't contain the answer, say 'I don't know based on the available policies.'"
        )

        try:
            response = self._generator.generate(prompt, system_prompt=system_prompt)
        except Exception as exc:
            raise GenerationError(f"LLM generation failed: {exc}") from exc

        # Step 3: Build result
        return RagResult(
            question=question,
            answer=response.text,
            citations=chunks,
            confidence=round(confidence, 3),
            model=response.model,
            latency_ms=response.latency_ms,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )

    def ingest(self, documents: list[Document]) -> int:
        """Ingest documents into the vector store.

        Args:
            documents: List of Document objects to chunk and store.

        Returns:
            Number of chunks stored.

        Raises:
            RagError: If ingestion fails.
        """
        from rag_local.chunker import RecursiveCharacterChunker

        chunker = RecursiveCharacterChunker(
            chunk_size=self._config.chunk_size,
            chunk_overlap=self._config.chunk_overlap,
        )

        chunks = chunker.chunk(documents)
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]

        try:
            self._store.add(texts=texts, metadatas=metadatas)
        except Exception as exc:
            raise RagError(f"Failed to ingest documents: {exc}") from exc

        return len(chunks)