# MCP Server

> **TL;DR** — MCP (Model Context Protocol) server, built on the official Python SDK (`mcp` 2.x `MCPServer`), with 3 tools (`get_reservation`, `change_reservation`, `cancel_reservation`). Validated input schemas (e.g. `R-#####` IDs), LLM-oriented tool descriptions, every booking-API outcome returned as structured JSON, idempotency keys on write tools, and a demo that drives the server over stdio with the MCP client. Wraps the [Mock Booking API](../mock-booking-api).

> **Tags:** `mcp`, `tool-design`, `structured-errors`, `idempotency`, `pydantic-schemas`, `llm-docstrings`, `stdio-transport`

Model Context Protocol server exposing rental-booking tools for LLM agents.

## Why This Exists

An agent is only as safe as its tools. This server wraps the booking API in three tools whose schemas and descriptions are the model's only instructions: inputs are validated before any request is made, write tools require an idempotency key so retries cannot double-apply, descriptions tell the model to confirm destructive actions, and every failure comes back as a code the agent can act on instead of an exception.

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
BOOKING_API_BASE=http://localhost:8000 python -m mcp_server.server
```

The server speaks MCP over stdio, so an MCP host (Claude Desktop, Claude Code, an agent framework) launches it as a subprocess. Logs go to stderr; stdout carries only JSON-RPC.

## Output Format

Each tool returns one text content block holding a JSON string: `{"status": "ok", "data": {...}}` or `{"status": "error", "code": "...", "reason": "..."}`.

### Run Demo

`scripts/demo_mcp.py` starts the server as a subprocess, connects with the MCP client over stdio, lists the tools and calls them against a running booking API:

```bash
python scripts/demo_mcp.py          # human-readable
python scripts/demo_mcp.py --json   # full results as JSON
```

Against a fresh booking API it prints:

```
Tools: get_reservation, change_reservation, cancel_reservation

get_reservation(R-99999) -> error NOT_FOUND
get_reservation(R-00001) -> ok active
change_reservation(R-00001) -> ok active
cancel_reservation(R-00001) -> ok cancelled
cancel_reservation(R-00001) -> error INVALID_STATE
```

## Tool Documentation

### `get_reservation`

Look up one reservation by ID.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, must match `R-#####` |

Returns reservation details including dates, status, and vehicle category. Returns `NOT_FOUND` error if the ID doesn't exist.

### `change_reservation`

Change the drop-off date of an existing reservation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, format `R-#####` |
| `new_dropoff_date` | string | ISO date `YYYY-MM-DD`, e.g. `2025-11-14` |
| `idempotency_key` | string | Caller-generated UUID; reuse on retry |

The booking API replays the stored result for a repeated key. Returns `INVALID_STATE` if the reservation is cancelled, `BAD_INPUT` if the date is not after pickup.

### `cancel_reservation`

Cancel a reservation.

| Parameter | Type | Description |
|-----------|------|-------------|
| `reservation_id` | string | Reservation ID, format `R-#####` |
| `idempotency_key` | string | Caller-generated UUID; reuse on retry |
| `reason` | string | Optional reason for cancellation |

Returns `INVALID_STATE` if the reservation is already cancelled.

## Error Handling

Arguments that fail the schema (e.g. `reservation_id="../admin"`, a non-ISO date, a missing idempotency key) are rejected by the MCP SDK with a tool error before any HTTP request is made. Once a tool runs, every outcome, including timeouts and connection failures, is a structured JSON string:

```json
{"status": "error", "code": "NOT_FOUND", "reason": "No reservation 'R-99999' found."}
```

Error codes: `NOT_FOUND`, `INVALID_STATE`, `IDEMPOTENCY_CONFLICT`, `BAD_INPUT`, `AUTH_FAILED`, `UPSTREAM_UNAVAILABLE`, `INTERNAL`.

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

Tests call the tools through `MCPServer.list_tools()` / `call_tool()` as a client would, with the booking API simulated by `httpx.MockTransport` (no network): request method, path, headers and body; mapping of every API error; timeouts and connection errors; schema rejection of bad arguments before any request.

## Not built yet

- No remote hosting (MCP runs over stdio for local agent integration).
- No OAuth (API key forwarded to booking API).
- No streaming (tools are request/response by nature).

## Related Repos

- [mock-booking-api](../mock-booking-api) — The REST API this MCP server wraps.
- [flagship-agent](../flagship-agent) — agent that calls the same booking API.
