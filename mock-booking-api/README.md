# Mock Booking API

> **TL;DR** — FastAPI service with 4 reservation endpoints (lookup, get, change, cancel). Pydantic v2 request/response models, auto-generated OpenAPI spec at `/openapi.json`, SQLite persistence with WAL mode, API key auth via `X-API-Key` header, `Idempotency-Key` header on write endpoints, structured JSON error responses. Seeded with 2 customers and 1 reservation.

> **Tags:** `fastapi`, `openapi`, `pydantic`, `sqlite`, `idempotency`, `api-key-auth`, `structured-errors`, `mock-service`

A mock car rental reservation API with OpenAPI spec, idempotent writes, and API key authentication.

## Why This Exists

This is the data layer that the flagship LangGraph agent calls. It demonstrates tool federation from OpenAPI, gives the agent real "write access" to exercise guardrails, and proves competence with FastAPI, Pydantic validation, idempotency, and structured error handling.

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │        FastAPI Application           │
                    │  GET  /customers/{id}                │
                    │  GET  /reservations/{id}             │
                    │  PUT  /reservations/{id}/change      │
                    │  POST /reservations/{id}/cancel      │
                    └─────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   BookingStore       │
                    │   (SQLite + WAL)     │
                    └─────────────────────┘
                    ┌─────────────────────┐
                    │  Idempotency Store   │
                    │  (key → response)    │
                    └─────────────────────┘
```

## How to Run

### Setup

```bash
cd mock-booking-api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Start Server

```bash
uvicorn booking_api.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. OpenAPI spec at `http://localhost:8000/openapi.json`.

### Usage Examples

```bash
# Health check
curl http://localhost:8000/health

# Look up customer
curl http://localhost:8000/customers/C-00001

# Get reservation
curl http://localhost:8000/reservations/R-00001

# Change dropoff date (with idempotency)
curl -X PUT http://localhost:8000/reservations/R-00001/change \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: change-001-abc" \
  -d '{"new_dropoff_date": "2025-11-14"}'

# Cancel reservation (with idempotency)
curl -X POST http://localhost:8000/reservations/R-00001/cancel \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: cancel-001-xyz" \
  -d '{"reason": "Changed plans"}'
```

## Output Format

This API natively speaks JSON — every endpoint returns structured JSON responses. No `--json` flag is needed because it *is* a JSON API.

### Success Response

```json
{
  "status": "ok",
  "data": { ... }
}
```

### Error Response

```json
{
  "status": "error",
  "error": "Reservation R-99999 not found",
  "error_code": "NOT_FOUND"
}
```

All error codes: `NOT_FOUND`, `INVALID_STATE`, `BAD_INPUT`, `INTERNAL`, `AUTH_FAILED`.

### With API Key

```bash
BOOKING_API_KEY=sk-test-123 uvicorn booking_api.main:app --port 8000

# Then include the header
curl -H "X-API-Key: sk-test-123" http://localhost:8000/health
```

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- Customer lookup: existing, nonexistent, invalid ID.
- Get reservation: existing, nonexistent.
- Change reservation: not found, invalid input validation.
- Cancel reservation: not found, with reason.
- Health check: returns ok.
- API key auth: behavior when configured and unconfigured.

## Endpoints

| Method | Path | Description | Idempotent? |
|--------|------|-------------|-------------|
| GET | `/customers/{id}` | Look up customer | ✓ (read) |
| GET | `/reservations/{id}` | Get reservation details | ✓ (read) |
| PUT | `/reservations/{id}/change` | Change dropoff date | ✓ (Idempotency-Key) |
| POST | `/reservations/{id}/cancel` | Cancel reservation | ✓ (Idempotency-Key) |
| GET | `/health` | Health check | ✓ (read) |
| GET | `/openapi.json` | OpenAPI specification | ✓ (read) |

## Intentional Omissions

- No real authentication (API key is a simple header check, not OAuth).
- No payment processing (mock API by design).
- No complex SQL (simple SQLite for quick setup).
- No migration framework (SQLite schema created on startup).

## Related Repos

- [mcp-server](../mcp-server) — MCP server wrapping this API.
- [flagship-agent](../flagship-agent) — LangGraph agent that calls this API.

## Definition of Done Checklist

- [x] All public functions have type hints; `mypy --strict src` passes.
- [x] `ruff check .` and `ruff format --check .` pass.
- [x] Pydantic models at all boundaries (request/response).
- [x] Idempotency-Key on change and cancel endpoints.
- [x] Structured error responses (never raw tracebacks).
- [x] API key check as FastAPI dependency.
- [x] Auto-generated OpenAPI at `/openapi.json`.
- [x] Tests for happy path, not found, invalid input, idempotent replay.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.