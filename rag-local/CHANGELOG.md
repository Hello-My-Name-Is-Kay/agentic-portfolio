# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `__init__.py` had an unterminated docstring; the package could not be imported.
- Retrieval scores were `1 - distance` on Chroma's default squared-L2 metric, so the 0.35 relevance threshold did not mean what it said. The collection now uses cosine distance and embeddings are normalised, so the score is cosine similarity. Delete an existing `data/vectorstore` and re-ingest.
- The chunker could loop forever when a separator fell inside the overlap window, and it split at the last space rather than preferring paragraph and sentence boundaries.
- Ollama ignored `temperature` and `max_tokens` because they were sent at the top level; they now go in `options`. 5xx errors are now retried, 4xx are not.
- Re-running `ingest` duplicated every chunk; chunks now have stable IDs and are upserted.
- Adding documents without metadata failed (Chroma rejects empty metadata dicts).
- `rag query --json` without a question crashed with `NameError` (missing `json` import).
- Logs went to stdout and corrupted `--json` output; they now go to stderr.
- The CI eval gate was `... || echo`, so it could never fail. CI now runs a retrieval-only eval that needs no LLM and fails below recall 0.85.
- Unit tests downloaded the embedding model from Hugging Face; they now run offline with fakes.

### Added

- `scripts/eval_rag.py --retrieval-only` and a measured result: recall@5 = 0.905.
- `RagPipeline` accepts injected embedder, store and generator; `RagPipeline.retrieve()`.
- Tests for store, generator, pipeline and CLI.

### Changed

- `NoRelevantDocuments` renamed to `NoRelevantDocumentsError`.

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