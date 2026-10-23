"""Agent graph nodes — the LangGraph nodes that form the agent loop.

Nodes:
  - authenticate: Identify and verify the customer.
  - classify_intent: Determine what the user wants to do.
  - execute_tool: Run the appropriate tool based on intent.
  - check_auth: Step-up auth for write operations.
  - respond: Generate a natural language response.
  - should_continue: Conditional edge routing.
"""

from __future__ import annotations

import json
from agent.logging import get_logger
from typing import Literal

from agent.config import AgentSettings
from agent.errors import HandoffRequired, MaxStepsExceeded
from agent.state import AgentState, AuthLevel, Intent
from agent.tools import AgentTools

log = get_logger(__name__)


# ─── Node Implementations ──────────────────────────────────────────

async def authenticate_node(state: AgentState, tools: AgentTools) -> AgentState:
    """Authenticate the customer.

    If already verified, skip. Otherwise ask for ID.
    """
    log.info("node.authenticate", request_id=state.request_id)

    if state.auth_level.value >= AuthLevel.VERIFIED.value:
        return state

    # Look for customer ID in the last user message
    last_user_msg = ""
    for msg in reversed(state.messages):
        if msg.role == "user":
            last_user_msg = msg.content
            break

    # Check if message contains authentication info
    import re
    cid_match = re.search(r'C-\d{5}', last_user_msg)
    pin_match = re.search(r'\b\d{4}\b', last_user_msg)

    if cid_match and pin_match:
        cid = cid_match.group()
        pin = pin_match.group()
        result = await tools.authenticate(cid, pin)
        data = json.loads(result)
        if data["status"] == "ok":
            customer = data["customer"]
            state = state.with_auth(AuthLevel.VERIFIED, cid, customer["name"])
            state = state.add_message("system", f"Authenticated as {customer['name']} ({cid}).")
            log.info("node.authenticate.ok", customer_id=cid, name=customer["name"])
            return state

    # Not authenticated yet — prompt for credentials
    state = state.add_message(
        "assistant",
        "Welcome to Rent-A-Car support! To help you, I need to verify your identity first.\n"
        "Please provide your Customer ID (e.g., C-00001) and your 4-digit PIN."
    )
    return state


async def classify_intent_node(state: AgentState, tools: AgentTools) -> AgentState:
    """Classify the user's intent from their message."""
    log.info("node.classify_intent", request_id=state.request_id)

    last_user_msg = ""
    for msg in reversed(state.messages):
        if msg.role == "user":
            last_user_msg = msg.content.lower()
            break

    if not last_user_msg:
        return state

    if state.intent != Intent.UNKNOWN:
        return state  # Already classified

    intent = Intent.UNKNOWN
    # Simple keyword-based classification (in prod, LLM-based)
    if any(w in last_user_msg for w in ["hello", "hi ", "hey", "help"]):
        intent = Intent.HANDSHAKE
    elif any(w in last_user_msg for w in ["lookup", "find", "check", "get", "status", "my reservation"]):
        intent = Intent.LOOKUP
    elif any(w in last_user_msg for w in ["change", "move", "reschedule", "later", "extend", "modify"]):
        intent = Intent.CHANGE
    elif any(w in last_user_msg for w in ["cancel", "stop", "end"]):
        intent = Intent.CANCEL
    elif any(w in last_user_msg for w in ["policy", "rule", "what is", "how does", "can i", "tell me about"]):
        intent = Intent.POLICY
    elif any(w in last_user_msg for w in ["human", "agent", "manager", "talk to", "speak to"]):
        intent = Intent.HANDOFF
    elif "reservation" in last_user_msg:
        intent = Intent.LOOKUP

    state = state.with_intent(intent)
    log.info("node.classify_intent.result", intent=intent.value)
    return state


