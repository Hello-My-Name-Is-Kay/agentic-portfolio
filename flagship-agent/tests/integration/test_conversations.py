"""Multi-turn conversations through the compiled LangGraph, asserting tool trajectories."""

from __future__ import annotations

import json

from agent.agent import CustomerServiceAgent, last_reply, trajectory
from agent.cli import run_json
from agent.config import AgentSettings
from agent.graph import build_graph
from agent.intent import KeywordClassifier
from agent.tools import AgentTools
from fakes import FakeBookingApi


async def test_graph_has_expected_nodes(tools: AgentTools) -> None:
    nodes = set(build_graph(tools, AgentSettings(), KeywordClassifier()).compile().get_graph().nodes)
    assert {"start_turn", "authenticate", "classify_intent", "run_account_tool", "request_step_up"} <= nodes


async def test_lookup_requires_authentication(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    state = await agent.run("Check reservation R-00001", thread_id="t")
    assert "verify you" in last_reply(state)
    assert trajectory(state) == []
    assert api.requests == []


async def test_authenticate_then_lookup_remembers_session(agent: CustomerServiceAgent) -> None:
    state = await agent.run("Hi, I'm C-00001, PIN 1234", thread_id="t")
    assert state["auth_level"] == "verified"
    assert "Alice Johnson" in last_reply(state)

    state = await agent.run("Check reservation R-00001", thread_id="t")
    assert trajectory(state) == ["authenticate", "lookup_reservation"]
    assert "R-00001: Standard, pickup 2025-11-01, return 2025-11-07" in last_reply(state)


async def test_pending_lookup_resumes_after_credentials(agent: CustomerServiceAgent) -> None:
    await agent.run("What's the status of R-00001?", thread_id="t")
    state = await agent.run("C-00001 1234", thread_id="t")
    assert trajectory(state) == ["authenticate", "lookup_reservation"]
    assert "status confirmed" in last_reply(state)


async def test_change_requires_step_up_then_writes_once(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    await agent.run("C-00001 1234", thread_id="t")
    state = await agent.run("Please extend R-00001 to 2025-11-14", thread_id="t")
    assert "confirm your Customer ID and PIN again" in last_reply(state)
    assert api.writes() == []

    state = await agent.run("C-00001 1234", thread_id="t")
    assert trajectory(state) == ["authenticate", "authenticate", "lookup_reservation", "change_reservation"]
    assert "now returns on 2025-11-14" in last_reply(state)
    assert api.reservations["R-00001"]["return_date"] == "2025-11-14"
    assert [r.headers["Idempotency-Key"] for r in api.writes()] == ["change-R-00001-2025-11-14"]
    assert state["auth_level"] == "verified"  # step-up was consumed


async def test_step_up_with_wrong_pin_does_not_write(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    await agent.run("C-00001 1234", thread_id="t")
    await agent.run("Cancel R-00001", thread_id="t")
    state = await agent.run("C-00001 9999", thread_id="t")
    assert "didn't match" in last_reply(state)
    assert "confirm your Customer ID and PIN again to cancel" in last_reply(state)
    assert api.writes() == []


async def test_cancel_before_login_needs_one_credential_entry(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    state = await agent.run("I need to cancel R-00001", thread_id="t")
    assert "verify you" in last_reply(state)
    state = await agent.run("C-00001 1234", thread_id="t")
    assert trajectory(state) == ["authenticate", "lookup_reservation", "cancel_reservation"]
    assert api.reservations["R-00001"]["status"] == "cancelled"


async def test_cannot_touch_another_customers_reservation(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    await agent.run("C-00001 1234", thread_id="t")
    await agent.run("Cancel R-00002", thread_id="t")
    state = await agent.run("C-00001 1234", thread_id="t")
    assert "couldn't find reservation R-00002 on your account" in last_reply(state)
    assert trajectory(state)[-1] == "lookup_reservation"
    assert api.writes() == []


async def test_missing_details_are_asked_for(agent: CustomerServiceAgent) -> None:
    await agent.run("C-00001 1234", thread_id="t")
    state = await agent.run("I want to change my reservation", thread_id="t")
    assert "Which reservation" in last_reply(state)
    state = await agent.run("R-00001", thread_id="t")
    assert "new return date" in last_reply(state)
    state = await agent.run("2025-11-20", thread_id="t")
    assert "confirm your Customer ID and PIN again to change" in last_reply(state)


async def test_unknown_reservation_and_outage_are_handled(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    await agent.run("C-00001 1234", thread_id="t")
    state = await agent.run("Check R-12345", thread_id="t")
    assert "couldn't find reservation R-12345" in last_reply(state)

    api.down = True
    state = await agent.run("Check R-00001", thread_id="t")
    assert "isn't responding" in last_reply(state)
    assert state["errors"][-1] == "Booking system unavailable."


async def test_failed_write_is_reported(agent: CustomerServiceAgent, api: FakeBookingApi) -> None:
    api.reservations["R-00001"]["status"] = "cancelled"
    await agent.run("C-00001 1234", thread_id="t")
    await agent.run("Extend R-00001 to 2025-11-14", thread_id="t")
    state = await agent.run("C-00001 1234", thread_id="t")
    assert "couldn't complete that: Reservation is cancelled" in last_reply(state)


async def test_policy_needs_no_authentication(agent: CustomerServiceAgent) -> None:
    state = await agent.run("What is the cancellation policy?", thread_id="t")
    assert trajectory(state) == ["ask_policy"]
    assert "24 hours before pickup" in last_reply(state)


async def test_human_handoff_on_request(agent: CustomerServiceAgent) -> None:
    state = await agent.run("I want to talk to a human", thread_id="t")
    assert state["handoff_reason"] == "Customer asked for a human agent."
    assert trajectory(state) == []
    state = await agent.run("hello?", thread_id="t")
    assert "already being transferred" in last_reply(state)


async def test_handoff_after_repeated_failed_logins(agent: CustomerServiceAgent) -> None:
    for _ in range(2):
        state = await agent.run("C-00001 0000", thread_id="t")
        assert "didn't match" in last_reply(state)
    state = await agent.run("C-00001 0000", thread_id="t")
    assert state["handoff_reason"] == "Too many failed authentication attempts."


async def test_handoff_after_turn_limit(agent: CustomerServiceAgent) -> None:
    for _ in range(6):
        state = await agent.run("hmm", thread_id="t")
    assert state["handoff_reason"] is None
    state = await agent.run("hmm", thread_id="t")
    assert state["handoff_reason"] == "Conversation exceeded 6 turns."


async def test_threads_are_isolated(agent: CustomerServiceAgent) -> None:
    await agent.run("C-00001 1234", thread_id="alice")
    state = await agent.run("Check R-00001", thread_id="someone-else")
    assert state["auth_level"] == "none"
    assert "verify you" in last_reply(state)


async def test_greeting_and_unclear_input(agent: CustomerServiceAgent) -> None:
    assert "I can look up" in last_reply(await agent.run("Hello", thread_id="t"))
    assert "didn't catch that" in last_reply(await agent.run("!@#$%", thread_id="t"))


async def test_pin_never_appears_in_trace(agent: CustomerServiceAgent) -> None:
    state = await agent.run("C-00001 1234", thread_id="t")
    assert "1234" not in json.dumps(state["tool_trace"])


async def test_cli_json_mode(agent: CustomerServiceAgent) -> None:
    out = json.loads(await run_json(agent, "What is the fuel policy?"))
    assert out["tool_trajectory"] == ["ask_policy"]
    assert "full-to-full" in out["reply"]
    assert json.loads(await run_json(agent, ""))["status"] == "error"
