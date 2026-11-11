"""Tools the agent calls.

Every tool returns a JSON string, ``{"status": "ok", ...}`` or
``{"status": "error", "code": ..., "reason": ...}``, and never raises.
Write tools send a deterministic ``Idempotency-Key`` so retries are safe.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field

from agent.logging import get_logger

log = get_logger(__name__)


class AuthenticateArgs(BaseModel):
    """Arguments for ``authenticate``."""

    customer_id: str = Field(..., min_length=1, description="Customer ID, e.g. 'C-00001'")
    pin: str = Field(..., min_length=4, max_length=4, description="Customer PIN (4 digits)")


class ChangeReservationArgs(BaseModel):
    """Arguments for ``change_reservation``."""

    reservation_id: str = Field(..., description="Reservation ID, e.g. 'R-00001'")
    new_dropoff_date: str = Field(..., description="ISO 8601 date, e.g. '2025-11-14'")

    @property
    def idempotency_key(self) -> str:
        """Same change to the same reservation always maps to the same key."""
        return f"change-{self.reservation_id}-{self.new_dropoff_date}"


class CancelReservationArgs(BaseModel):
    """Arguments for ``cancel_reservation``."""

    reservation_id: str = Field(..., description="Reservation ID, e.g. 'R-00001'")
    reason: str = Field(default="", description="Reason for cancellation")

    @property
    def idempotency_key(self) -> str:
        """A reservation can only be cancelled once, so its ID is the key."""
        return f"cancel-{self.reservation_id}"


_POLICIES = {
    "fuel": "The fuel policy is full-to-full. Return the vehicle with a full tank or pay a refuel fee. [Document 4]",
    "cancel": "You can cancel free of charge up to 24 hours before pickup. After that, a fee applies. [Document 3]",
    "insurance": "We offer Damage Waiver ($15/day), Liability Protection ($10/day), and more. [Document 2]",
    "age": "Minimum rental age is 21. Drivers aged 21-24 pay a young-driver surcharge of $20/day. [Document 6]",
    "late": "There is a 30-minute grace period; after that, fees rise from 50% to 200% of the day rate. [Document 12]",
}

_MOCK_CUSTOMERS = {("C-00001", "1234"): "Alice Johnson", ("C-00002", "5678"): "Bob Smith"}


def _ok(**payload: Any) -> str:
    return json.dumps({"status": "ok", **payload})


def _error(code: str, reason: str) -> str:
    return json.dumps({"status": "error", "code": code, "reason": reason})


class AgentTools:
    """Booking and policy tools backed by the mock booking API."""

    def __init__(
        self,
        booking_api_base: str = "http://localhost:8000",
        api_key: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        """Configure the booking API client; ``transport`` lets tests stub the API."""
        self._base = booking_api_base
        self._transport = transport
        self._timeout = httpx.Timeout(timeout_s)
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key

    async def _call_api(
        self, method: str, path: str, json_body: dict[str, Any] | None = None, idem_key: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = dict(self._headers)
        if idem_key:
            headers["Idempotency-Key"] = idem_key
        try:
            async with httpx.AsyncClient(base_url=self._base, transport=self._transport, timeout=self._timeout) as c:
                resp = await c.request(method, path, headers=headers, json=json_body)
            body = resp.json() if resp.content else {}
        except httpx.TimeoutException:
            log.warning("tool.api.timeout", path=path)
            return 504, {}
        except (httpx.RequestError, ValueError) as exc:
            log.warning("tool.api.unreachable", path=path, error=str(exc))
            return 502, {}
        return resp.status_code, body if isinstance(body, dict) else {}

    @staticmethod
    def _api_error(body: dict[str, Any], default: str) -> str:
        detail = body.get("detail", body)
        return str(detail.get("error", default)) if isinstance(detail, dict) else default

    async def authenticate(self, customer_id: str, pin: str) -> str:
        """Verify a customer's ID and PIN (mock store; the PIN is never logged)."""
        log.info("tool.authenticate", customer_id=customer_id)
        if not customer_id.startswith("C-"):
            return _error("BAD_INPUT", "Invalid customer ID format.")
        if len(pin) != 4 or not pin.isdigit():
            return _error("BAD_INPUT", "PIN must be 4 digits.")
        name = _MOCK_CUSTOMERS.get((customer_id, pin))
        if name is None:
            return _error("AUTH_FAILED", "Invalid customer ID or PIN.")
        return _ok(customer={"id": customer_id, "name": name})

    async def lookup_reservation(self, reservation_id: str) -> str:
        """Fetch a reservation by ID."""
        log.info("tool.lookup_reservation", reservation_id=reservation_id)
        code, body = await self._call_api("GET", f"/reservations/{reservation_id}")
        if code == 200:
            return _ok(reservation=body.get("data", body))
        if code == 404:
            return _error("NOT_FOUND", f"No reservation {reservation_id}.")
        return _error("UPSTREAM_UNAVAILABLE", "Booking system unavailable.")

    async def change_reservation(self, reservation_id: str, new_dropoff_date: str) -> str:
        """Move a reservation's drop-off date."""
        args = ChangeReservationArgs(reservation_id=reservation_id, new_dropoff_date=new_dropoff_date)
        log.info("tool.change_reservation", reservation_id=reservation_id, idem_key=args.idempotency_key)
        code, body = await self._call_api(
            "PUT",
            f"/reservations/{reservation_id}/change",
            json_body={"new_dropoff_date": new_dropoff_date},
            idem_key=args.idempotency_key,
        )
        if code == 200:
            return _ok(reservation=body.get("data", body))
        if code == 404:
            return _error("NOT_FOUND", f"No reservation {reservation_id}.")
        if code in (409, 422):
            return _error("INVALID_STATE", self._api_error(body, "That change isn't possible for this reservation."))
        return _error("UPSTREAM_UNAVAILABLE", "Booking system unavailable.")

    async def cancel_reservation(self, reservation_id: str, reason: str = "") -> str:
        """Cancel a reservation."""
        args = CancelReservationArgs(reservation_id=reservation_id, reason=reason)
        log.info("tool.cancel_reservation", reservation_id=reservation_id, idem_key=args.idempotency_key)
        code, body = await self._call_api(
            "POST",
            f"/reservations/{reservation_id}/cancel",
            json_body={"reason": reason},
            idem_key=args.idempotency_key,
        )
        if code == 200:
            return _ok(reservation=body.get("data", body))
        if code == 404:
            return _error("NOT_FOUND", f"No reservation {reservation_id}.")
        if code == 409:
            return _error("INVALID_STATE", self._api_error(body, "This reservation is already cancelled."))
        return _error("UPSTREAM_UNAVAILABLE", "Booking system unavailable.")

    async def ask_policy(self, question: str) -> str:
        """Answer a rental-policy question (keyword stand-in for the rag-local pipeline)."""
        log.info("tool.ask_policy", question=question[:80])
        q = question.lower()
        for key, answer in _POLICIES.items():
            if key in q:
                return _ok(answer=answer)
        return _ok(answer="I don't know based on the available policies. Could you ask about a specific policy?")
