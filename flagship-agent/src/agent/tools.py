"""Tools for the flagship agent.

Each tool:
  - Returns a structured JSON string (never raises)
  - Logs with context
  - Accepts typed Pydantic args
  - Includes idempotency on write operations

Tools:
  - authenticate(customer_id, pin) — Verify customer identity
  - lookup_reservation(reservation_id) — Get reservation details
  - change_reservation(reservation_id, new_dropoff_date) — Change dropoff date
  - cancel_reservation(reservation_id, reason) — Cancel a reservation
  - ask_policy(question) — Ask a policy question via RAG
"""

from __future__ import annotations

import json
from agent.logging import get_logger
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field

log = get_logger(__name__)


# ─── Tool Arguments (Pydantic) ─────────────────────────────────────

class AuthenticateArgs(BaseModel):
    customer_id: str = Field(..., description="Customer ID, e.g. 'C-00001'")
    pin: str = Field(..., description="Customer PIN (4 digits)")


class LookupReservationArgs(BaseModel):
    reservation_id: str = Field(..., description="Reservation ID, e.g. 'R-00001'")


class ChangeReservationArgs(BaseModel):
    reservation_id: str = Field(..., description="Reservation ID, e.g. 'R-00001'")
    new_dropoff_date: str = Field(..., description="ISO 8601 date, e.g. '2025-11-14'")

    @property
    def idempotency_key(self) -> str:
        return f"change-{self.reservation_id}-{self.new_dropoff_date}"


class CancelReservationArgs(BaseModel):
    reservation_id: str = Field(..., description="Reservation ID, e.g. 'R-00001'")
    reason: str = Field(default="", description="Reason for cancellation")

    @property
    def idempotency_key(self) -> str:
        return f"cancel-{self.reservation_id}-{uuid.uuid4().hex[:8]}"


class AskPolicyArgs(BaseModel):
    question: str = Field(..., description="Policy question to ask")


# ─── Tool Implementations ──────────────────────────────────────────

