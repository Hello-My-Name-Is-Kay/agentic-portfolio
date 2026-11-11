"""LangGraph nodes and routing functions.

One graph invocation handles one user turn:

    start_turn → authenticate → classify_intent → (route) → one reply node → END

Intent classification is keyword-based so behaviour is deterministic in tests;
``classify`` is the single place to swap in an LLM classifier.
"""

import json
import re
from typing import Any, Literal

from agent.config import AgentSettings
from agent.logging import get_logger
from agent.state import ACCOUNT_INTENTS, WRITE_INTENTS, AgentState, Intent, Message, PendingAction, ToolCall
from agent.tools import AgentTools

log = get_logger(__name__)

_CUSTOMER_ID = re.compile(r"\bC-\d{5}\b")
_PIN = re.compile(r"(?<![\d-])\d{4}(?![\d-])")
_RESERVATION_ID = re.compile(r"\bR-\d{5}\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_HANDOFF = re.compile(r"\b(human|real person|manager|supervisor|talk to|speak to|operator)\b")
_POLICY = re.compile(r"\b(policy|policies|rules?|fees?|what is|what's|how does|how do|can i|tell me about)\b")
_CANCEL = re.compile(r"\bcancel\b")
_CHANGE = re.compile(r"\b(change|extend|reschedule|move|modify|postpone)\b")
_LOOKUP = re.compile(r"\b(look ?up|check|status|details|find|my reservation|reservation)\b")
_GREETING = re.compile(r"\b(hello|hi|hey|good (morning|afternoon|evening))\b")

_TRANSFER = "I'm transferring you to a colleague now."

StateUpdate = dict[str, Any]


def classify(text: str) -> Intent:
    """Map a user message to an intent."""
    t = text.lower()
    has_reservation = bool(_RESERVATION_ID.search(text))
    if _HANDOFF.search(t):
        return "handoff"
    if _POLICY.search(t) and not has_reservation:
        return "policy"
    if _CANCEL.search(t):
        return "cancel"
    if _CHANGE.search(t):
        return "change"
    if _LOOKUP.search(t) or has_reservation:
        return "lookup"
    if _GREETING.search(t):
        return "greeting"
    return "unknown"


def _last_user_text(state: AgentState) -> str:
    return next((m["content"] for m in reversed(state["messages"]) if m["role"] == "user"), "")


def _say(text: str) -> StateUpdate:
    return {"messages": [Message(role="assistant", content=text)]}


def _call(name: str, args: dict[str, str], raw: str) -> tuple[dict[str, Any], ToolCall]:
    result: dict[str, Any] = json.loads(raw)
    return result, ToolCall(name=name, args=args, result=result)


class Nodes:
    """Graph nodes bound to one set of tools and settings."""

    def __init__(self, tools: AgentTools, settings: AgentSettings) -> None:
        """Bind the nodes to the tools and limits they use."""
        self._tools = tools
        self._settings = settings

    async def start_turn(self, state: AgentState) -> StateUpdate:
        """Count the turn and hand off once the conversation runs too long."""
        turn = state["turn"] + 1
        update: StateUpdate = {"turn": turn}
        if turn > self._settings.max_steps and not state["handoff_reason"]:
            update["handoff_reason"] = f"Conversation exceeded {self._settings.max_steps} turns."
        log.info("node.start_turn", turn=turn)
        return update

    async def authenticate(self, state: AgentState) -> StateUpdate:
        """Verify credentials found in the message; credentials sent while a write is pending grant step-up."""
        text = _last_user_text(state)
        cid, pin = _CUSTOMER_ID.search(text), _PIN.search(text)
        if not (cid and pin):
            return {}
        customer_id = cid.group()
        result, call = _call(
            "authenticate", {"customer_id": customer_id}, await self._tools.authenticate(customer_id, pin.group())
        )
        update: StateUpdate = {"tool_trace": [call]}
        if result["status"] != "ok":
            failed = state["failed_auth"] + 1
            update |= {"failed_auth": failed, "auth_fail_turn": state["turn"], "errors": [result["reason"]]}
            if failed >= self._settings.max_auth_failures:
                update["handoff_reason"] = "Too many failed authentication attempts."
            log.info("node.authenticate.failed", customer_id=customer_id, failed=failed)
            return update
        pending = state["pending"]
        write_pending = pending is not None and pending["intent"] in WRITE_INTENTS
        level = "step_up" if write_pending else "verified"
        log.info("node.authenticate.ok", customer_id=customer_id, level=level)
        return update | {
            "auth_level": level,
            "customer_id": customer_id,
            "customer_name": result["customer"]["name"],
            "failed_auth": 0,
            "auth_ok_turn": state["turn"],
        }

    async def classify_intent(self, state: AgentState) -> StateUpdate:
        """Classify the turn and keep the account action it refers to in ``pending``."""
        text = _last_user_text(state)
        intent = classify(text)
        pending = state["pending"]
        rid = _RESERVATION_ID.search(text)
        date = _DATE.search(text)
        reservation_id = rid.group() if rid else None
        new_date = date.group() if date else None

        keywords_only = classify(_DATE.sub(" ", _RESERVATION_ID.sub(" ", text)))
        if keywords_only in ("unknown", "greeting") and pending is not None:
            auth_attempt_now = state["turn"] in (state["auth_ok_turn"], state["auth_fail_turn"])
            if auth_attempt_now or reservation_id or new_date:
                intent = pending["intent"]

        update: StateUpdate = {"intent": intent}
        if intent in ACCOUNT_INTENTS:
            same_action = pending is not None and pending["intent"] == intent
            update["pending"] = PendingAction(
                intent=intent,
                reservation_id=reservation_id or (pending["reservation_id"] if same_action and pending else None),
                new_dropoff_date=new_date or (pending["new_dropoff_date"] if same_action and pending else None),
            )
        log.info("node.classify_intent", intent=intent)
        return update

    async def answer_policy(self, state: AgentState) -> StateUpdate:
        """Answer a policy question; no authentication needed."""
        question = _last_user_text(state)
        result, call = _call("ask_policy", {"question": question}, await self._tools.ask_policy(question))
        return {"tool_trace": [call]} | _say(result["answer"])

    async def run_account_tool(self, state: AgentState) -> StateUpdate:
        """Look up the reservation, check it belongs to the customer, then read or write it."""
        pending = state["pending"]
        assert pending is not None and pending["reservation_id"] is not None
        rid = pending["reservation_id"]
        result, lookup = _call("lookup_reservation", {"reservation_id": rid}, await self._tools.lookup_reservation(rid))
        update: StateUpdate = {"pending": None, "tool_trace": [lookup]}
        if pending["intent"] in WRITE_INTENTS:
            update["auth_level"] = "verified"  # step-up is single-use

        if result["status"] != "ok":
            update["errors"] = [result["reason"]]
            if result["code"] == "NOT_FOUND":
                return update | _say(f"I couldn't find reservation {rid} on your account. Could you check the ID?")
            return update | _say("Our booking system isn't responding right now. Please try again in a few minutes.")

        res = result["reservation"]
        if res.get("customer_id") != state["customer_id"]:
            update["errors"] = [f"Reservation {rid} does not belong to {state['customer_id']}."]
            return update | _say(f"I couldn't find reservation {rid} on your account. Could you check the ID?")

        if pending["intent"] == "lookup":
            return update | _say(
                f"Reservation {rid}: {res.get('vehicle_category', 'vehicle')}, pickup {res.get('pickup_date')}, "
                f"return {res.get('return_date')}, status {res.get('status')}."
            )

        if pending["intent"] == "change":
            new_date = pending["new_dropoff_date"]
            assert new_date is not None
            args = {"reservation_id": rid, "new_dropoff_date": new_date}
            write, call = _call("change_reservation", args, await self._tools.change_reservation(rid, new_date))
            done = f"Done — reservation {rid} now returns on {new_date}."
        else:
            args = {"reservation_id": rid}
            write, call = _call(
                "cancel_reservation", args, await self._tools.cancel_reservation(rid, "Customer request")
            )
            done = f"Done — reservation {rid} has been cancelled."

        update["tool_trace"] = [lookup, call]
        if write["status"] == "ok":
            return update | _say(done)
        update["errors"] = [write["reason"]]
        return update | _say(f"I couldn't complete that: {write['reason']}")

    async def request_auth(self, state: AgentState) -> StateUpdate:
        """Ask for credentials before any account action."""
        prefix = "Those details didn't match. " if state["auth_fail_turn"] == state["turn"] else ""
        return _say(
            f"{prefix}To help with your reservation I need to verify you first. "
            "Please send your Customer ID (e.g. C-00001) and your 4-digit PIN."
        )

    async def request_step_up(self, state: AgentState) -> StateUpdate:
        """Ask the customer to re-confirm credentials before a write."""
        prefix = "Those details didn't match. " if state["auth_fail_turn"] == state["turn"] else ""
        action = "change" if state["intent"] == "change" else "cancel"
        return _say(
            f"{prefix}For your security, please confirm your Customer ID and PIN again to {action} this reservation."
        )

    async def ask_details(self, state: AgentState) -> StateUpdate:
        """Ask for the reservation ID or new date the action still needs."""
        pending = state["pending"]
        assert pending is not None
        if pending["reservation_id"] is None:
            return _say("Which reservation is this about? Please send the ID, e.g. R-00001.")
        return _say("What new return date would you like? Please use the format YYYY-MM-DD.")

    async def greet(self, state: AgentState) -> StateUpdate:
        """Greet, or confirm a successful verification."""
        if state["auth_ok_turn"] == state["turn"]:
            return _say(f"Thanks, {state['customer_name']} — you're verified. How can I help with your rental?")
        return _say("Hello! I can look up, change or cancel a reservation, or answer questions about our policies.")

    async def clarify(self, state: AgentState) -> StateUpdate:  # noqa: ARG002
        """Ask the customer to rephrase."""
        return _say(
            "Sorry, I didn't catch that. I can look up, change or cancel a reservation, "
            "or answer policy questions. What would you like to do?"
        )

    async def handoff(self, state: AgentState) -> StateUpdate:
        """Transfer to a human colleague; later turns just confirm the transfer."""
        already = any(m["role"] == "assistant" and m["content"].startswith(_TRANSFER) for m in state["messages"])
        if already:
            return _say("You're already being transferred to a colleague. Thank you for your patience.")
        reason = state["handoff_reason"] or "Customer asked for a human agent."
        log.info("node.handoff", reason=reason)
        return {"handoff_reason": reason} | _say(f"{_TRANSFER} Reason: {reason}")


def route_start(state: AgentState) -> Literal["handoff", "authenticate"]:
    """Skip straight to handoff once a conversation is over its limit."""
    return "handoff" if state["handoff_reason"] else "authenticate"


def route_intent(
    state: AgentState,
) -> Literal[
    "handoff", "answer_policy", "request_auth", "ask_details", "request_step_up", "run_account_tool", "greet", "clarify"
]:
    """Pick the reply node for this turn."""
    intent = state["intent"]
    if state["handoff_reason"] or intent == "handoff":
        return "handoff"
    if intent == "policy":
        return "answer_policy"
    if intent in ACCOUNT_INTENTS:
        pending = state["pending"]
        if state["auth_level"] == "none":
            return "request_auth"
        if pending is None or pending["reservation_id"] is None:
            return "ask_details"
        if intent == "change" and pending["new_dropoff_date"] is None:
            return "ask_details"
        if intent in WRITE_INTENTS and state["auth_level"] != "step_up":
            return "request_step_up"
        return "run_account_tool"
    if state["auth_fail_turn"] == state["turn"]:
        return "request_auth"
    if intent == "greeting" or state["auth_ok_turn"] == state["turn"]:
        return "greet"
    return "clarify"
