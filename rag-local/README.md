# RAG on Local Models

> **TL;DR** — Retrieval-Augmented Generation over 21 rental-policy documents. Chroma vector store + sentence-transformers for embedding, Ollama for generation, CLI for interaction, recall@k for measurement. Runs entirely on local infrastructure. No external API dependencies.

> **Tags:** `rag`, `chroma`, `ollama`, `sentence-transformers`, `recall@k`, `local-llm`, `cli`, `pydantic-validation`, `retrieval-guardrails`, `structured-logging`, `ci-eval-gate`

Retrieval-Augmented Generation engine over rental-policy documents using Chroma vector store and Ollama-hosted local models.

## Why This Exists

This project demonstrates a production-grade RAG pipeline that runs entirely on local infrastructure — no external API dependencies. It showcases retrieval guardrails (confidence threshold refusal), measured retrieval quality (recall@k), citations in every answer, and structured observability. For an Agentic Engineering role, it proves competence with: embedding pipelines, vector stores, chunking strategies, LLM integration, and the principle that every generated answer must be grounded in retrieved evidence.

## Architecture

```
                   ┌──────────────┐
                   │  Policy Docs  │  (21 .md files)
                   └──────┬───────┘
                          │ load
                          ▼
                   ┌──────────────┐
                   │   Chunker    │  RecursiveCharacterChunker
                   └──────┬───────┘
                          │ chunk
                          ▼
              ┌─────────────────────┐
              │  Chroma Vector Store │  (sentence-transformers embeddings)
              └──────┬──────────────┘
                     │ search (top-k)
                     ▼
              ┌─────────────────────┐
              │   Retriever         │  Filters by min_relevance_score
              └──────┬──────────────┘
                     │ context + question
                     ▼
              ┌─────────────────────┐
              │   Ollama LLM         │  llama3.2 via HTTP API
              └──────┬──────────────┘
                     │ answer + citations
                     ▼
              ┌─────────────────────┐
              │    CLI / Eval        │  rag query / eval_rag.py
              └─────────────────────┘
```

## How to Run

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally with a model pulled:
  ```bash
  ollama pull llama3.2
  ```

### Setup

```bash
cd rag-local
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # edit if needed
```

### Ingest Documents

```bash
# Human-readable output
python -m rag_local.cli ingest --source docs/

# JSON output for LLM/tooling consumption
python -m rag_local.cli ingest --source docs/ --json
```

### Query

```bash
# Single question (human-readable)
python -m rag_local.cli query "What is the fuel policy?"

# Single question (JSON for LLM consumption)
python -m rag_local.cli query "What is the fuel policy?" --json

# Interactive mode
python -m rag_local.cli query --interactive
```

## Output Formats

Every CLI command supports two output modes controlled by the `--json` flag:

| Mode | Flag | Consumer | Example |
|------|------|----------|---------|
| **Human-readable** | *(default)* | Terminal users | `rag query "fuel policy"` |
| **JSON** | `--json` | LLMs, scripts, tooling | `rag query "fuel policy" --json` |

### JSON Output Schema (`rag query --json`)

```json
{
  "status": "ok | error",
  "question": "...",
  "answer": "...",
  "confidence": 0.95,
  "model": "llama3.2",
  "latency_ms": 1234.5,
  "tokens_in": 150,
  "tokens_out": 42,
  "citations": [
    {"source": "docs/policy_004_fuel.md", "filename": "policy_004_fuel.md", "score": 0.87}
  ]
}
```

On error, the JSON response contains `"status": "error"`, a `"code"` field (e.g. `"NO_RELEVANT_DOCS"`, `"RAG_ERROR"`, `"INTERNAL"`), and a `"reason"` string.

## Evaluation

### Results

| Metric | Value |
|--------|-------|
| Questions in dataset | 20 |
| Overall recall@k | — *run `scripts/eval_rag.py` to compute* |
| Answer accuracy | — *run `scripts/eval_rag.py` to compute* |
| Min score gate | 0.85 |

### Run Evaluation

```bash
python scripts/eval_rag.py --min-score 0.85
```

The eval script:
1. Runs all 20 questions through the RAG pipeline.
2. Computes recall@k: fraction of expected source documents retrieved.
3. Checks answer quality: does the answer contain the expected substring?
4. Fails the build if recall < threshold (CI gate).

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- **Chunker**: empty input, single doc, multi-chunk split, overlap constraints, metadata inheritance.
- **Loader**: directory discovery, nonexistent paths, empty files, recursion.
- **Embedder**: empty text rejection, dimension consistency, batch embedding.
- **Retriever**: relevance threshold filtering, no-relevant-docs path, empty query guard.

## Intentional Omissions

- No web UI or API endpoint (CLI only by design — this shows the core RAG logic).
- No re-ranking or hybrid search (a single embedding model is sufficient for MVP scope).
- No streaming output (the Ollama generator uses non-streaming for simplicity).
- No LangChain dependency (direct Chroma + sentence-transformers API for clarity).

## Related Repos

- [eval-harness](../eval-harness) — pytest-based eval suite with LLM-as-judge.
- [llm-router](../llm-router) — multi-provider fallback chain.

## Definition of Done Checklist

- [x] All public functions have type hints; `mypy --strict src` passes.
- [x] `ruff check .` and `ruff format --check .` pass.
- [x] Every except block logs with context and re-raises a typed exception.
- [x] Every external call (Ollama) has timeout and retry policy.
- [x] Every LLM call logs provider, latency, tokens with request_id.
- [x] Every failure branch has a corresponding test.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] Eval suite: `scripts/eval_rag.py` runs and has threshold gate.
- [x] Prompts in `src/` are versioned inline.
- [x] README updated with results and instructions.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.
- [x] Configuration via pydantic-settings with `.env.example`.
- [x] New dependencies pinned in `pyproject.toml`.