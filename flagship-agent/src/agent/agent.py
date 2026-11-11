"""Customer-service agent: a compiled LangGraph with per-conversation memory."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import structlog
from langgraph.checkpoint.memory import InMemorySaver

from agent.config import AgentSettings
from agent.graph import build_graph
from agent.logging import get_logger
from agent.state import AgentState, Message, initial_state
from agent.tools import AgentTools

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver

log = get_logger(__name__)


class CustomerServiceAgent:
    """Runs one graph invocation per user turn; state persists per ``thread_id``.

    Usage:
        agent = CustomerServiceAgent()
        state = await agent.run("C-00001 1234", thread_id="chat-42")
        state = await agent.run("Check reservation R-00001", thread_id="chat-42")
        print(last_reply(state))
    """

    def __init__(
        self,
        settings: AgentSettings | None = None,
        tools: AgentTools | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        """Compile the graph; defaults to the configured booking API and an in-memory checkpointer."""
        self._settings = settings or AgentSettings()
        self._tools = tools or AgentTools(
            booking_api_base=self._settings.booking_api_base, api_key=self._settings.booking_api_key
        )
        self.graph = build_graph(self._tools, self._settings).compile(checkpointer=checkpointer or InMemorySaver())

    async def run(self, user_input: str, thread_id: str = "default") -> AgentState:
        """Process one user message in a conversation thread and return the thread's full state."""
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self._settings.recursion_limit,
        }
        snapshot = await self.graph.aget_state(config)
        update: dict[str, Any] = {} if snapshot.values else initial_state()
        update |= {"request_id": request_id, "messages": [Message(role="user", content=user_input)]}

        with structlog.contextvars.bound_contextvars(request_id=request_id, thread_id=thread_id):
            log.info("agent.turn.start", input_preview=user_input[:80])
            state = cast("AgentState", await self.graph.ainvoke(cast("AgentState", update), config))
            log.info(
                "agent.turn.end", turn=state["turn"], intent=state["intent"], handoff=bool(state["handoff_reason"])
            )
        return state


def last_reply(state: AgentState) -> str:
    """Return the agent's latest message."""
    return next((m["content"] for m in reversed(state["messages"]) if m["role"] == "assistant"), "")


def trajectory(state: AgentState) -> list[str]:
    """Return the names of all tools called in the thread, in order."""
    return [call["name"] for call in state["tool_trace"]]
