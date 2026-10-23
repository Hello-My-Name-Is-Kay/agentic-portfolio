"""FastAPI application for the Mock Booking API.

Provides 4 endpoints:
  - GET /customers/{customer_id} — Look up a customer
  - GET /reservations/{reservation_id} — Get a reservation
  - PUT /reservations/{reservation_id}/change — Change dropoff date
  - POST /reservations/{reservation_id}/cancel — Cancel reservation

With API key authentication, idempotency on change/cancel,
auto-generated OpenAPI spec at /openapi.json.
"""

from __future__ import annotations

from booking_api.logging import get_logger
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from booking_api.errors import AuthError, BookingError, NotFoundError
from booking_api.models import (
    ApiResponse,
    CancelReservationRequest,
    ChangeReservationRequest,
    Reservation,
    ReservationCreate,
    ReservationUpdate,
)
from booking_api.store import BookingStore

log = get_logger(__name__)

# --- Globals (set during lifespan) ---
store: BookingStore | None = None
API_KEY: str = ""


def verify_api_key(x_api_key: str = Header("", alias="X-API-Key")) -> None:
    """Dependency: validate the API key on every request."""
    if not API_KEY:
        return  # no key configured — allow all
    if x_api_key != API_KEY:
        log.warning("auth.key_rejected", key_preview=x_api_key[:8] if x_api_key else "none")
        raise HTTPException(status_code=401, detail={"status": "error", "error": "Invalid API key"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize store and seed data."""
    global store, API_KEY
    db_path = os.environ.get("BOOKING_DB_PATH", "booking.db")
    API_KEY = os.environ.get("BOOKING_API_KEY", "")

    store = BookingStore(db_path=db_path)

    # Seed some customers
    store.seed_customers([
        {"id": "C-00001", "name": "Alice Johnson", "email": "alice@example.com",
         "phone": "555-0101", "drivers_license": "DL-USA-12345"},
        {"id": "C-00002", "name": "Bob Smith", "email": "bob@example.com",
         "phone": "555-0102", "drivers_license": "DL-USA-67890"},
    ])

    # Seed a reservation for testing
    from booking_api.models import ReservationCreate
    store.create_reservation(ReservationCreate(
        customer_id="C-00001",
        pickup_location_id="L-0001",
        return_location_id="L-0001",
        pickup_date=date(2025, 11, 1),
        return_date=date(2025, 11, 7),
        vehicle_category="Standard",
    ))

    log.info("Mock Booking API initialized with seeded data")
    yield


app = FastAPI(
    title="Mock Rental Booking API",
    description="A mock car rental reservation API for agent tool-federation demos.\n\n"
                "This API simulates a real booking system with idempotent writes, "
                "structured error responses, and an auto-generated OpenAPI spec.",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ────────────────────────────────────────────────────────

def _ok(data: dict | list | None = None) -> ApiResponse:
    return ApiResponse(status="ok", data=data)


def _error(code: str, msg: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ApiResponse(status="error", error=msg, error_code=code).model_dump(),
    )


def _handle_request_error(exc: BookingError, status_code: int = 400):
    """Map BookingErrors to HTTP responses."""
    if isinstance(exc, NotFoundError):
        raise _error("NOT_FOUND", str(exc), 404)
    raise _error("REQUEST_ERROR", str(exc), status_code)


# ─── Idempotency middleware ─────────────────────────────────────────

async def get_idempotency_key(x_idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    return x_idempotency_key


# ─── Endpoints ──────────────────────────────────────────────────────

@app.get("/customers/{customer_id}", response_model=ApiResponse)
async def lookup_customer(customer_id: str) -> Any:
    """Look up a customer by ID."""
    if store is None:
        raise _error("INTERNAL", "Store not initialized", 500)
    customer = store.get_customer(customer_id)
    if customer is None:
        raise _error("NOT_FOUND", f"Customer {customer_id} not found", 404)
    return _ok(customer)


@app.get("/reservations/{reservation_id}", response_model=ApiResponse)
async def get_reservation(reservation_id: str) -> Any:
    """Get reservation details by ID."""
    if store is None:
        raise _error("INTERNAL", "Store not initialized", 500)
    reservation = store.get_reservation(reservation_id)
    if reservation is None:
        raise _error("NOT_FOUND", f"Reservation {reservation_id} not found", 404)
    return _ok(reservation)


@app.put("/reservations/{reservation_id}/change", response_model=ApiResponse)
async def change_reservation(
    reservation_id: str,
    body: ChangeReservationRequest,
    idem_key: str | None = Depends(get_idempotency_key),
) -> Any:
    """Change the drop-off date of an existing reservation.

    Accepts an Idempotency-Key header for safe retries.
    """
    if store is None:
        raise _error("INTERNAL", "Store not initialized", 500)

    if idem_key:
        cached = store.get_idempotent(idem_key)
        if cached is not None:
            log.info("idempotency.replay", key=idem_key)
            return _ok(cached)

    existing = store.get_reservation(reservation_id)
    if existing is None:
        raise _error("NOT_FOUND", f"Reservation {reservation_id} not found", 404)

    if existing["status"] == "cancelled":
        raise _error("INVALID_STATE", f"Cannot change a cancelled reservation", 409)

    # Update the return_date to the new dropoff date
    update = ReservationUpdate(new_return_date=body.new_dropoff_date)
    result = store.update_reservation(reservation_id, update)
    if result is None:
        raise _error("NOT_FOUND", f"Reservation {reservation_id} not found", 404)

    if idem_key:
        store.put_idempotent(idem_key, result)

    return _ok(result)


@app.post("/reservations/{reservation_id}/cancel", response_model=ApiResponse)
async def cancel_reservation(
    reservation_id: str,
    body: CancelReservationRequest | None = None,
    idem_key: str | None = Depends(get_idempotency_key),
) -> Any:
    """Cancel a reservation.

    Accepts an Idempotency-Key header for safe retries.
    """
    if store is None:
        raise _error("INTERNAL", "Store not initialized", 500)

    if idem_key:
        cached = store.get_idempotent(idem_key)
        if cached is not None:
            log.info("idempotency.replay", key=idem_key)
            return _ok(cached)

    existing = store.get_reservation(reservation_id)
    if existing is None:
        raise _error("NOT_FOUND", f"Reservation {reservation_id} not found", 404)

    if existing["status"] == "cancelled":
        raise _error("INVALID_STATE", f"Reservation {reservation_id} is already cancelled", 409)

    result = store.cancel_reservation(reservation_id)
    if result is None:
        raise _error("NOT_FOUND", f"Reservation {reservation_id} not found", 404)

    if idem_key:
        store.put_idempotent(idem_key, result)

    return _ok(result)


@app.get("/health", response_model=ApiResponse)
async def health_check() -> Any:
    """Health check endpoint."""
    return _ok({"status": "healthy", "store_initialized": store is not None})