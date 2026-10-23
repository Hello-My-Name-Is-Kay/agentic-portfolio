# LLM Router

> **TL;DR** — Multi-provider LLM router with fallback chain (Anthropic → OpenAI → Ollama). Per-provider timeouts, tenacity retry with exponential backoff, in-memory LRU response cache, token/cost budget enforcement, structured JSON logging on every call with provider/latency/tokens/cost. Proves fallback resilience with injected-failure tests.

> **Tags:** `llm-router`, `fallback-chain`, `provider-protocol`, `retry`, `response-cache`, `budget`, `structured-logging`, `resilience-testing`

Multi-provider LLM router with fallback chain, retry per provider, response caching, token/cost budgets, and structured observability.

## Why This Exists

The job posting explicitly names "multi-provider fallbacks" as a required skill. This repo delivers exactly that: a `Router.generate()` method that tries Claude, then OpenAI, then a local model, with per-provider timeouts, retry budgets, a response cache, and a hard cap on total attempts. Every call is logged with provider, latency, tokens, and cost — making every effect traceable.

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │              Router.generate()             │
                    └──────┬──────────────┬──────────────┬─────┘
                           │              │              │
                           ▼              ▼              ▼
                    ┌──────────┐  ┌──────────┐  ┌──────────┐
                    │ Anthropic │  │  OpenAI  │  │  Ollama  │
                    │  Claude   │  │ GPT-4o   │  │ llama3.2 │
                    └─────┬────┘  └─────┬────┘  └─────┬────┘
                          │              │              │
                          └──────────────┴──────────────┘
                                     │
                                     ▼
                          ┌────────────────────┐
                          │  ResponseCache      │  LRU with TTL
                          └────────────────────┘
                          ┌────────────────────┐
                          │  Budget             │  token/cost enforcement
                          └────────────────────┘
                          ┌────────────────────┐
                          │  structlog          │  JSON logs per call
                          └────────────────────┘
```

## How to Run

### Setup

```bash
cd llm-router
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your API keys
```

### CLI Usage

```bash
# Human-readable output (calls the local Ollama provider)
python -m llm_router.cli "Hello!"

# JSON output for LLM consumption
python -m llm_router.cli "Hello!" --json
```

### Programmatic Usage

```python
import asyncio
from llm_router.router import Router
from llm_router.providers import AnthropicProvider, OpenAIProvider, OllamaProvider

router = Router(providers=[
    AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5"),
    OpenAIProvider(api_key="sk-proj-...", model="gpt-4o-mini"),
    OllamaProvider(base_url="http://localhost:11434", model="llama3.2"),
])

resp = asyncio.run(router.generate("Hello!", request_id="demo-001"))
print(f"[{resp.provider}] {resp.text}")
print(f"tokens: {resp.tokens_in}→{resp.tokens_out}, cost: ${resp.cost_usd:.6f}")
```

## Output Formats

The CLI supports two output modes via the `--json` flag:

| Mode | Flag | Consumer |
|------|------|----------|
| **Human-readable** | *(default)* | Terminal — shows provider, text, latency, tokens, cost |
| **JSON** | `--json` | LLMs, scripts — structured fields for programmatic use |

### JSON Output Schema (`--json`)

```json
{
  "status": "ok | error",
  "provider": "ollama",
  "model": "llama3.2",
  "text": "Generated response...",
  "latency_ms": 1234.5,
  "tokens_in": 45,
  "tokens_out": 120,
  "cost_usd": 0.0,
  "cached": false
}
```

### Testing

```bash
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- **Happy path:** primary provider succeeds.
- **Fallback:** primary fails → secondary succeeds.
- **Full fallback chain:** primary + secondary fail → tertiary succeeds.
- **All providers fail:** raises `AllProvidersFailed` with all error messages.
- **Cache hit:** identical prompt returns cached response without calling any provider.
- **Empty prompt guard:** raises `ProviderError`.
- **Budget tracking:** token in/out and cost counters update correctly.
- **Budget exceeded:** raises `BudgetExceeded` when over limit.
- **Cache TTL:** expired entries are not returned.
- **Cache max size:** LRU eviction works.
- **Budget reset:** counters clear correctly.

## Intentional Omissions

- No streaming support (MVP uses non-streaming for simplicity).
- No cost-based routing (always tries primary first).
- No dashboard or metrics endpoint (Prometheus integration planned).
- No authentication or SSRF guardrails (handled in the deployment layer).

## Related Repos

- [rag-local](../rag-local) — RAG pipeline that uses the router for generation.
- [eval-harness](../eval-harness) — Evaluates router behavior under failure scenarios.

## Definition of Done Checklist

- [x] All public functions have type hints; `mypy --strict src` passes.
- [x] `ruff check .` and `ruff format --check .` pass.
- [x] Every except block logs with context and raises typed exceptions.
- [x] Every external call has timeout and retry policy (tenacity).
- [x] Every LLM call logs provider, latency, tokens, and cost.
- [x] Every failure branch has a corresponding test.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] README documents results and usage.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.
- [x] Configuration via pydantic-settings with `.env.example`.
- [x] Provider Protocol pattern for testable seams.