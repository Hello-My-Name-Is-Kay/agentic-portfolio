"""AgentCore entrypoint tests: request validation, one turn per invocation, memory selection. No AWS calls."""

from __future__ import annotations

from typing import Any

import pytest

from agent import agentcore
from agent.agent import CustomerServiceAgent
from agent.agentcore import MAX_PROMPT_CHARS, build_agent, handle
from agent.config import AgentSettings
from agent.tools import AgentTools

SESSION = "session-" + "x" * 30  # AgentCore session IDs are at least 33 characters


@pytest.mark.parametrize(
    "payload",
    [None, "hello", {}, {"prompt": ""}, {"prompt": "   "}, {"prompt": 42}, {"message": "hi"}],
)
async def test_rejects_malformed_payloads(agent: CustomerServiceAgent, payload: Any) -> None:
    assert "error" in await handle(payload, SESSION, agent)


async def test_rejects_oversized_prompt(agent: CustomerServiceAgent) -> None:
    result = await handle({"prompt": "a" * (MAX_PROMPT_CHARS + 1)}, SESSION, agent)
    assert "limited" in result["error"]


async def test_requires_a_session_id(agent: CustomerServiceAgent) -> None:
    assert "session" in (await handle({"prompt": "hi"}, None, agent))["error"]


async def test_session_is_the_conversation_thread(agent: CustomerServiceAgent) -> None:
    await handle({"prompt": "C-00001 1234"}, SESSION, agent)
    result = await handle({"prompt": "Check reservation R-00001"}, SESSION, agent)
    assert result["intent"] == "lookup"
    assert result["tools"] == ["authenticate", "lookup_reservation"]
    assert result["reply"].startswith("Reservation R-00001")
    assert result["handoff"] is False

    other = await handle({"prompt": "Check reservation R-00001"}, SESSION + "-other", agent)
    assert other["tools"] == []  # a different session is not authenticated


async def test_response_never_contains_the_pin(agent: CustomerServiceAgent) -> None:
    result = await handle({"prompt": "C-00001 1234"}, SESSION, agent)
    assert "1234" not in str(result)


async def test_entrypoint_builds_the_agent_once(monkeypatch: pytest.MonkeyPatch, tools: AgentTools) -> None:
    built: list[CustomerServiceAgent] = []

    def fake_build() -> CustomerServiceAgent:
        built.append(CustomerServiceAgent(tools=tools))
        return built[-1]

    class Context:
        session_id = SESSION

    monkeypatch.setattr(agentcore, "_agent", None)
    monkeypatch.setattr(agentcore, "build_agent", fake_build)
    await agentcore.invoke({"prompt": "hi"}, Context())  # type: ignore[arg-type]
    await agentcore.invoke({"prompt": "hi"}, Context())  # type: ignore[arg-type]
    assert len(built) == 1


def test_memory_id_selects_agentcore_memory() -> None:
    agent = build_agent(AgentSettings(memory_id="mem-test", aws_region="eu-north-1"))
    assert type(agent.graph.checkpointer).__name__ == "AgentCoreMemorySaver"
    assert type(build_agent(AgentSettings()).graph.checkpointer).__name__ == "InMemorySaver"


async def test_logs_never_contain_message_content(agent: CustomerServiceAgent) -> None:
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        await handle({"prompt": "C-00001 1234"}, SESSION, agent)
        await handle({"prompt": "What is the fuel policy for my trip to Porto?"}, SESSION, agent)
    text = str(logs)
    assert logs  # the turns were logged
    assert "1234" not in text
    assert "Porto" not in text
