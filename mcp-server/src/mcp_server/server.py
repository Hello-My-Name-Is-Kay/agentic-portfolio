"""MCP server with 3 booking API tools.

Tools:
  - get_reservation: look up a reservation by ID.
  - change_reservation: change the drop-off date of a reservation.
  - cancel_reservation: cancel a reservation.

Arguments are validated against the tool schema before a tool runs (for
example, reservation IDs must match ``R-#####``, so they cannot alter the
request path). Once a tool runs, every booking-API outcome, including
timeouts and connection failures, comes back as a JSON string:
``{"status": "ok", "data": ...}`` or ``{"status": "error", "code": ..., "reason": ...}``.
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from mcp_server.logging import configure_logging, get_logger

log = get_logger("mcp-server")

# ─── Configuration ──────────────────────────────────────────────────

BOOKING_API_BASE = os.environ.get("BOOKING_API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("BOOKING_API_KEY", "")
TIMEOUT_S = 15.0

# Tests replace this with an httpx.MockTransport; None means real network.
_transport: httpx.AsyncBaseTransport | None = None

ReservationId = Annotated[
    str, Field(pattern=r"^R-\d{5}$", description="Reservation ID, format 'R-#####', e.g. 'R-00001'")
]
IdempotencyKey = Annotated[
    str,
    Field(min_length=1, max_length=200, description="Caller-generated UUID; reuse the same key when retrying"),
]

server = MCPServer("booking-mcp")


# ─── Helpers ────────────────────────────────────────────────────────


def _ok(data: Any) -> str:
    return json.dumps({"status": "ok", "data": data})


def _error(code: str, reason: str) -> str:
    return json.dumps({"status": "error", "code": code, "reason": reason})


async def _request(
    method: str, path: str, body: dict[str, Any] | None = None, idempotency_key: str | None = None
) -> tuple[int, dict[str, Any]]:
    """Call the booking API. Never raises: transport failures become 502/504 with an error body."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        async with httpx.AsyncClient(
            base_url=BOOKING_API_BASE, timeout=httpx.Timeout(TIMEOUT_S), transport=_transport
        ) as client:
            resp = await client.request(method, path, headers=headers, json=body)
    except httpx.TimeoutException:
        log.warning("api.timeout", method=method, path=path, timeout_s=TIMEOUT_S)
        return 504, {"error": f"Booking API timed out after {TIMEOUT_S:.0f}s"}
    except httpx.RequestError as exc:
        log.warning("api.connection_error", method=method, path=path, error=str(exc))
        return 502, {"error": f"Cannot reach booking API: {exc}"}

    try:
        data = resp.json()
    except ValueError:
        data = {"error": resp.text[:200]}
    return resp.status_code, data if isinstance(data, dict) else {"data": data}


def _to_result(status_code: int, data: dict[str, Any], reservation_id: str) -> str:
    """Map a booking API response to the tool's JSON result."""
    if status_code in (200, 201):
        return _ok(data.get("data", data))
    reason = str(data.get("error") or f"Booking API returned HTTP {status_code}")
    if status_code == 404:
        return _error("NOT_FOUND", f"No reservation '{reservation_id}' found.")
    if status_code in (409, 422, 401):
        default = {409: "INVALID_STATE", 422: "BAD_INPUT", 401: "AUTH_FAILED"}[status_code]
        return _error(str(data.get("error_code") or default), reason)
    if status_code in (502, 503, 504):
        return _error("UPSTREAM_UNAVAILABLE", f"Booking system is temporarily unavailable: {reason}")
    return _error("INTERNAL", f"Booking API returned HTTP {status_code}: {reason}")


# ─── Tools ──────────────────────────────────────────────────────────


@server.tool(structured_output=False)
async def get_reservation(reservation_id: ReservationId) -> str:
    """Look up one reservation by ID: dates, pickup/return locations, vehicle category and status.

    Returns JSON. Error codes: NOT_FOUND (no such reservation), UPSTREAM_UNAVAILABLE
    (booking system down; tell the customer and try later), INTERNAL.
    """
    log.info("tool.get_reservation.call", reservation_id=reservation_id)
    status_code, data = await _request("GET", f"/reservations/{reservation_id}")
    return _to_result(status_code, data, reservation_id)


@server.tool(structured_output=False)
async def change_reservation(
    reservation_id: ReservationId,
    new_dropoff_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO date, e.g. 2025-11-14")],
    idempotency_key: IdempotencyKey,
) -> str:
    """Change the drop-off (return) date of an active reservation. Confirm the new date with the customer first.

    Retrying with the same idempotency_key returns the original result without
    changing anything twice. Error codes: NOT_FOUND, INVALID_STATE (reservation is
    cancelled), BAD_INPUT (date not after pickup), IDEMPOTENCY_CONFLICT (key reused
    for a different change), UPSTREAM_UNAVAILABLE, INTERNAL.
    """
    log.info("tool.change_reservation.call", reservation_id=reservation_id, idempotency_key=idempotency_key)
    status_code, data = await _request(
        "PUT",
        f"/reservations/{reservation_id}/change",
        body={"new_dropoff_date": new_dropoff_date},
        idempotency_key=idempotency_key,
    )
    return _to_result(status_code, data, reservation_id)


@server.tool(structured_output=False)
async def cancel_reservation(
    reservation_id: ReservationId,
    idempotency_key: IdempotencyKey,
    reason: Annotated[str, Field(max_length=500, description="Optional reason for cancellation")] = "",
) -> str:
    """Cancel a reservation. This cannot be undone; confirm with the customer before calling.

    Retrying with the same idempotency_key returns the original result. Error codes:
    NOT_FOUND, INVALID_STATE (already cancelled), IDEMPOTENCY_CONFLICT,
    UPSTREAM_UNAVAILABLE, INTERNAL.
    """
    log.info("tool.cancel_reservation.call", reservation_id=reservation_id, idempotency_key=idempotency_key)
    status_code, data = await _request(
        "POST",
        f"/reservations/{reservation_id}/cancel",
        body={"reason": reason} if reason else {},
        idempotency_key=idempotency_key,
    )
    return _to_result(status_code, data, reservation_id)


# ─── Main Entry Point ───────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio. Logs go to stderr so stdout carries only JSON-RPC."""
    configure_logging()
    log.info("mcp.server.starting", booking_api=BOOKING_API_BASE)
    server.run()


if __name__ == "__main__":
    main()
