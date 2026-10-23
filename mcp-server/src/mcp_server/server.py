"""MCP server definition with 3 Booking API tools.

Tools:
  - get_reservation: Look up a reservation by ID.
  - change_reservation: Change the drop-off date of a reservation.
  - cancel_reservation: Cancel a reservation.

Every tool follows the pattern:
  - Accepts Pydantic-validated input.
  - Returns JSON string — never raises.
  - Structured error JSON on failure.
  - Logs every call with context.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server import Server, stdio_server
from mcp.types import Tool, TextContent, CallToolResult
from pydantic import BaseModel, Field

from mcp_server.logging import configure_logging, get_logger

log = get_logger("mcp-server")

# ─── Configuration ──────────────────────────────────────────────────

BOOKING_API_BASE = os.environ.get("BOOKING_API_BASE", "http://localhost:8000")
API_KEY = os.environ.get("BOOKING_API_KEY", "")

_HEADERS: dict[str, str] = {"Content-Type": "application/json"}
if API_KEY:
    _HEADERS["X-API-Key"] = API_KEY

_TIMEOUT_S = 15.0


# ─── Tool Input Schemas ────────────────────────────────────────────

class GetReservationArgs(BaseModel):
    reservation_id: str = Field(
        ..., description="Reservation ID, format 'R-#####' e.g. 'R-00001'"
    )


class ChangeReservationArgs(BaseModel):
    reservation_id: str = Field(
        ..., description="Reservation ID, format 'R-#####' e.g. 'R-00001'"
    )
    new_dropoff_date: str = Field(
        ..., description="ISO 8601 date, e.g. '2025-11-14'"
    )
    idempotency_key: str = Field(
        ..., description="Caller-generated UUID; reuse on retry for safe idempotent replay"
    )


class CancelReservationArgs(BaseModel):
    reservation_id: str = Field(
        ..., description="Reservation ID, format 'R-#####' e.g. 'R-00001'"
    )
    reason: str = Field(default="", description="Optional reason for cancellation")
    idempotency_key: str = Field(
        ..., description="Caller-generated UUID; reuse on retry for safe idempotent replay"
    )


# ─── Server Setup ──────────────────────────────────────────────────

server = Server("booking-mcp")


def _make_ok(data: Any) -> str:
    """Wrap result in a success JSON string."""
    return json.dumps({"status": "ok", "data": data})


def _make_error(code: str, reason: str) -> str:
    """Wrap error in a structured JSON string for the agent to consume."""
    return json.dumps({"status": "error", "code": code, "reason": reason})


async def _call_api(method: str, path: str, json_body: dict | None = None) -> tuple[int, Any]:
    """Make an HTTP request to the booking API.

    Returns (status_code, response_data).
    Never raises — returns structured error info on failure.
    """
    url = f"{BOOKING_API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_S)) as client:
            if method == "GET":
                resp = await client.get(url, headers=_HEADERS)
            elif method == "PUT":
                resp = await client.put(url, headers=_HEADERS, json=json_body)
            elif method == "POST":
                resp = await client.post(url, headers=_HEADERS, json=json_body)
            else:
                return (500, {"status": "error", "error": f"Unsupported method {method}"})
            resp.raise_for_status()
            return (resp.status_code, resp.json())
    except httpx.TimeoutException:
        log.warning("api.timeout", method=method, path=path, timeout_s=_TIMEOUT_S)
        return (504, {"status": "error", "error": "Upstream API timed out"})
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except (json.JSONDecodeError, ValueError):
            detail = {"status": "error", "error": exc.response.text[:200]}
        return (exc.response.status_code, detail)
    except httpx.RequestError as exc:
        log.warning("api.connection_error", method=method, path=path, error=str(exc))
        return (502, {"status": "error", "error": f"Cannot reach booking API: {exc}"})
    except Exception as exc:
        log.exception("api.unexpected_error", method=method, path=path)
        return (500, {"status": "error", "error": f"Unexpected error: {exc}"})


# ─── Tool Implementations ──────────────────────────────────────────

async def _get_reservation(reservation_id: str) -> str:
    """Look up a reservation by ID.

    Args:
        reservation_id: The reservation ID from the customer, format 'R-#####'.

    Returns:
        JSON string. On success: {"status":"ok","data":{...}}.
        On not found: {"status":"error","code":"NOT_FOUND",...}.
        On upstream outage: {"status":"error","code":"UPSTREAM_UNAVAILABLE",...}.

    Never raises.
    """
    log.info("tool.get_reservation.call", reservation_id=reservation_id)
    status_code, data = await _call_api("GET", f"/reservations/{reservation_id}")

    if status_code == 200:
        return _make_ok(data.get("data", data))
    if status_code == 404:
        return _make_error("NOT_FOUND", f"No reservation '{reservation_id}' found.")
    if status_code in (502, 504):
        return _make_error("UPSTREAM_UNAVAILABLE", "Booking system is temporarily unavailable.")
    return _make_error("INTERNAL", f"Unexpected status {status_code}: {data.get('error', str(data))}")


async def _change_reservation(reservation_id: str, new_dropoff_date: str, idempotency_key: str) -> str:
    """Change the drop-off date of an existing reservation.

    Args:
        reservation_id: The reservation ID, format 'R-#####'.
        new_dropoff_date: ISO 8601 date for the new drop-off date.
        idempotency_key: UUID for safe retry; reuse the same key if you retry.

    Returns:
        JSON string. On success: {"status":"ok","data":{...}}.
        On not found: {"status":"error","code":"NOT_FOUND",...}.
        On upstream outage: {"status":"error","code":"UPSTREAM_UNAVAILABLE",...}.

    Never raises. Uses idempotency key to prevent duplicate processing.
    """
    log.info("tool.change_reservation.call", reservation_id=reservation_id, idem_key=idempotency_key)

    headers_with_idem = dict(_HEADERS)
    headers_with_idem["Idempotency-Key"] = idempotency_key

    url = f"{BOOKING_API_BASE}/reservations/{reservation_id}/change"
    body = {"new_dropoff_date": new_dropoff_date}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_S)) as client:
            resp = await client.put(url, headers=headers_with_idem, json=body)
            if resp.status_code in (200, 201):
                data = resp.json()
                return _make_ok(data.get("data", data))
            detail = resp.json() if resp.text else {}
            if resp.status_code == 404:
                return _make_error("NOT_FOUND", f"No reservation '{reservation_id}' found.")
            if resp.status_code == 409:
                return _make_error("INVALID_STATE", detail.get("error", f"Cannot change reservation '{reservation_id}' in its current state."))
            return _make_error("INTERNAL", f"Booking API returned {resp.status_code}: {detail.get('error', resp.text[:200])}")
    except httpx.TimeoutException:
        return _make_error("UPSTREAM_UNAVAILABLE", "Booking system timed out. Do not retry more than once.")
    except httpx.RequestError as exc:
        return _make_error("UPSTREAM_UNAVAILABLE", f"Booking system unavailable: {exc}")
    except Exception as exc:
        log.exception("tool.change_reservation.unexpected")
        return _make_error("INTERNAL", f"Unexpected error: {exc}")


async def _cancel_reservation(reservation_id: str, reason: str, idempotency_key: str) -> str:
    """Cancel a reservation.

    Args:
        reservation_id: The reservation ID, format 'R-#####'.
        reason: Optional reason for cancellation.
        idempotency_key: UUID for safe retry; reuse the same key if you retry.

    Returns:
        JSON string. On success: {"status":"ok","data":{...}}.
        On not found: {"status":"error","code":"NOT_FOUND",...}.
        On already cancelled: {"status":"error","code":"INVALID_STATE",...}.

    Never raises.
    """
    log.info("tool.cancel_reservation.call", reservation_id=reservation_id, idem_key=idempotency_key)

    headers_with_idem = dict(_HEADERS)
    headers_with_idem["Idempotency-Key"] = idempotency_key
    body = {"reason": reason} if reason else {}

    url = f"{BOOKING_API_BASE}/reservations/{reservation_id}/cancel"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_S)) as client:
            resp = await client.post(url, headers=headers_with_idem, json=body)
            if resp.status_code in (200, 201):
                data = resp.json()
                return _make_ok(data.get("data", data))
            detail = resp.json() if resp.text else {}
            if resp.status_code == 404:
                return _make_error("NOT_FOUND", f"No reservation '{reservation_id}' found.")
            if resp.status_code == 409:
                return _make_error("INVALID_STATE", detail.get("error", f"Reservation '{reservation_id}' is already cancelled."))
            return _make_error("INTERNAL", f"Booking API returned {resp.status_code}: {detail.get('error', resp.text[:200])}")
    except httpx.TimeoutException:
        return _make_error("UPSTREAM_UNAVAILABLE", "Booking system timed out.")
    except httpx.RequestError as exc:
        return _make_error("UPSTREAM_UNAVAILABLE", f"Booking system unavailable: {exc}")
    except Exception as exc:
        log.exception("tool.cancel_reservation.unexpected")
        return _make_error("INTERNAL", f"Unexpected error: {exc}")


# ─── Tool Registration ─────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_reservation",
            description="Look up one reservation by ID. Returns reservation details including dates, status, and vehicle category.",
            inputSchema=GetReservationArgs.model_json_schema(),
        ),
        Tool(
            name="change_reservation",
            description="Change the drop-off date of an existing reservation. Use an idempotency key so retrying is safe.",
            inputSchema=ChangeReservationArgs.model_json_schema(),
        ),
        Tool(
            name="cancel_reservation",
            description="Cancel a reservation. Use an idempotency key so retrying is safe. Returns the cancelled reservation data.",
            inputSchema=CancelReservationArgs.model_json_schema(),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch to the appropriate tool handler."""
    log.info("tool.call", name=name, args=arguments)

    try:
        if name == "get_reservation":
            args = GetReservationArgs(**arguments)
            result = await _get_reservation(args.reservation_id)
        elif name == "change_reservation":
            args = ChangeReservationArgs(**arguments)
            result = await _change_reservation(args.reservation_id, args.new_dropoff_date, args.idempotency_key)
        elif name == "cancel_reservation":
            args = CancelReservationArgs(**arguments)
            result = await _cancel_reservation(args.reservation_id, args.reason, args.idempotency_key)
        else:
            result = _make_error("UNKNOWN_TOOL", f"No tool named '{name}'.")
    except Exception as exc:
        log.exception("tool.call.unexpected_error", name=name)
        result = _make_error("INTERNAL", f"Unexpected error in tool handler: {exc}")

    return [TextContent(type="text", text=result)]


# ─── Main Entry Point ──────────────────────────────────────────────

def main() -> None:
    """Run the MCP server over stdio transport."""
    configure_logging()
    log.info("mcp.server.starting", booking_api=BOOKING_API_BASE)
    server.run(stdio_server())


if __name__ == "__main__":
    main()