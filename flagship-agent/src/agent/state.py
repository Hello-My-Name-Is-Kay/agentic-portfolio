"""Agent state model — tracks conversation, step count, and auth status.

Uses a frozen Pydantic model for immutability; state transitions
create new state objects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuthLevel(Enum):
    """Authentication level for the current session."""
    NONE = "none"
    BASIC = "basic"  # Customer identified
    VERIFIED = "verified"  # Customer authenticated (e.g., PIN verified)
    STEP_UP = "step_up"  # Elevated auth for write operations


class Intent(Enum):
    """Classified intent of the user's request."""
    UNKNOWN = "unknown"
    LOOKUP = "lookup"  # Get reservation info
    CHANGE = "change"  # Change reservation details
    CANCEL = "cancel"  # Cancel a reservation
    POLICY = "policy"  # Ask about policy
    HANDSHAKE = "handshake"  # Greeting/identification
    HANDOFF = "handoff"  # Request human agent


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    tool_name: str | None = None
    tool_result: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AgentState:
    """Immutable state of the agent at a point in time."""

    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:8]}")
    customer_id: str | None = None
    customer_name: str | None = None
    auth_level: AuthLevel = AuthLevel.NONE
    intent: Intent = Intent.UNKNOWN
    step_count: int = 0
    messages: list[Message] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    handoff_reason: str | None = None
    reservation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, tool_name: str | None = None, tool_result: str | None = None) -> "AgentState":
        """Return a new state with an added message."""
        msg = Message(
            role=role,
            content=content,
            tool_name=tool_name,
            tool_result=tool_result,
        )
        return AgentState(
            request_id=self.request_id,
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            auth_level=self.auth_level,
            intent=self.intent,
            step_count=self.step_count + 1,
            messages=self.messages + [msg],
            tool_trace=list(self.tool_trace),
            errors=list(self.errors),
            handoff_reason=self.handoff_reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )

    def add_tool_call(self, name: str, args: dict, result: str) -> "AgentState":
        """Record a tool call in the trace."""
        return AgentState(
            request_id=self.request_id,
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            auth_level=self.auth_level,
            intent=self.intent,
            step_count=self.step_count,
            messages=list(self.messages),
            tool_trace=self.tool_trace + [{"name": name, "args": args, "result": result}],
            errors=list(self.errors),
            handoff_reason=self.handoff_reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )

    def with_auth(self, level: AuthLevel, customer_id: str | None = None, customer_name: str | None = None) -> "AgentState":
        """Return a new state with updated auth level."""
        return AgentState(
            request_id=self.request_id,
            customer_id=customer_id or self.customer_id,
            customer_name=customer_name or self.customer_name,
            auth_level=level,
            intent=self.intent,
            step_count=self.step_count,
            messages=list(self.messages),
            tool_trace=list(self.tool_trace),
            errors=list(self.errors),
            handoff_reason=self.handoff_reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )

    def with_intent(self, intent: Intent) -> "AgentState":
        return AgentState(
            request_id=self.request_id,
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            auth_level=self.auth_level,
            intent=intent,
            step_count=self.step_count,
            messages=list(self.messages),
            tool_trace=list(self.tool_trace),
            errors=list(self.errors),
            handoff_reason=self.handoff_reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )

    def with_error(self, error: str) -> "AgentState":
        return AgentState(
            request_id=self.request_id,
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            auth_level=self.auth_level,
            intent=self.intent,
            step_count=self.step_count,
            messages=list(self.messages),
            tool_trace=list(self.tool_trace),
            errors=self.errors + [error],
            handoff_reason=self.handoff_reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )

    def with_handoff(self, reason: str) -> "AgentState":
        return AgentState(
            request_id=self.request_id,
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            auth_level=self.auth_level,
            intent=self.intent,
            step_count=self.step_count,
            messages=list(self.messages),
            tool_trace=list(self.tool_trace),
            errors=list(self.errors),
            handoff_reason=reason,
            reservation_id=self.reservation_id,
            metadata=dict(self.metadata),
        )