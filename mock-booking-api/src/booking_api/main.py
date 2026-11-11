"""FastAPI application for the Mock Booking API.

Endpoints:
  - GET  /customers/{customer_id}             look up a customer
  - GET  /reservations/{reservation_id}       get a reservation
  - PUT  /reservations/{reservation_id}/change change the drop-off date
  - POST /reservations/{reservation_id}/cancel cancel a reservation
  - GET  /health

Optional API key (``BOOKING_API_KEY``), ``Idempotency-Key`` on change/cancel,
OpenAPI spec at /openapi.json. Every error is returned as
``{"status": "error", "error": ..., "error_code": ...}``.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from booking_api.logging import get_logger
from booking_api.models import (
    ApiResponse,
    CancelReservationRequest,
    ChangeReservationRequest,
    ReservationCreate,
    ReservationUpdate,
)
from booking_api.store import BookingStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

log = get_logger(__name__)

SEED_CUSTOMERS = [
    {
        "id": "C-00001",
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "phone": "555-0101",
        "drivers_license": "DL-USA-12345",
    },
    {
        "id": "C-00002",
        "name": "Bob Smith",
        "email": "bob@example.com",
        "phone": "555-0102",
        "drivers_license": "DL-USA-67890",
    },
]


class ApiError(Exception):
    """An error returned to the client in the standard envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        """Create an error with a machine-readable code and HTTP status."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the store, seed 2 customers and reservation R-00001, close on shutdown."""
    store = BookingStore(db_path=os.environ.get("BOOKING_DB_PATH", "booking.db"))
    store.seed_customers(SEED_CUSTOMERS)
    if store.get_reservation("R-00001") is None:
        store.create_reservation(
            ReservationCreate(
                customer_id="C-00001",
                pickup_location_id="L-0001",
                return_location_id="L-0001",
                pickup_date=date(2025, 11, 1),
                return_date=date(2025, 11, 7),
                vehicle_category="Standard",
            )
        )
    app.state.store = store
    app.state.api_key = os.environ.get("BOOKING_API_KEY", "")
    log.info("booking_api.started", api_key_required=bool(app.state.api_key))
    yield
    app.state.store = None
    store.close()


def verify_api_key(request: Request, x_api_key: str = Header("", alias="X-API-Key")) -> None:
    """Reject the request unless it carries the configured API key (no key configured = open)."""
    expected: str = getattr(request.app.state, "api_key", "")
    if expected and not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        log.warning("auth.key_rejected", path=request.url.path)
        raise ApiError("AUTH_FAILED", "Invalid API key", 401)


def get_store(request: Request) -> BookingStore:
    """Return the store opened by the lifespan handler."""
    store: BookingStore | None = getattr(request.app.state, "store", None)
    if store is None:
        raise ApiError("INTERNAL", "Store not initialized", 500)
    return store


app = FastAPI(
    title="Mock Rental Booking API",
    description="A mock car rental reservation API for agent tool-calling demos.\n\n"
    "Idempotent writes, structured error responses, and an auto-generated OpenAPI spec.",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    body = ApiResponse(status="error", error=message, error_code=code).model_dump()
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(ApiError)
async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return _error_response(exc.code, exc.message, exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()))
    return _error_response("BAD_INPUT", f"{where}: {first.get('msg', 'invalid input')}", 422)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("booking_api.unhandled", path=request.url.path, error=str(exc))
    return _error_response("INTERNAL", "Internal server error", 500)


def _ok(data: dict[str, Any]) -> ApiResponse:
    return ApiResponse(status="ok", data=data)


