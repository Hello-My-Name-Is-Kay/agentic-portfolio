"""Shared fixtures: an in-memory fake of the mock booking API, so no test touches the network."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from agent.agent import CustomerServiceAgent
from agent.config import AgentSettings
from agent.tools import AgentTools
from fakes import FakeBookingApi


def _reservation(rid: str, customer_id: str) -> dict[str, Any]:
    return {
        "id": rid,
        "customer_id": customer_id,
        "pickup_date": "2025-11-01",
        "return_date": "2025-11-07",
        "vehicle_category": "Standard",
        "status": "confirmed",
    }


@pytest.fixture
def api() -> FakeBookingApi:
    return FakeBookingApi(
        reservations={"R-00001": _reservation("R-00001", "C-00001"), "R-00002": _reservation("R-00002", "C-00002")}
    )


@pytest.fixture
def tools(api: FakeBookingApi) -> AgentTools:
    return AgentTools(booking_api_base="http://booking.test", transport=httpx.MockTransport(api.handler))


@pytest.fixture
def agent(tools: AgentTools) -> CustomerServiceAgent:
    return CustomerServiceAgent(settings=AgentSettings(max_steps=6), tools=tools)