class AgentTools:
    """Collection of tools that the agent can call.

    Each method returns a JSON string with {"status": "ok", ...} or
    {"status": "error", "code": "...", "reason": "..."}.

    Never raises.
    """

    def __init__(self, booking_api_base: str = "http://localhost:8000", api_key: str = "") -> None:
        self._base = booking_api_base
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key

    async def _call_api(self, method: str, path: str, json_body: dict | None = None, extra_headers: dict | None = None) -> tuple[int, Any]:
        """Make an API call to the booking service."""
        headers = dict(self._headers)
        if extra_headers:
            headers.update(extra_headers)

        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=json_body)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=json_body)
                else:
                    return 500, {"error": f"Unsupported method {method}"}
                data = resp.json() if resp.text else {}
                return resp.status_code, data
        except httpx.TimeoutException:
            return 504, {"error": "Upstream API timed out"}
        except httpx.RequestError as exc:
            return 502, {"error": f"Cannot reach API: {exc}"}
        except Exception as exc:
            log.exception("API call failed")
            return 500, {"error": str(exc)}

    async def authenticate(self, customer_id: str, pin: str) -> str:
        """Authenticate a customer.

        In production, this would verify against a secure store.
        For MVP, accepts C-00001/pin=1234 as the test customer.
        """
        log.info("tool.authenticate", customer_id=customer_id)
        if not customer_id or not customer_id.startswith("C-"):
            return json.dumps({"status": "error", "code": "BAD_INPUT", "reason": "Invalid customer ID format."})
        if not pin or len(pin) != 4 or not pin.isdigit():
            return json.dumps({"status": "error", "code": "BAD_INPUT", "reason": "PIN must be 4 digits."})

        # Mock authentication
        if customer_id == "C-00001" and pin == "1234":
            return json.dumps({"status": "ok", "customer": {
                "id": "C-00001", "name": "Alice Johnson", "auth_level": "verified"
            }})
        if customer_id == "C-00002" and pin == "5678":
            return json.dumps({"status": "ok", "customer": {
                "id": "C-00002", "name": "Bob Smith", "auth_level": "verified"
            }})

        return json.dumps({"status": "error", "code": "AUTH_FAILED", "reason": "Invalid customer ID or PIN."})

    async def lookup_reservation(self, reservation_id: str) -> str:
        """Look up a reservation by ID."""
        log.info("tool.lookup_reservation", reservation_id=reservation_id)
        status_code, data = await self._call_api("GET", f"/reservations/{reservation_id}")
        api_data = data.get("data", data) if isinstance(data, dict) else data

        if status_code == 200:
            return json.dumps({"status": "ok", "reservation": api_data})
        if status_code == 404:
            return json.dumps({"status": "error", "code": "NOT_FOUND", "reason": f"No reservation {reservation_id}."})
        return json.dumps({"status": "error", "code": "UPSTREAM_UNAVAILABLE", "reason": "Booking system unavailable."})

    async def change_reservation(self, reservation_id: str, new_dropoff_date: str) -> str:
        """Change the drop-off date."""
        idem_key = ChangeReservationArgs(reservation_id=reservation_id, new_dropoff_date=new_dropoff_date).idempotency_key
        log.info("tool.change_reservation", reservation_id=reservation_id, idem_key=idem_key)

        status_code, data = await self._call_api(
            "PUT", f"/reservations/{reservation_id}/change",
            json_body={"new_dropoff_date": new_dropoff_date},
            extra_headers={"Idempotency-Key": idem_key},
        )
        api_data = data.get("data", data) if isinstance(data, dict) else data

        if status_code == 200:
            return json.dumps({"status": "ok", "reservation": api_data})
        if status_code == 404:
            return json.dumps({"status": "error", "code": "NOT_FOUND", "reason": f"No reservation {reservation_id}."})
        if status_code == 409:
            err = data.get("error", "Cannot change in current state.") if isinstance(data, dict) else str(data)
            return json.dumps({"status": "error", "code": "INVALID_STATE", "reason": err})
        return json.dumps({"status": "error", "code": "UPSTREAM_UNAVAILABLE", "reason": "Booking system unavailable."})

    async def cancel_reservation(self, reservation_id: str, reason: str = "") -> str:
        """Cancel a reservation."""
        idem_key = CancelReservationArgs(reservation_id=reservation_id, reason=reason).idempotency_key
        log.info("tool.cancel_reservation", reservation_id=reservation_id, idem_key=idem_key)

        status_code, data = await self._call_api(
            "POST", f"/reservations/{reservation_id}/cancel",
            json_body={"reason": reason},
            extra_headers={"Idempotency-Key": idem_key},
        )
        api_data = data.get("data", data) if isinstance(data, dict) else data

        if status_code == 200:
            return json.dumps({"status": "ok", "reservation": api_data})
        if status_code == 404:
            return json.dumps({"status": "error", "code": "NOT_FOUND", "reason": f"No reservation {reservation_id}."})
        if status_code == 409:
            err = data.get("error", "Already cancelled.") if isinstance(data, dict) else str(data)
            return json.dumps({"status": "error", "code": "INVALID_STATE", "reason": err})
        return json.dumps({"status": "error", "code": "UPSTREAM_UNAVAILABLE", "reason": "Booking system unavailable."})

    async def ask_policy(self, question: str) -> str:
        """Ask a policy question (simulated RAG response)."""
        log.info("tool.ask_policy", question=question[:80])
        # Simulated RAG response (in production, calls rag-local pipeline)
        responses = {
            "fuel": "The fuel policy is full-to-full. Return the vehicle with a full tank or pay a refueling fee. [Document 4]",
            "cancellation": "You can cancel free up to 24 hours before pickup. After that, a fee applies. [Document 3]",
            "insurance": "We offer Damage Waiver ($15/day), Liability Protection ($10/day), and more. [Document 2]",
            "age": "Minimum rental age is 21. Drivers 21-24 pay a young driver surcharge of $20/day. [Document 6]",
            "late": "30-minute grace period, then fees escalate from 50% to 200% of daily rate. [Document 12]",
        }
        q_lower = question.lower()
        for key, response in responses.items():
            if key in q_lower:
                return json.dumps({"status": "ok", "answer": response})

        return json.dumps({
            "status": "ok",
            "answer": "I don't know based on the available policies. Please ask a more specific question about our rental policies. [Document 1]"
        })