"""MCP tool tests. The booking API is simulated with httpx.MockTransport (no network)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mcp_server import server

RESERVATION = {"id": "R-00001", "status": "active", "return_date": "2025-11-07"}


class FakeBookingApi:
    """Records requests and answers like the mock booking API."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.next: httpx.Response | Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.next, Exception):
            raise self.next
        if self.next is not None:
            return self.next
        if "R-99999" in request.url.path:
            return httpx.Response(404, json={"status": "error", "error": "not found", "error_code": "NOT_FOUND"})
        return httpx.Response(200, json={"status": "ok", "data": RESERVATION})


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeBookingApi:
    fake = FakeBookingApi()
    monkeypatch.setattr(server, "_transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(server, "API_KEY", "secret")
    return fake


async def call(name: str, **arguments: Any) -> dict[str, Any]:
    """Call a tool through the MCP server, as a client would, and decode its JSON text."""
    result = await server.server.call_tool(name, arguments)
    return json.loads(result.content[0].text)  # type: ignore[union-attr]


async def test_lists_three_tools_with_schemas() -> None:
    tools = {t.name: t for t in await server.server.list_tools()}
    assert set(tools) == {"get_reservation", "change_reservation", "cancel_reservation"}
    change = tools["change_reservation"].input_schema
    assert set(change["required"]) == {"reservation_id", "new_dropoff_date", "idempotency_key"}
    assert change["properties"]["reservation_id"]["pattern"] == r"^R-\d{5}$"
    assert "reason" not in tools["cancel_reservation"].input_schema["required"]
    assert "cannot be undone" in (tools["cancel_reservation"].description or "")


async def test_get_reservation_ok(api: FakeBookingApi) -> None:
    assert await call("get_reservation", reservation_id="R-00001") == {"status": "ok", "data": RESERVATION}
    req = api.requests[0]
    assert (req.method, str(req.url)) == ("GET", "http://localhost:8000/reservations/R-00001")
    assert req.headers["X-API-Key"] == "secret"


@pytest.mark.usefixtures("api")
async def test_get_reservation_not_found() -> None:
    result = await call("get_reservation", reservation_id="R-99999")
    assert result == {"status": "error", "code": "NOT_FOUND", "reason": "No reservation 'R-99999' found."}


async def test_change_sends_body_and_idempotency_key(api: FakeBookingApi) -> None:
    result = await call(
        "change_reservation", reservation_id="R-00001", new_dropoff_date="2025-11-14", idempotency_key="k1"
    )
    assert result["status"] == "ok"
    req = api.requests[0]
    assert (req.method, req.url.path) == ("PUT", "/reservations/R-00001/change")
    assert req.headers["Idempotency-Key"] == "k1"
    assert json.loads(req.content) == {"new_dropoff_date": "2025-11-14"}


async def test_cancel_with_and_without_reason(api: FakeBookingApi) -> None:
    await call("cancel_reservation", reservation_id="R-00001", idempotency_key="k2", reason="plans changed")
    await call("cancel_reservation", reservation_id="R-00001", idempotency_key="k3")
    assert [json.loads(r.content) for r in api.requests] == [{"reason": "plans changed"}, {}]
    assert api.requests[0].url.path == "/reservations/R-00001/cancel"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(409, json={"error": "already cancelled", "error_code": "INVALID_STATE"}), "INVALID_STATE"),
        (
            httpx.Response(409, json={"error": "key reused", "error_code": "IDEMPOTENCY_CONFLICT"}),
            "IDEMPOTENCY_CONFLICT",
        ),
        (httpx.Response(422, json={"error": "date before pickup", "error_code": "BAD_INPUT"}), "BAD_INPUT"),
        (httpx.Response(401, json={"error": "Invalid API key"}), "AUTH_FAILED"),
        (httpx.Response(503, text="maintenance"), "UPSTREAM_UNAVAILABLE"),
        (httpx.Response(500, json=["unexpected"]), "INTERNAL"),
    ],
)
async def test_api_errors_mapped(api: FakeBookingApi, response: httpx.Response, code: str) -> None:
    api.next = response
    result = await call("cancel_reservation", reservation_id="R-00001", idempotency_key="k")
    assert (result["status"], result["code"]) == ("error", code)


@pytest.mark.parametrize(
    ("exc", "reason"),
    [(httpx.ReadTimeout("slow"), "timed out"), (httpx.ConnectError("refused"), "Cannot reach booking API")],
)
async def test_transport_failures_become_upstream_unavailable(api: FakeBookingApi, exc: Exception, reason: str) -> None:
    api.next = exc
    result = await call("get_reservation", reservation_id="R-00001")
    assert result["code"] == "UPSTREAM_UNAVAILABLE"
    assert reason in result["reason"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"reservation_id": "../admin"},
        {"reservation_id": "R-1"},
        {"reservation_id": "R-00001", "new_dropoff_date": "next friday", "idempotency_key": "k"},
        {"reservation_id": "R-00001", "new_dropoff_date": "2025-11-14"},
    ],
)
async def test_invalid_arguments_rejected_before_any_request(api: FakeBookingApi, arguments: dict[str, Any]) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    name = "get_reservation" if len(arguments) == 1 else "change_reservation"
    with pytest.raises(ToolError):
        await server.server.call_tool(name, arguments)
    assert api.requests == []
