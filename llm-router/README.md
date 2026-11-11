# LLM Router

> **TL;DR** — Multi-provider LLM router with a fallback chain (Anthropic → OpenAI → Ollama). Per-provider timeouts, tenacity retries with exponential backoff for transient errors, an in-memory LRU response cache, token/cost budget enforcement, and structured JSON logs on every call. Fallback, retry and budget behaviour are tested with injected failures against mocked HTTP.

> **Tags:** `llm-router`, `fallback-chain`, `provider-protocol`, `retry`, `response-cache`, `budget`, `structured-logging`, `resilience-testing`

Multi-provider LLM router with fallback chain, retry per provider, response caching, token/cost budgets, and structured observability.

## Why This Exists

A production LLM feature should not go down because one provider is slow, rate-limited or out of credit. `Router.generate()` tries providers in order (for example Claude, then OpenAI, then a local model), retries transient failures within each provider, serves repeated prompts from a cache, and refuses further calls once a token or cost budget is used up. Every call is logged with provider, latency, tokens and estimated cost.

## Behaviour

| Concern | What the code does |
|---------|--------------------|
| Fallback | Providers are tried in list order; any `ProviderError` (or unexpected exception) moves on to the next. If all fail, `AllProvidersFailedError` lists each provider's error. |
| Retry | Per provider, via tenacity: timeouts, connection errors, HTTP 429 and 5xx are retried `max_retries` times with exponential backoff (capped at 4s). 401 and other 4xx are not retried. |
| Timeout | Per-provider `timeout_s` on every HTTP call. |
| Cache | In-memory LRU keyed by provider + model + prompt, with TTL. Hits are returned with `cached=True` and cost nothing. |
| Budget | Tracks tokens in/out and estimated cost. A call that pushes a total over its limit raises `BudgetExceededError` after the response is recorded; once a limit is reached, later calls are refused before any provider is called. |
| Cost | An estimate from per-million-token rates passed to each provider (defaults are list prices at the time of writing; Ollama is 0). |

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

The CLI builds the chain from `ROUTER_*` settings: Anthropic and OpenAI are added when their API keys are set, and the local Ollama provider is always last. Logs go to stderr, so `--json` output on stdout is clean.

```bash
# Human-readable output
python -m llm_router.cli "Hello!"

# JSON output for LLM consumption
python -m llm_router.cli "Hello!" --json
```

### Programmatic Usage

```python
import asyncio
from llm_router.router import Router
from llm_router.providers import AnthropicProvider, OpenAIProvider, OllamaProvider

router = Router(
    providers=[
        AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-5"),
        OpenAIProvider(api_key="sk-proj-...", model="gpt-4o-mini"),
        OllamaProvider(base_url="http://localhost:11434", model="llama3.2"),
    ]
)

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

All tests run offline: providers are tested against `httpx.MockTransport`, the router against fake providers.

- **Fallback:** primary fails → secondary; primary + secondary fail → tertiary; all fail → `AllProvidersFailedError` with every message; unexpected exceptions also fall back.
- **Retry:** 429/500/503 retried then succeed; timeouts retried `max_retries` times then raised; 401/400 not retried.
- **Providers:** request URL, headers and payload for each API; response parsing, token counts and cost; invalid bodies.
- **Cache:** hit returns `cached=True` without calling the provider; TTL expiry; LRU eviction order.
- **Budget:** counters; each limit; calls refused before reaching a provider once the budget is spent.
- **CLI:** chain built from settings; JSON and text output; error exit code.

## Not built yet

- Streaming responses.
- Cost- or latency-based routing (the order is fixed).
- A metrics endpoint; observability is structured logs only.
- A shared cache (the cache is per process, in memory).

## Related Repos

- [rag-local](../rag-local) — RAG pipeline that uses the router for generation.
- [eval-harness](../eval-harness) — golden-dataset evaluation that a router-backed pipeline can be scored with.
