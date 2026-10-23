"""Typed exception hierarchy for the agent."""

from __future__ import annotations


class AgentError(Exception):
    """Base for all agent errors."""


class ConfigError(AgentError):
    """Invalid or missing configuration."""


class StateError(AgentError):
    """Invalid agent state transition."""


class ToolError(AgentError):
    """A tool call failed in a way the agent should handle."""
    def __init__(self, code: str, reason: str, tool_name: str = "unknown") -> None:
        self.code = code
        self.reason = reason
        self.tool_name = tool_name
        super().__init__(f"[{tool_name}] {code}: {reason}")


class AuthError(AgentError):
    """Authentication failure."""


class HandoffRequired(AgentError):
    """Agent determined it needs to hand off to a human."""
    def __init__(self, reason: str = "Handoff required") -> None:
        self.reason = reason
        super().__init__(reason)


class MaxStepsExceeded(HandoffRequired):
    """Agent exceeded the maximum number of steps."""
    def __init__(self, steps: int, limit: int) -> None:
        self.steps = steps
        self.limit = limit
        super().__init__(f"Exceeded maximum steps ({steps} > {limit})")