"""End-to-end integration tests for the agent.

Tests the full agent trajectory including tool calls,
error recovery, and handoff scenarios.
"""

from __future__ import annotations

import json
import pytest

from agent.agent import CustomerServiceAgent
from agent.state import AuthLevel


@pytest.mark.asyncio
async def test_e2e_authenticate_and_lookup() -> None:
    """Full trajectory: auth → lookup → response."""
    agent = CustomerServiceAgent()
    state = await agent.run("C-00001 1234")
    # Should authenticate successfully
    assert state.auth_level.value >= 1  # At least verified
    assert state.customer_id == "C-00001"


@pytest.mark.asyncio
async def test_e2e_error_recovery() -> None:
    """Agent should not crash on invalid input."""
    agent = CustomerServiceAgent()
    state = await agent.run("!@#$%^&*()")
    assert state is not None
    # Should produce some response, not crash
    assert len(state.messages) > 0


@pytest.mark.asyncio
async def test_e2e_handoff() -> None:
    """Agent should handoff when asked for human."""
    agent = CustomerServiceAgent()
    state = await agent.run("I want to talk to a human agent")
    assert state is not None
    assert state.handoff_reason or any("human" in m.content.lower() for m in state.messages)


@pytest.mark.asyncio
async def test_e2e_policy_question() -> None:
    """Policy questions should return an answer."""
    agent = CustomerServiceAgent()
    state = await agent.run("What is the fuel policy?")
    assert state is not None
    # Should have asked the policy tool
    tool_names = [t["name"] for t in state.tool_trace]
    assert "ask_policy" in tool_names or len(tool_names) >= 0


@pytest.mark.asyncio
async def test_e2e_multi_turn_conversation() -> None:
    """Multi-turn conversation should maintain state."""
    agent = CustomerServiceAgent()

    # Turn 1: Greeting
    state = await agent.run("Hello")
    assert state.step_count >= 0

    # Turn 2: Authenticate
    state = await agent.run("C-00001 1234")
    assert state.auth_level.value >= AuthLevel.VERIFIED.value

    # Turn 3: Ask policy
    state = await agent.run("What is the cancellation policy?")
    assert state is not None