async def execute_tool_node(state: AgentState, tools: AgentTools) -> AgentState:
    """Execute the appropriate tool based on classified intent."""
    log.info("node.execute_tool", intent=state.intent.value, request_id=state.request_id)

    if state.intent == Intent.LOOKUP:
        # Extract reservation ID from messages
        import re
        rid = state.reservation_id
        if not rid:
            for msg in state.messages:
                m = re.search(r'R-\d{5}', msg.content)
                if m:
                    rid = m.group()
                    break

        if rid:
            result = await tools.lookup_reservation(rid)
            state = state.add_tool_call("lookup_reservation", {"reservation_id": rid}, result)
            data = json.loads(result)
            if data["status"] == "ok":
                res = data["reservation"]
                state = state.add_message("system",
                    f"Reservation {rid}: {res.get('vehicle_category', 'N/A')}, "
                    f"pickup {res.get('pickup_date', 'N/A')}, "
                    f"return {res.get('return_date', 'N/A')}, "
                    f"status: {res.get('status', 'N/A')}.")
            else:
                state = state.add_message("system", f"Could not find reservation {rid}.")
        else:
            state = state.add_message("assistant", "I need a reservation ID to look up. Could you provide it?")

    elif state.intent == Intent.CHANGE:
        if state.auth_level != AuthLevel.STEP_UP:
            state = state.add_message("assistant",
                "For security, I need to verify your identity first. Please confirm your Customer ID and PIN again to authorize changes.")
            return state

        import re
        rid = state.reservation_id
        if not rid:
            for msg in state.messages:
                m = re.search(r'R-\d{5}', msg.content)
                if m:
                    rid = m.group()
                    break

        if rid:
            # Find a date in messages
            date_match = None
            for msg in state.messages:
                m = re.search(r'\d{4}-\d{2}-\d{2}', msg.content)
                if m:
                    date_match = m.group()
                    break

            if date_match:
                result = await tools.change_reservation(rid, date_match)
                state = state.add_tool_call("change_reservation",
                    {"reservation_id": rid, "new_dropoff_date": date_match}, result)
                data = json.loads(result)
                if data["status"] == "ok":
                    state = state.add_message("system", f"Reservation {rid} updated to return on {date_match}.")
                else:
                    state = state.add_message("system",
                        f"Could not change reservation: {data.get('reason', 'Unknown error')}.")
            else:
                state = state.add_message("assistant", "What date would you like to change the return to?")
        else:
            state = state.add_message("assistant", "Which reservation would you like to change?")

    elif state.intent == Intent.CANCEL:
        if state.auth_level != AuthLevel.STEP_UP:
            state = state.add_message("assistant",
                "For security, I need to verify your identity first. Please confirm your Customer ID and PIN again to authorize cancellation.")
            return state

        import re
        rid = state.reservation_id
        if not rid:
            for msg in state.messages:
                m = re.search(r'R-\d{5}', msg.content)
                if m:
                    rid = m.group()
                    break

        if rid:
            result = await tools.cancel_reservation(rid, "Requested by customer")
            state = state.add_tool_call("cancel_reservation", {"reservation_id": rid}, result)
            data = json.loads(result)
            if data["status"] == "ok":
                state = state.add_message("system", f"Reservation {rid} has been cancelled.")
            else:
                state = state.add_message("system",
                    f"Could not cancel: {data.get('reason', 'Unknown error')}.")
        else:
            state = state.add_message("assistant", "Which reservation would you like to cancel?")

    elif state.intent == Intent.POLICY:
        last_msg = ""
        for msg in reversed(state.messages):
            if msg.role == "user":
                last_msg = msg.content
                break
        result = await tools.ask_policy(last_msg)
        state = state.add_tool_call("ask_policy", {"question": last_msg}, result)
        data = json.loads(result)
        answer = data.get("answer", "I don't know based on the available policies.")
        state = state.add_message("system", answer)

    elif state.intent == Intent.HANDSHAKE:
        state = state.add_message("assistant",
            "Hello! I'm the Rent-A-Car assistant. How can I help you today? "
            "I can look up reservations, change dates, cancel bookings, or answer policy questions.")

    elif state.intent == Intent.HANDOFF:
        state = state.with_handoff("Customer requested human agent.")

    elif state.intent == Intent.UNKNOWN:
        state = state.add_message("assistant",
            "I'm not sure I understand. I can help with: looking up reservations, "
            "changing or cancelling bookings, and answering policy questions. "
            "What would you like help with?")

    return state


async def step_up_auth_node(state: AgentState, tools: AgentTools) -> AgentState:
    """Step-up authentication for write operations (change/cancel)."""
    log.info("node.step_up_auth", request_id=state.request_id, auth_level=state.auth_level.value)

    if state.intent in (Intent.CHANGE, Intent.CANCEL):
        if state.auth_level == AuthLevel.VERIFIED:
            # Prompt for re-verification
            state = state.add_message("assistant",
                "To process this request, I need you to confirm your identity. "
                "Please re-enter your Customer ID and PIN for authorization.")
            return state

        if state.auth_level == AuthLevel.STEP_UP:
            return state  # Already step-up authed

    return state


async def respond_node(state: AgentState, config: AgentSettings) -> AgentState:
    """Generate the final response (currently just relays system messages).

    In production, this would call an LLM to generate natural language
    from the tool results and system messages.
    """
    log.info("node.respond", request_id=state.request_id)

    if state.handoff_reason:
        state = state.add_message("assistant",
            f"I'm transferring you to a human agent now. Reason: {state.handoff_reason}\n"
            "Thank you for your patience.")
        return state

    # Relay the last system message as the response
    last_system = ""
    for msg in reversed(state.messages):
        if msg.role == "system" and msg.content:
            last_system = msg.content
            break

    if not last_system:
        last_user = ""
        for msg in reversed(state.messages):
            if msg.role == "assistant" and msg.content:
                last_user = msg.content
                break
        if not last_user:
            state = state.add_message("assistant", "How can I help you with your rental today?")

    return state


def should_continue(state: AgentState, config: AgentSettings) -> Literal["tools", "handoff", "__end__"]:
    """Determine the next step in the agent graph."""
    log.info("node.should_continue", request_id=state.request_id, step=state.step_count, max=config.max_steps)

    # Check max steps
    if state.step_count >= config.max_steps:
        log.warning("agent.loop_limit_reached", steps=state.step_count, request_id=state.request_id)
        return "handoff"

    # Check handoff
    if state.handoff_reason:
        return "handoff"

    # Check if we need to execute a tool
    if state.intent in (Intent.LOOKUP, Intent.CHANGE, Intent.CANCEL, Intent.POLICY):
        return "tools"

    return "__end__"