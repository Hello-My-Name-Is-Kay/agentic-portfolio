"""Amazon Bedrock AgentCore Runtime entrypoint (HTTP protocol: ``GET /ping``, ``POST /invocations`` on port 8080).

One invocation is one customer turn. The AgentCore runtime session ID is the conversation thread, and with
``AGENT_MEMORY_ID`` set the LangGraph state is checkpointed to AgentCore Memory, so a conversation survives the
session's microVM being recycled.

Request:  ``{"prompt": "Check reservation R-00001"}`` (plus the ``runtimeSessionId`` AgentCore passes through)
Response: ``{"reply": "...", "intent": "lookup", "tools": ["authenticate", "lookup_reservation"], "handoff": false}``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext

from agent.agent import CustomerServiceAgent, last_reply, trajectory
from agent.config import AgentSettings
from agent.logging import get_logger

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

log = get_logger(__name__)

MAX_PROMPT_CHARS = 2000
ACTOR_ID = "web-customer"  # AgentCore Memory actor; customers are anonymous until they authenticate in the chat

app = BedrockAgentCoreApp()
_agent: CustomerServiceAgent | None = None


def build_agent(settings: AgentSettings | None = None) -> CustomerServiceAgent:
    """Create the agent, checkpointing to AgentCore Memory when ``AGENT_MEMORY_ID`` is set."""
    settings = settings or AgentSettings()
    checkpointer: BaseCheckpointSaver[Any] | None = None
    if settings.memory_id:
        from langgraph_checkpoint_aws import AgentCoreMemorySaver

        checkpointer = AgentCoreMemorySaver(settings.memory_id, region_name=settings.aws_region)
    return CustomerServiceAgent(settings=settings, checkpointer=checkpointer)


async def handle(payload: Any, session_id: str | None, agent: CustomerServiceAgent) -> dict[str, Any]:
    """Validate the request, run one turn and return the reply; never echoes the input back."""
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        return {"error": 'Send {"prompt": "<customer message>"}.'}
    if len(prompt) > MAX_PROMPT_CHARS:
        return {"error": f"Messages are limited to {MAX_PROMPT_CHARS} characters."}
    if not session_id:
        return {"error": "Missing runtime session ID; invoke with --runtime-session-id (33+ characters)."}

    state = await agent.run(prompt, thread_id=session_id, actor_id=ACTOR_ID)
    return {
        "reply": last_reply(state),
        "intent": state["intent"],
        "tools": trajectory(state),
        "handoff": bool(state["handoff_reason"]),
    }


@app.entrypoint
async def invoke(payload: Any, context: RequestContext) -> dict[str, Any]:
    """AgentCore invocation handler; the agent is built once per microVM."""
    global _agent
    if _agent is None:
        _agent = build_agent()
    return await handle(payload, context.session_id, _agent)


def main() -> None:
    """Serve on 0.0.0.0:8080 inside the AgentCore microVM (AgentCore terminates TLS and authenticates callers)."""
    app.run()


if __name__ == "__main__":
    main()
