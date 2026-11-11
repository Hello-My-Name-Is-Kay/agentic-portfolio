# Agentic AI Engineering Portfolio

Eight independent Python projects around one fictional car-rental domain: a retrieval pipeline, an eval harness, an LLM router, guardrails, a booking API, an MCP server wrapping it, an agent that uses it, and a ticket-queue tool.
Each project has its own dependencies, tests, CI workflow and README. Every README states what is measured and what is not built yet.

## Projects

| # | Project | Description | Directory |
|---|---------|-------------|-----------|
| 1 | **RAG on Local Models** | Chroma (cosine) + sentence-transformers + Ollama over 21 policy docs; cited answers, refusal below a similarity threshold; measured recall@5 = 0.905, gated in CI | [rag-local](rag-local/) |
| 2 | **Eval Harness** | JSONL golden dataset, recall + answer-accuracy scoring, Ollama LLM-as-judge, gate script that fails CI on regression | [eval-harness](eval-harness/) |
| 3 | **Multi-Provider LLM Router** | Fallback chain (Anthropic → OpenAI → Ollama), retries on transient errors, LRU cache, token/cost budget that refuses calls once spent | [llm-router](llm-router/) |
| 4 | **Mock Booking API** | FastAPI + Pydantic, OpenAPI spec, optional API key, request-scoped `Idempotency-Key`, one JSON error envelope | [mock-booking-api](mock-booking-api/) |
| 5 | **MCP Server** | 3 booking tools on the MCP Python SDK (2.x), validated inputs, structured error codes, stdio demo with the MCP client | [mcp-server](mcp-server/) |
| 6 | **Guardrails Suite** | Regex PII redaction, pattern-based injection detector, output validator; 36-case attack dataset with CI gate | [guardrails](guardrails/) |
| 7 | **Flagship LangGraph Agent** | LangGraph `StateGraph` customer-service agent: auth, step-up for writes, ownership checks, handoff | [flagship-agent](flagship-agent/) |
| 8 | **Ticket Automation Tool** | SQLite ticket queue CLI, parameterized SQL, idempotent writes, audit log that survives deletes, synthetic data only | [ticket-tool](ticket-tool/) |

## Stack

- **Language:** Python 3.11+ (CI runs 3.12)
- **Validation:** Pydantic v2
- **Logging:** structlog (JSON, to stderr)
- **Persistence:** SQLite, ChromaDB
- **LLM:** Ollama (local), Anthropic, OpenAI
- **Testing:** pytest, pytest-cov, mypy, ruff

## What CI checks

Each project has a workflow in [.github/workflows](.github/workflows/) that runs when its directory changes:

1. `ruff check .` and `ruff format --check .`
2. `mypy --strict src`
3. `pytest` with an 80% coverage gate; tests run offline, with external services faked or mocked
4. `pip-audit`
5. Where the project has one, its eval gate: eval-harness score threshold, guardrails pass rate, rag-local retrieval recall

## Principles

1. **Fail loudly in dev, fail safely in prod** — never swallow exceptions
2. **LLM output is untrusted input** — validate at every boundary
3. **Every effect is traceable** — structured logs on every external call
4. **Tests describe behavior** — assert outcomes, not implementation details
5. **Small, boring, and correct** — short functions, explicit types, no magic
6. **Say what is not built** — each README lists its gaps

All data is synthetic and built from scratch.
