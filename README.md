# Portfolio Overview
# Built from Work-Portfolio-Urgent.md specification

This repository contains independent, portfolio-quality projects for an Agentic AI Engineer role.
Each project is self-contained with its own tests, CI, documentation, and dependencies.

## Projects

| # | Project | Description | Directory |
|---|---------|-------------|-----------|
| 1 | **RAG on Local Models** | Chroma + Ollama RAG over rental-policy docs, CLI, recall@k eval | [rag-local](rag-local/) |
| 2 | **Eval Harness** | pytest-based eval with golden dataset, LLM-as-judge, CI gate | [eval-harness](eval-harness/) |
| 3 | **Multi-Provider LLM Router** | Fallback chain (Anthropic → OpenAI → Ollama), cache, budget | [llm-router](llm-router/) |
| 4 | **Mock Booking API** | FastAPI with OpenAPI, Pydantic, idempotency, API key auth | [mock-booking-api](mock-booking-api/) |
| 5 | **MCP Server** | 3 booking tools with typed schemas, JSON error responses | [mcp-server](mcp-server/) |
| 6 | **Guardrails Suite** | 33 attack cases, PII redaction, output validation, CI gate | [guardrails](guardrails/) |
| 7 | **Flagship LangGraph Agent** | Customer service agent: auth → intent → tools → respond | [flagship-agent](flagship-agent/) |
| 8 | **Ticket Automation Tool** | SQL ticket queue, idempotency, audit, fake data only | [ticket-tool](ticket-tool/) |

## Stack

- **Language:** Python 3.11+
- **Validation:** Pydantic v2
- **Logging:** structlog (JSON)
- **Persistence:** SQLite, ChromaDB
- **LLM:** Ollama (local), Anthropic, OpenAI
- **Testing:** pytest, pytest-cov, mypy, ruff
- **CI:** GitHub Actions (lint → type → test → coverage → audit → eval gate)

## Key Principles (from Work-Portfolio-Urgent.md)

1. **Fail loudly in dev, fail safely in prod** — never swallow exceptions
2. **LLM output is untrusted input** — validate at every boundary
3. **Every effect is traceable** — structured logging with request_id
4. **Tests describe behavior** — tool trajectory > implementation details
5. **Small, boring, and correct** — short functions, explicit types, no magic
6. **Ship the smallest thing that fully works** — no half-finished features

## Definition of Done (applied to every project)

- [x] `mypy --strict src` passes
- [x] `ruff check .` and `ruff format --check .` pass
- [x] Every except block logs with context and either recovers or re-raises typed errors
- [x] Every write operation accepts an idempotency key
- [x] Every external call has a timeout and retry policy
- [x] Every LLM call logs provider, latency, tokens, and cost
- [x] Every failure branch has a corresponding test
- [x] `pytest --cov=src --cov-fail-under=80` passes
- [x] README documents architecture, usage, and results
- [x] CHANGELOG.md has an entry
- [x] No secrets, no print, no commented-out code, no TODO
- [x] Configuration via pydantic-settings with .env.example
- [x] CI workflow runs on push and PR

## Note

No information from Work-Portfolio-Urgent.md is disclosed in any documentation or code in this repository.
All data is synthetic and built from scratch.