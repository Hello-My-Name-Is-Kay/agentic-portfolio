# Mock Booking API

> **TL;DR** — FastAPI service with 4 endpoints (customer lookup, get/change/cancel reservation). Pydantic v2 request/response models, auto-generated OpenAPI spec at `/openapi.json`, SQLite persistence, optional API key via `X-API-Key`, `Idempotency-Key` on write endpoints (replays the stored response; a reused key for a different request gets 409), and one flat JSON error envelope for every error. Seeded with 2 customers and reservation `R-00001`.

> **Tags:** `fastapi`, `openapi`, `pydantic`, `sqlite`, `idempotency`, `api-key-auth`, `structured-errors`, `mock-service`

A mock car rental reservation API with OpenAPI spec, idempotent writes, and API key authentication.

## Why This Exists

This is the system of record that the [flagship agent](../flagship-agent) and the [MCP server](../mcp-server) call. It gives an agent real write operations (change, cancel) to exercise, with the properties a production booking API would need for safe agent use: input validation, an API key, idempotent retries, and machine-readable errors.

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
                    │   (SQLite)           │
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

| Code | HTTP | When |
|------|------|------|
| `NOT_FOUND` | 404 | Unknown customer or reservation |
| `BAD_INPUT` | 422 | Request body fails validation, or the new drop-off date is not after pickup |
| `INVALID_STATE` | 409 | Changing or cancelling a cancelled reservation |
| `IDEMPOTENCY_CONFLICT` | 409 | `Idempotency-Key` already used for a different request |
| `AUTH_FAILED` | 401 | API key configured and missing/wrong |
| `INTERNAL` | 500 | Unhandled error (no traceback is returned) |

### Idempotency

`PUT /change` and `POST /cancel` accept an `Idempotency-Key` header. The first response is stored for 24 hours together with a hash of the request (action, reservation ID, body). Repeating the same request with the same key returns the stored response without applying the change again; using the key for a different request returns `IDEMPOTENCY_CONFLICT`.

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

Each test starts the app with a fresh in-memory database.

- Customer lookup and get reservation: found, not found.
- Change: success (persisted), not found, invalid date, drop-off before pickup, cancelled reservation.
- Cancel: success, twice (409), not found.
- Idempotency: replay returns the stored response and does not re-apply; reused key for a different request conflicts; records expire.
- API key: open when unset; missing, wrong and correct key when set.
- Error envelope for validation errors, a missing store, and unhandled exceptions; OpenAPI lists the endpoints.
- Store: sequential IDs, partial updates, persistence to a file.

## Endpoints

| Method | Path | Description | Idempotent? |
|--------|------|-------------|-------------|
| GET | `/customers/{id}` | Look up customer | ✓ (read) |
| GET | `/reservations/{id}` | Get reservation details | ✓ (read) |
| PUT | `/reservations/{id}/change` | Change dropoff date | ✓ (Idempotency-Key) |
| POST | `/reservations/{id}/cancel` | Cancel reservation | ✓ (Idempotency-Key) |
| GET | `/health` | Health check | ✓ (read) |
| GET | `/openapi.json` | OpenAPI specification | ✓ (read) |

## Not built yet

- No real authentication (API key is a simple header check, not OAuth).
- No payment processing (mock API by design).
- No create-reservation endpoint (reservations are seeded or created through `BookingStore`).
- No migration framework (the SQLite schema is created on startup; delete `booking.db` after schema changes).
- No per-customer authorization: any valid API key can change any reservation.

## Related Repos

- [mcp-server](../mcp-server) — MCP server wrapping this API.
- [flagship-agent](../flagship-agent) — agent that calls this API as tools.
