"""RagPipeline end to end with a real Chroma index, the hash embedder and a fake LLM."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rag_local.chunker import Document
from rag_local.config import Settings
from rag_local.errors import GenerationError, NoRelevantDocumentsError, RagError
from rag_local.loader import load_documents
from rag_local.pipeline import RagPipeline, _build_rag_prompt
from rag_local.retriever import RetrievedChunk
from rag_local.store import ChromaVectorStore

from .fakes import EchoGenerator, HashEmbedder

if TYPE_CHECKING:
    from rag_local.generator import LLMResponse

DOCS = Path(__file__).resolve().parents[2] / "docs"


def _pipeline(tmp_path: Path, generator: object | None = None, min_score: float = 0.2) -> RagPipeline:
    settings = Settings(_env_file=None, chroma_persist_dir=str(tmp_path), min_relevance_score=min_score)  # type: ignore[call-arg]
    embedder = HashEmbedder(dim=256)
    store = ChromaVectorStore(persist_dir=str(tmp_path), collection_name="test_policies", embedder=embedder)
    return RagPipeline(settings, embedder=embedder, store=store, generator=generator or EchoGenerator())  # type: ignore[arg-type]


def test_ingest_real_docs_is_idempotent(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)
    docs = load_documents(str(DOCS))
    assert len(docs) == 21
    first = pipeline.ingest(docs)
    assert first > 21
    pipeline.ingest(docs)
    assert pipeline._store.count == first


def test_query_returns_answer_with_citations(tmp_path: Path) -> None:
    gen = EchoGenerator()
    pipeline = _pipeline(tmp_path, gen)
    pipeline.ingest(
        [
            Document(page_content="Fuel policy: return the car with a full tank.", metadata={"filename": "fuel.md"}),
            Document(page_content="Pets travel in carriers only.", metadata={"filename": "pets.md"}),
        ]
    )
    result = pipeline.query("What is the fuel policy for a full tank?", top_k=2)
    assert result.citations[0].metadata["filename"] == "fuel.md"
    assert result.answer == "Fuel policy: return the car with a full tank. [Document 1]"
    assert 0.2 <= result.confidence <= 1.0
    assert (result.model, result.tokens_in, result.tokens_out) == ("echo", 10, 5)
    assert "=== Question ===\nWhat is the fuel policy for a full tank?" in gen.prompts[0]


def test_unrelated_question_refuses(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path, min_score=0.5)
    pipeline.ingest(
        [Document(page_content="Fuel policy: return the car with a full tank.", metadata={"filename": "f"})]
    )
    with pytest.raises(NoRelevantDocumentsError):
        pipeline.query("Quantum chromodynamics lecture schedule")


def test_empty_question(tmp_path: Path) -> None:
    with pytest.raises(RagError, match="empty question"):
        _pipeline(tmp_path).query(" ")


def test_generation_failure_wrapped(tmp_path: Path) -> None:
    class Failing:
        def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse:  # noqa: ARG002
            raise RuntimeError("ollama down")

    pipeline = _pipeline(tmp_path, Failing())
    pipeline.ingest([Document(page_content="fuel tank full", metadata={"filename": "f"})])
    with pytest.raises(GenerationError, match="ollama down"):
        pipeline.query("fuel tank")


def test_retrieval_failure_wrapped(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)
    pipeline.ingest([Document(page_content="fuel tank full", metadata={"filename": "f"})])
    pipeline._retriever._embedder = HashEmbedder(dim=8)  # wrong dimension for the index
    with pytest.raises(RagError, match="Retrieval failed"):
        pipeline.query("fuel tank")


def test_ingest_nothing(tmp_path: Path) -> None:
    assert _pipeline(tmp_path).ingest([Document(page_content="   ")]) == 0


def test_prompt_numbers_documents_with_sources() -> None:
    chunks = [RetrievedChunk("alpha", {"source": "a.md"}, 0.9, 0.1), RetrievedChunk("beta", {}, 0.5, 0.5)]
    prompt = _build_rag_prompt("Q?", chunks)
    assert "--- Document 1 (source: a.md) ---\nalpha" in prompt
    assert "--- Document 2 (source: unknown) ---\nbeta" in prompt
    assert "[Document 1]" in prompt
