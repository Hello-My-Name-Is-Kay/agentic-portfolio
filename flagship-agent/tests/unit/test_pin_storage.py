"""The PIN is used to authenticate but never stored: not in state, not in the checkpointer."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from agent.agent import CustomerServiceAgent, trajectory
from agent.tools import AgentTools


def _all_text(obj: Any) -> str:
    """Flatten a checkpointer's storage (nested dicts, tuples, bytes) into one searchable string."""
    if isinstance(obj, dict):
        return " ".join(_all_text(k) + " " + _all_text(v) for k, v in obj.items())
    if isinstance(obj, list | tuple | set):
        return " ".join(_all_text(v) for v in obj)
    if isinstance(obj, bytes | bytearray):
        return bytes(obj).decode("utf-8", "replace")
    return str(obj)


async def test_pin_authenticates_but_is_never_stored(tools: AgentTools) -> None:
    saver = InMemorySaver()
    agent = CustomerServiceAgent(tools=tools, checkpointer=saver)
    state = await agent.run("C-00001 1234", thread_id="t")
    state = await agent.run("Check reservation R-00001", thread_id="t")

    assert trajectory(state) == ["authenticate", "lookup_reservation"]  # the PIN still worked
    assert [m["content"] for m in state["messages"] if m["role"] == "user"][0] == "C-00001 [PIN]"
    assert "1234" not in _all_text(saver.storage) + _all_text(saver.writes) + _all_text(saver.blobs)


async def test_wrong_pin_is_not_stored_either(tools: AgentTools) -> None:
    saver = InMemorySaver()
    agent = CustomerServiceAgent(tools=tools, checkpointer=saver)
    state = await agent.run("C-00001 9999", thread_id="t")
    assert state["failed_auth"] == 1
    assert "9999" not in _all_text(saver.storage) + _all_text(saver.writes) + _all_text(saver.blobs)
