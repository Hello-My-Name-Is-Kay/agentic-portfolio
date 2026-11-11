# RAG on Local Models

> **TL;DR** — Retrieval-Augmented Generation over 21 rental-policy documents. Chroma (cosine) + sentence-transformers embeddings, Ollama for generation, answers cite `[Document N]`, and the pipeline refuses when nothing passes a similarity threshold. Measured retrieval recall@5 = **0.905** on 20 golden questions, gated in CI. Runs on local infrastructure; the only download is the embedding model on first use.

> **Tags:** `rag`, `chroma`, `ollama`, `sentence-transformers`, `recall@k`, `local-llm`, `cli`, `pydantic-validation`, `retrieval-guardrails`, `structured-logging`, `ci-eval-gate`

Retrieval-Augmented Generation engine over rental-policy documents using Chroma vector store and Ollama-hosted local models.

## Why This Exists

A RAG pipeline that runs on local infrastructure: no hosted LLM or embedding API. The point is that an answer should be grounded in retrieved evidence or not given at all, and that retrieval quality is measured instead of assumed. It covers chunking, embedding, a vector store, a similarity-threshold refusal, cited answers, and a recall gate in CI.

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
              │  Chroma Vector Store │  cosine distance, MiniLM-L6 embeddings
              └──────┬──────────────┘
                     │ search (top-k)
                     ▼
              ┌─────────────────────┐
              │   Retriever         │  drops chunks with cosine sim < 0.35
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

The embedding model (`all-MiniLM-L6-v2`, ~90 MB) is downloaded from Hugging Face the first time you ingest or query.

### Ingest Documents

Chunks get stable IDs (`<filename>#<n>`), so re-running ingest updates the index instead of duplicating it.

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
| Questions in dataset | 20 (21 expected source documents) |
| Retrieval recall@5 (cosine ≥ 0.35) | **0.905** — 19 of 21 expected documents |
| Answer accuracy | not measured yet (needs a running Ollama; not run in CI) |
| CI gate | recall@5 ≥ 0.85 |

Measured with `scripts/eval_rag.py --retrieval-only`. The miss is "Can I use the vehicle for international travel?": no chunk reaches the 0.35 similarity threshold, so the pipeline refuses instead of answering. That is the threshold doing its job, but it is also a retrieval gap worth fixing (e.g. a lower threshold or hybrid keyword search).

### Run Evaluation

```bash
# Retrieval only: indexes docs/ in a temp dir with the real embedding model; no LLM needed (what CI runs)
python scripts/eval_rag.py --retrieval-only --min-score 0.85

# Full pipeline against your ingested index and a running Ollama: also checks answer accuracy
python scripts/eval_rag.py --min-score 0.85
```

The script writes `eval-report.json` and exits 1 if recall (and, in full mode, answer accuracy) is below `--min-score`.

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

Unit tests run offline: the sentence-transformers model is replaced by a fake, Ollama by `httpx.MockTransport`, and pipeline tests use a real Chroma index in a temp dir with a deterministic bag-of-words embedder.

- **Chunker**: size limit, overlap between chunks, paragraph-boundary preference, termination (regression for an infinite loop), metadata.
- **Loader**: directory discovery, nonexistent paths, empty files, recursion.
- **Embedder**: normalisation, batching, error wrapping.
- **Store**: cosine distance, upsert without duplicates, validation, error wrapping.
- **Retriever**: cosine scoring, sorting, threshold filtering, refusal, error wrapping.
- **Generator**: Ollama request shape (`options.num_predict`/`temperature`), retries on 5xx/timeouts/connection errors, no retry on 4xx, malformed bodies.
- **Pipeline**: ingest of the real 21 docs is idempotent; cited answer; refusal on an unrelated question.
- **CLI**: ingest/query in JSON and text, refusal vs error exit codes, interactive mode.

## Dependency audit

`pip-audit` in CI ignores four chromadb advisories (PYSEC-2026-311, -3813, -3814, -3815). All of them are in the Chroma HTTP server's endpoints and RBAC provider; this project only uses the embedded `PersistentClient` and never starts a Chroma server. No fixed chromadb release exists yet, so the ignores should be removed when one ships.

## Not built yet

- No web UI or API endpoint (CLI only by design — this shows the core RAG logic).
- No re-ranking or hybrid (keyword + dense) search; retrieval is dense-only.
- No streaming output (the Ollama generator uses non-streaming for simplicity).
- No LangChain dependency (direct Chroma + sentence-transformers API for clarity).
- Generation goes straight to Ollama; it does not use [llm-router](../llm-router) yet.

## Related Repos

- [eval-harness](../eval-harness) — the same 20 golden questions as a reusable eval library with an LLM-as-judge scorer.
- [guardrails](../guardrails) — attack cases written against this pipeline.
