# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- Initial RAG pipeline: ingestion, chunking, embedding, retrieval, generation.
- 21 fictional rental-policy documents in `docs/`.
- ChromaDB vector store with sentence-transformers embeddings (CPU).
- Ollama-based LLM generation with retry, timeout, and structured logging.
- Confidence-threshold guardrail: refuses when no document scores above `min_relevance_score`.
- CLI interface: `rag ingest` and `rag query` (interactive and single-shot).
- Evaluation script (`scripts/eval_rag.py`) with recall@k and answer-accuracy metrics.
- 20-question eval dataset in `tests/fixtures/eval_questions.py`.
- Full CI pipeline: lint, type, test, coverage, audit, eval gate.
- Unit tests for chunker, loader, embedder, and retriever. 
- Pydantic v2 models at all boundaries.
- Structured JSON logging with structlog.
- Typed exception hierarchy in `errors.py`.