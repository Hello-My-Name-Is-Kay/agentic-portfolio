"""Graph state for the customer-service agent.

Plain JSON-friendly types only, so every turn can be checkpointed per conversation thread.
List fields use an ``operator.add`` reducer: nodes return new items and LangGraph appends them.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

AuthLevel = Literal["none", "verified", "step_up"]
Intent = Literal["unknown", "greeting", "lookup", "change", "cancel", "policy", "handoff"]

ACCOUNT_INTENTS: frozenset[Intent] = frozenset({"lookup", "change", "cancel"})
WRITE_INTENTS: frozenset[Intent] = frozenset({"change", "cancel"})


class Message(TypedDict):
    """One conversation message."""

    role: Literal["user", "assistant"]
    content: str


class ToolCall(TypedDict):
    """One recorded tool call; ``args`` never contains secrets such as the PIN."""

    name: str
    args: dict[str, str]
    result: dict[str, Any]


class PendingAction(TypedDict):
    """An account action waiting for details or authentication."""

    intent: Intent
    reservation_id: str | None
    new_dropoff_date: str | None


class AgentState(TypedDict):
    """Full state of one conversation thread."""

    messages: Annotated[list[Message], operator.add]
    tool_trace: Annotated[list[ToolCall], operator.add]
    errors: Annotated[list[str], operator.add]
    request_id: str
    turn: int
    customer_id: str | None
    customer_name: str | None
    auth_level: AuthLevel
    failed_auth: int
    auth_ok_turn: int
    auth_fail_turn: int
    intent: Intent
    pending: PendingAction | None
    handoff_reason: str | None


def initial_state() -> dict[str, Any]:
    """Return the values a brand-new conversation thread starts with."""
    return {
        "turn": 0,
        "customer_id": None,
        "customer_name": None,
        "auth_level": "none",
        "failed_auth": 0,
        "auth_ok_turn": 0,
        "auth_fail_turn": 0,
        "intent": "unknown",
        "pending": None,
        "handoff_reason": None,
    }
