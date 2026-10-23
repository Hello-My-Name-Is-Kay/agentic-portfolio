# Flagship Agent — Customer Service LangGraph Agent

> **TL;DR** — LangGraph-inspired state-machine agent with nodes: authenticate → classify_intent → execute_tool (+ step-up auth on writes) → respond → should_continue (loops or handoffs). Tools: authenticate, lookup_reservation, change_reservation (with idempotency key), cancel_reservation (with idempotency key), ask_policy. Step-up auth required for write operations. Handoff to human after 12 steps or on user request. Full tool trajectory tracked in state. This is the **pinned** portfolio project that ties together RAG, booking API, and router skills.

> **Tags:** `langgraph`, `agent`, `state-machine`, `tool-trajectory`, `step-up-auth`, `idempotency`, `handoff`, `error-recovery`, `flagship`

A LangGraph-inspired customer service agent for a fictional car rental company. Authenticates customers, looks up/modifies reservations via tools, answers policy questions, and hands off to humans when needed.

This is the **pinned repo** — the one that demonstrates every skill from the job posting: LangGraph, tool design, error recovery, step-up auth, idempotency, observability, and evals.

## Why This Exists

This is the project that ties together everything in the portfolio. The RAG pipeline provides policy answers. The mock booking API provides the data layer. The router provides model flexibility. The eval harness gates changes. The MCP server exposes tools. And this agent orchestrates it all in a LangGraph loop that hiring managers can run end-to-end.

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │            Agent Loop                     │
                    │                                           │
                    │  ┌────────────┐                           │
                    │  │ authenticate│  Verify customer ID+PIN  │
                    │  └──────┬─────┘                           │
                    │         ▼                                 │
                    │  ┌────────────┐                           │
                    │  │ intent     │  Classify user request    │
                    │  └──────┬─────┘                           │
                    │         ▼                                 │
                    │  ┌────────────┐  ┌──────────────────┐    │
                    │  │ step-up    │  │ if write intent  │    │
                    │  │ auth       │◀─│ re-verify ID+PIN │    │
                    │  └──────┬─────┘  └──────────────────┘    │
                    │         ▼                                 │
                    │  ┌────────────┐                           │
                    │  │ execute    │  Call booking tool/RAG    │
                    │  │ tool       │                           │
                    │  └──────┬─────┘                           │
                    │         ▼                                 │
                    │  ┌────────────┐                           │
                    │  │ respond    │  Natural language reply   │
                    │  └────────────┘                           │
                    │         │                                 │
                    │  ┌──────▼──────┐                          │
                    │  │ should_    │  Continue? Handoff? End?  │
                    │  │ continue   │                           │
                    │  └────────────┘                           │
                    └──────────────────────────────────────────┘
```

## How to Run

### Setup

```bash
cd flagship-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Output Formats

The agent CLI supports two modes:

| Mode | Invocation | Consumer |
|------|-----------|----------|
| **Interactive** (human-readable) | `python -m agent.cli` | Terminal chat |
| **JSON (pipe)** | `echo "C-00001 1234" \| python -m agent.cli --json` | LLMs, scripts |

### JSON Output Schema (`--json`)

```json
{
  "status": "ok | error",
  "request_id": "req-abc12345",
  "customer_id": "C-00001",
  "customer_name": "Alice Johnson",
  "auth_level": "verified",
  "intent": "lookup",
  "steps": 3,
  "handoff": false,
  "handoff_reason": null,
  "tool_trajectory": ["authenticate", "lookup_reservation"],
  "errors": [],
  "final_response": "Your reservation...",
  "conversation": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

On error, `"status": "error"` with a `"reason"` field.

### Interactive CLI

```bash
python -m agent.cli
```

Then try conversations like:

```
You: Hello
You: C-00001 1234
You: What is the fuel policy?
You: I want to change reservation R-00001
You: talk to a human
```

### Programmatic Usage

```python
import asyncio
from agent.agent import CustomerServiceAgent

async def main():
    agent = CustomerServiceAgent()
    state = await agent.run("C-00001 1234")
    print(f"Authenticated: {state.customer_name}")

    state = await agent.run("What is the fuel policy?")
    for msg in state.messages:
        if msg.role == "assistant":
            print(f"Agent: {msg.content}")

asyncio.run(main())
```

## Tool Trajectories

The agent tracks every tool call in `state.tool_trace`:

```python
[tc["name"] for tc in state.tool_trace]
# → ["authenticate", "lookup_reservation", "ask_policy"]
```

## State Model

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | str | Unique request ID for tracing |
| `auth_level` | Enum | NONE → BASIC → VERIFIED → STEP_UP |
| `intent` | Enum | UNKNOWN, LOOKUP, CHANGE, CANCEL, POLICY, HANDSHAKE, HANDOFF |
| `step_count` | int | Monotonically increasing; handoff at 12 |
| `tool_trace` | list[dict] | Every tool call with args and result |
| `errors` | list[str] | Captured errors for diagnostics |
| `handoff_reason` | str or None | Set when human transfer is needed |

## Testing

```bash
# Unit tests
pytest tests/unit

# Integration tests
pytest tests/integration

# Full suite with coverage
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- **Auth**: valid/invalid credentials, bad ID format.
- **Tools**: lookup nonexistent returns error, policy questions return answers.
- **State model**: request_id, step count, tool trace, auth transitions, handoff, errors.
- **Idempotency**: change/cancel generate deterministic idempotency keys.
- **End-to-end**: full auth→lookup→policy trajectory.
- **Error recovery**: agent doesn't crash on invalid input.
- **Handoff**: agent transfers when asked or step limit exceeded.
- **Multi-turn**: state persists across conversation turns.

## Intentional Omissions

- No LangGraph framework dependency (pure Python state machine for self-containment).
- No streaming (request/response loop for MVP).
- No real LLM call for natural language generation (rule-based responses).
- No real RAG integration (simulated policy answers — real RAG in rag-local repo).

## Related Repos

- [rag-local](../rag-local) — RAG pipeline for policy answers.
- [mock-booking-api](../mock-booking-api) — Data layer for this agent.
- [mcp-server](../mcp-server) — MCP interface to the same booking tools.
- [llm-router](../llm-router) — Multi-provider router for LLM calls.
- [eval-harness](../eval-harness) — Eval suite that gates agent changes.
- [guardrails](../guardrails) — Red-team suite that hardens the agent.

## Definition of Done Checklist

- [x] Graph nodes: authenticate → intent → tools | handoff → respond.
- [x] Step-up auth before any write tool (change/cancel require re-auth).
- [x] `recursion_limit` set at 25; node-level counter hands off at 12.
- [x] Every tool returns structured errors, never raises.
- [x] Idempotency key generated per write intent.
- [x] End-to-end test asserting tool trajectory + error recovery + handoff.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] README documents architecture, usage, trajectory, and results.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print (in production code), no commented-out code, no TODO.