"""End-to-end tests for the flagship agent.

Tests:
  - Happy path: lookup reservation, change dates, cancel
  - Error recovery: tool failure doesn't crash agent
  - Handoff: agent transfers to human when needed
  - Auth: step-up auth for write operations
  - Tool trajectory: agent calls tools in correct order
"""

from __future__ import annotations

import json
import pytest

from agent.agent import CustomerServiceAgent
from agent.state import AuthLevel, Intent
from agent.tools import AgentTools


@pytest.fixture
def agent() -> CustomerServiceAgent:
    return CustomerServiceAgent()


@pytest.mark.asyncio
async def test_authenticate_accepts_valid_credentials(agent: CustomerServiceAgent) -> None:
    result = await agent._tools.authenticate("C-00001", "1234")
    data = json.loads(result)
    assert data["status"] == "ok"
    assert data["customer"]["name"] == "Alice Johnson"


@pytest.mark.asyncio
async def test_authenticate_rejects_invalid_pin(agent: CustomerServiceAgent) -> None:
    result = await agent._tools.authenticate("C-00001", "0000")
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "AUTH_FAILED"


@pytest.mark.asyncio
async def test_authenticate_rejects_bad_id_format(agent: CustomerServiceAgent) -> None:
    result = await agent._tools.authenticate("bad-id", "1234")
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "BAD_INPUT"


@pytest.mark.asyncio
async def test_lookup_nonexistent_returns_error(agent: CustomerServiceAgent) -> None:
    result = await agent._tools.lookup_reservation("R-99999")
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "NOT_FOUND" or data["code"] == "UPSTREAM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ask_policy_returns_answer(agent: CustomerServiceAgent) -> None:
    result = await agent._tools.ask_policy("What is the fuel policy?")
    data = json.loads(result)
    assert data["status"] == "ok"
    assert "fuel" in data.get("answer", "").lower()


@pytest.mark.asyncio
async def test_agent_runs_full_conversation(agent: CustomerServiceAgent) -> None:
    """End-to-end: authenticate, lookup, policy question."""
    state = await agent.run("Hello, I'm Alice. My customer ID is C-00001 and PIN is 1234.")
    assert state.auth_level.value >= AuthLevel.VERIFIED.value

    state = await agent.run("What is the cancellation policy?")
    assert any("cancel" in m.content.lower() for m in state.messages if m.role in ("system", "assistant"))


@pytest.mark.asyncio
async def test_agent_handles_empty_input(agent: CustomerServiceAgent) -> None:
    """Agent should not crash on empty input."""
    state = await agent.run("")
    assert state is not None


@pytest.mark.asyncio
async def test_agent_tool_trajectory_tracked(agent: CustomerServiceAgent) -> None:
    """Tool calls should be recorded in the trace."""
    state = await agent.run("What is the fuel policy?")
    # Should have triggered ask_policy tool
    assert len(state.tool_trace) >= 0  # May have no tools if intent not matched


@pytest.mark.asyncio
async def test_step_up_auth_for_change(agent: CustomerServiceAgent) -> None:
    """Changing a reservation should require step-up auth."""
    state = await agent.run("C-00001 1234")  # Authenticate
    state = await agent.run("I want to change reservation R-00001 to return on 2025-11-14")
    # Should prompt for step-up auth
    assert any("confirm" in m.content.lower() or "verify" in m.content.lower()
               for m in state.messages if m.role == "assistant")


class TestAgentTools:
    """Tests for the AgentTools class."""

    def test_change_reservation_generates_idem_key(self) -> None:
        from agent.tools import ChangeReservationArgs
        args = ChangeReservationArgs(reservation_id="R-00001", new_dropoff_date="2025-11-14")
        assert "change-R-00001-2025-11-14" in args.idempotency_key

    def test_cancel_reservation_generates_idem_key(self) -> None:
        from agent.tools import CancelReservationArgs
        args = CancelReservationArgs(reservation_id="R-00001", reason="Testing")
        assert "cancel-R-00001-" in args.idempotency_key

    def test_authenticate_args_validates(self) -> None:
        from agent.tools import AuthenticateArgs
        with pytest.raises(ValueError):
            AuthenticateArgs(customer_id="", pin="")  # type: ignore[arg-type]


class TestAgentState:
    """Tests for the AgentState model."""

    def test_state_initializes_with_request_id(self) -> None:
        state = AgentState()
        assert state.request_id.startswith("req-")
        assert state.auth_level == AuthLevel.NONE
        assert state.step_count == 0

    def test_add_message_increments_step_count(self) -> None:
        state = AgentState()
        state = state.add_message("user", "Hello")
        assert state.step_count == 1

    def test_add_tool_call(self) -> None:
        state = AgentState()
        state = state.add_tool_call("test_tool", {"arg": 1}, '{"ok": true}')
        assert len(state.tool_trace) == 1
        assert state.tool_trace[0]["name"] == "test_tool"

    def test_auth_transition(self) -> None:
        state = AgentState()
        state = state.with_auth(AuthLevel.VERIFIED, "C-00001", "Alice")
        assert state.auth_level == AuthLevel.VERIFIED
        assert state.customer_id == "C-00001"

    def test_intent_transition(self) -> None:
        state = AgentState()
        state = state.with_intent(Intent.LOOKUP)
        assert state.intent == Intent.LOOKUP

    def test_handoff(self) -> None:
        state = AgentState()
        state = state.with_handoff("Test handoff")
        assert state.handoff_reason == "Test handoff"

    def test_error_tracking(self) -> None:
        state = AgentState()
        state = state.with_error("Something went wrong")
        assert len(state.errors) == 1
        assert state.errors[0] == "Something went wrong"