def get_idempotency_key(idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> str | None:
    """Read the optional Idempotency-Key header."""
    return idempotency_key


def _fingerprint(action: str, reservation_id: str, body: dict[str, Any]) -> str:
    raw = json.dumps({"action": action, "reservation_id": reservation_id, "body": body}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _replay(store: BookingStore, idem_key: str | None, fingerprint: str) -> dict[str, Any] | None:
    """Return the stored response for a repeated request; 409 if the key was used for a different one."""
    if not idem_key:
        return None
    record = store.get_idempotent(idem_key)
    if record is None:
        return None
    stored_fingerprint, response = record
    if stored_fingerprint != fingerprint:
        raise ApiError("IDEMPOTENCY_CONFLICT", "Idempotency-Key was already used for a different request", 409)
    log.info("idempotency.replay", key=idem_key)
    return response


def _existing_reservation(store: BookingStore, reservation_id: str) -> dict[str, Any]:
    existing = store.get_reservation(reservation_id)
    if existing is None:
        raise ApiError("NOT_FOUND", f"Reservation {reservation_id} not found", 404)
    return existing


# ─── Endpoints ──────────────────────────────────────────────────────


@app.get("/customers/{customer_id}", response_model=ApiResponse)
async def lookup_customer(customer_id: str, store: BookingStore = Depends(get_store)) -> ApiResponse:
    """Look up a customer by ID."""
    customer = store.get_customer(customer_id)
    if customer is None:
        raise ApiError("NOT_FOUND", f"Customer {customer_id} not found", 404)
    return _ok(customer)


@app.get("/reservations/{reservation_id}", response_model=ApiResponse)
async def get_reservation(reservation_id: str, store: BookingStore = Depends(get_store)) -> ApiResponse:
    """Get reservation details by ID."""
    return _ok(_existing_reservation(store, reservation_id))


@app.put("/reservations/{reservation_id}/change", response_model=ApiResponse)
async def change_reservation(
    reservation_id: str,
    body: ChangeReservationRequest,
    idem_key: str | None = Depends(get_idempotency_key),
    store: BookingStore = Depends(get_store),
) -> ApiResponse:
    """Change the drop-off date of an active reservation. Safe to retry with an Idempotency-Key."""
    fingerprint = _fingerprint("change", reservation_id, body.model_dump())
    replayed = _replay(store, idem_key, fingerprint)
    if replayed is not None:
        return _ok(replayed)

    existing = _existing_reservation(store, reservation_id)
    if existing["status"] == "cancelled":
        raise ApiError("INVALID_STATE", "Cannot change a cancelled reservation", 409)
    if body.new_dropoff_date <= date.fromisoformat(existing["pickup_date"]):
        raise ApiError("BAD_INPUT", "new_dropoff_date must be after the pickup date", 422)

    result = store.update_reservation(reservation_id, ReservationUpdate(new_return_date=body.new_dropoff_date)) or {}
    if idem_key:
        store.put_idempotent(idem_key, fingerprint, result)
    log.info("reservation.changed", reservation_id=reservation_id, new_dropoff_date=str(body.new_dropoff_date))
    return _ok(result)


@app.post("/reservations/{reservation_id}/cancel", response_model=ApiResponse)
async def cancel_reservation(
    reservation_id: str,
    body: CancelReservationRequest | None = None,
    idem_key: str | None = Depends(get_idempotency_key),
    store: BookingStore = Depends(get_store),
) -> ApiResponse:
    """Cancel an active reservation. Safe to retry with an Idempotency-Key."""
    fingerprint = _fingerprint("cancel", reservation_id, body.model_dump() if body else {})
    replayed = _replay(store, idem_key, fingerprint)
    if replayed is not None:
        return _ok(replayed)

    existing = _existing_reservation(store, reservation_id)
    if existing["status"] == "cancelled":
        raise ApiError("INVALID_STATE", f"Reservation {reservation_id} is already cancelled", 409)

    result = store.cancel_reservation(reservation_id) or {}
    if idem_key:
        store.put_idempotent(idem_key, fingerprint, result)
    log.info("reservation.cancelled", reservation_id=reservation_id)
    return _ok(result)


@app.get("/health", response_model=ApiResponse)
async def health_check(request: Request) -> ApiResponse:
    """Health check endpoint."""
    return _ok({"status": "healthy", "store_initialized": getattr(request.app.state, "store", None) is not None})
