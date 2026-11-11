"""Tool contracts: structured JSON results, error codes, and idempotency keys."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.nodes import classify
from agent.tools import AgentTools, AuthenticateArgs, CancelReservationArgs, ChangeReservationArgs
from fakes import FakeBookingApi


async def test_authenticate_accepts_valid_credentials(tools: AgentTools) -> None:
    data = json.loads(await tools.authenticate("C-00001", "1234"))
    assert data == {"status": "ok", "customer": {"id": "C-00001", "name": "Alice Johnson"}}


@pytest.mark.parametrize(
    ("cid", "pin", "code"),
    [("C-00001", "0000", "AUTH_FAILED"), ("bad-id", "1234", "BAD_INPUT"), ("C-00001", "12a4", "BAD_INPUT")],
)
async def test_authenticate_rejects(tools: AgentTools, cid: str, pin: str, code: str) -> None:
    data = json.loads(await tools.authenticate(cid, pin))
    assert data["status"] == "error"
    assert data["code"] == code


async def test_lookup_found_and_not_found(tools: AgentTools) -> None:
    assert json.loads(await tools.lookup_reservation("R-00001"))["reservation"]["customer_id"] == "C-00001"
    assert json.loads(await tools.lookup_reservation("R-99999"))["code"] == "NOT_FOUND"


async def test_api_outage_maps_to_upstream_unavailable(tools: AgentTools, api: FakeBookingApi) -> None:
    api.down = True
    assert json.loads(await tools.lookup_reservation("R-00001"))["code"] == "UPSTREAM_UNAVAILABLE"
    assert json.loads(await tools.change_reservation("R-00001", "2025-11-14"))["code"] == "UPSTREAM_UNAVAILABLE"
    assert json.loads(await tools.cancel_reservation("R-00001"))["code"] == "UPSTREAM_UNAVAILABLE"


async def test_unreachable_api_never_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    tools = AgentTools(booking_api_base="http://booking.test", transport=httpx.MockTransport(boom))
    assert json.loads(await tools.lookup_reservation("R-00001"))["code"] == "UPSTREAM_UNAVAILABLE"


async def test_timeout_never_raises() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    tools = AgentTools(booking_api_base="http://booking.test", transport=httpx.MockTransport(slow))
    assert json.loads(await tools.lookup_reservation("R-00001"))["code"] == "UPSTREAM_UNAVAILABLE"


async def test_cancel_retry_is_idempotent(tools: AgentTools, api: FakeBookingApi) -> None:
    first = json.loads(await tools.cancel_reservation("R-00001"))
    retry = json.loads(await tools.cancel_reservation("R-00001"))
    assert first["status"] == retry["status"] == "ok"
    keys = {r.headers["Idempotency-Key"] for r in api.writes()}
    assert keys == {"cancel-R-00001"}


async def test_change_on_cancelled_reservation_is_invalid_state(tools: AgentTools, api: FakeBookingApi) -> None:
    api.reservations["R-00001"]["status"] = "cancelled"
    data = json.loads(await tools.change_reservation("R-00001", "2025-11-14"))
    assert data == {"status": "error", "code": "INVALID_STATE", "reason": "Reservation is cancelled"}
    assert json.loads(await tools.cancel_reservation("R-00009"))["code"] == "NOT_FOUND"


async def test_policy_answers_and_falls_back(tools: AgentTools) -> None:
    assert "full-to-full" in json.loads(await tools.ask_policy("What is the fuel policy?"))["answer"]
    assert "don't know" in json.loads(await tools.ask_policy("Do you rent boats?"))["answer"]


def test_idempotency_keys_are_deterministic() -> None:
    change = ChangeReservationArgs(reservation_id="R-00001", new_dropoff_date="2025-11-14")
    assert change.idempotency_key == "change-R-00001-2025-11-14"
    assert CancelReservationArgs(reservation_id="R-00001").idempotency_key == "cancel-R-00001"


def test_authenticate_args_validate() -> None:
    with pytest.raises(ValueError, match="at least"):
        AuthenticateArgs(customer_id="", pin="")


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("What is the cancellation policy?", "policy"),
        ("Please cancel R-00001", "cancel"),
        ("Can I extend R-00001 to 2025-11-14?", "change"),
        ("Check reservation R-00001", "lookup"),
        ("I want to talk to a human", "handoff"),
        ("Hello there", "greeting"),
        ("I'd like to extend my booking", "change"),
        ("!@#$%", "unknown"),
    ],
)
def test_classify(text: str, intent: str) -> None:
    assert classify(text) == intent
