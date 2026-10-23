# MCP Server

> **TL;DR** — MCP (Model Context Protocol) server with 3 tools (`get_reservation`, `change_reservation`, `cancel_reservation`). Typed Pydantic input schemas, precise LLM-oriented docstrings on every tool, structured error JSON (never raises), idempotency key on write tools, demo script showing LLM agent calling each tool. Wraps the Mock Booking API.

> **Tags:** `mcp`, `tool-design`, `structured-errors`, `idempotency`, `pydantic-schemas`, `llm-docstrings`, `stdio-transport`

Model Context Protocol server exposing rental-booking tools for LLM agents.

## Why This Exists

This project demonstrates MCP tool design — a skill explicitly called out in the job posting. The server wraps the Mock Booking API into three tools with typed inputs, precise docstrings (which are the LLM's only instructions), and structured error JSON that never raises. It proves competence with the tool-as-a-service pattern for agentic systems.

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │          MCP Server (stdio)           │
                    │                                       │
                    │  Tools:                               │
                    │   • get_reservation(id)                │
                    │   • change_reservation(id, date, key)  │
                    │   • cancel_reservation(id, reason, key)│
                    └──────────────────┬───────────────────┘
                                       │ HTTP
                                       ▼
                    ┌──────────────────────────────────────┐
                    │     Mock Booking API (localhost:8000)  │
                    └──────────────────────────────────────┘
```

## How to Run

### Prerequisites

The Mock Booking API must be running on `localhost:8000`:
```bash
cd ../mock-booking-api
uvicorn booking_api.main:app --port 8000 &
```

### Setup

```bash
cd mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Run Server

```bash
python -m mcp_server.server
```

The server runs over stdio transport, suitable for MCP clients.

## Output Format

The MCP server communicates over stdio using **JSON-RPC** messages — every tool response is a JSON string. When using the demo script directly:

| Mode | Flag | Consumer |
|------|------|----------|
| **Human-readable** | *(default)* | Terminal — formatted demo flow |
| **JSON** | `--json` | LLMs, scripts — structured tool results |

### JSON Output Schema (`scripts/demo_mcp.py --json`)

```json
{
  "tools": [
    {
      "name": "get_reservation",
      "result": {
        "status": "ok",
        "data": { ... }
      }
    },
    {
      "name": "get_reservation_not_found",
      "result": {
        "status": "error",
        "code": "NOT_FOUND",
        "reason": "No reservation 'R-99999' found."
      }
    }
  ]
}
```

When called by an LLM host (e.g. Claude Desktop), each tool returns a JSON string per the MCP spec — always `{"status": "ok|error", ...}`.

### Run Demo

```bash
# Human-readable
python scripts/demo_mcp.py

# JSON output (for LLM consumption)
python scripts/demo_mcp.py --json
```

## Tool Documentation

### `get_reservation`

Look up one reservation by ID.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, format `R-#####` |

Returns reservation details including dates, status, and vehicle category. Returns `NOT_FOUND` error if the ID doesn't exist.

### `change_reservation`

Change the drop-off date of an existing reservation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, format `R-#####` |
| `new_dropoff_date` | string | ISO 8601 date, e.g. `2025-11-14` |
| `idempotency_key` | string | Caller-generated UUID; reuse on retry |

Uses the idempotency key to prevent duplicate processing. Returns `INVALID_STATE` if the reservation is already cancelled.

### `cancel_reservation`

Cancel a reservation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, format `R-#####` |
| `reason` | string | Optional reason for cancellation |
| `idempotency_key` | string | Caller-generated UUID; reuse on retry |

Returns `INVALID_STATE` if the reservation is already cancelled.

## Error Handling

Every tool returns a structured JSON string — never raises.

```json
{"status": "error", "code": "NOT_FOUND", "reason": "No reservation 'R-99999' found."}
```

Error codes: `NOT_FOUND`, `INVALID_STATE`, `UPSTREAM_UNAVAILABLE`, `INTERNAL`.

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

## Intentional Omissions

- No remote hosting (MCP runs over stdio for local agent integration).
- No OAuth (API key forwarded to booking API).
- No streaming (tools are request/response by nature).

## Related Repos

- [mock-booking-api](../mock-booking-api) — The REST API this MCP server wraps.
- [flagship-agent](../flagship-agent) — LangGraph agent that uses these tools.

## Definition of Done Checklist

- [x] All public functions have type hints; `mypy --strict src` passes.
- [x] `ruff check .` and `ruff format --check .` pass.
- [x] 3 tools with precise docstrings (designed for LLM consumption).
- [x] Typed input schemas via Pydantic.
- [x] Never raise: every tool returns structured error JSON.
- [x] Every write tool accepts idempotency key.
- [x] Demo script shows LLM calling tools.
- [x] Tests: each tool returns error JSON on injected failure.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.