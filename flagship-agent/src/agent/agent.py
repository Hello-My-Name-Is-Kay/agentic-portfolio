"""Main agent orchestration — runs the LangGraph-inspired agent loop.

Orchestrates: authenticate → classify_intent → execute_tool (+ step-up auth) → respond

Uses a simple state-machine loop (LangGraph-like but without the
framework dependency for self-containment).
"""

from __future__ import annotations

import asyncio
from agent.logging import get_logger
from typing import Any

from agent.config import AgentSettings
from agent.errors import AgentError, HandoffRequired
from agent.nodes import (
    authenticate_node,
    classify_intent_node,
    execute_tool_node,
    respond_node,
    should_continue,
    step_up_auth_node,
)
from agent.state import AgentState
from agent.tools import AgentTools

log = get_logger(__name__)


class CustomerServiceAgent:
    """LangGraph-inspired customer service agent.

    Runs a state-machine loop until the conversation is complete
    or handoff is required.

    Usage:
        agent = CustomerServiceAgent()
        result = await agent.run("I need to check my reservation R-00001")
        print(result.messages[-1].content)
    """

    def __init__(self, settings: AgentSettings | None = None) -> None:
        self._config = settings or AgentSettings()
        self._tools = AgentTools(
            booking_api_base=self._config.booking_api_base,
            api_key=self._config.booking_api_key,
        )

    async def run(self, user_input: str) -> AgentState:
        """Process a user request through the agent graph.

        Args:
            user_input: The user's message.

        Returns:
            Final AgentState with all messages, tool traces, and errors.

        Raises:
            AgentError: If the agent encounters an unrecoverable error.
        """
        state = AgentState()
        log.info("agent.run.start", request_id=state.request_id, input_preview=user_input[:80])

        # Add user message
        state = state.add_message("user", user_input)

        # Agent loop
        while True:
            # Step 1: Authenticate
            state = await authenticate_node(state, self._tools)
            if state.handoff_reason:
                state = await respond_node(state, self._config)
                break

            # Step 2: Classify intent
            state = await classify_intent_node(state, self._tools)
            if state.handoff_reason:
                state = await respond_node(state, self._config)
                break

            # Step 3: Step-up auth for writes
            state = await step_up_auth_node(state, self._tools)
            if state.handoff_reason:
                state = await respond_node(state, self._config)
                break

            # Step 4: Check if we need tools
            next_step = should_continue(state, self._config)

            if next_step == "handoff":
                state = state.with_handoff("Max steps exceeded or handoff requested.")
                state = await respond_node(state, self._config)
                break

            if next_step == "__end__":
                state = await respond_node(state, self._config)
                break

            # Step 5: Execute tool
            if next_step == "tools":
                state = await execute_tool_node(state, self._tools)

            # Safety check — prevent infinite loops
            if state.step_count > self._config.max_steps:
                state = state.with_handoff(f"Exceeded max steps ({state.step_count})")
                break

        log.info("agent.run.end", request_id=state.request_id, steps=state.step_count,
                 handoff=bool(state.handoff_reason), errors=len(state.errors))
        return state

    def _extract_tool_trajectory(self, state: AgentState) -> list[str]:
        """Extract the sequence of tool names called."""
        return [t["name"] for t in state.tool_trace]

    def _extract_final_message(self, state: AgentState) -> str:
        """Extract the final assistant message."""
        for msg in reversed(state.messages):
            if msg.role == "assistant":
                return msg.content
        return ""


async def run_cli(json_output: bool = False) -> None:
    """Run the agent in interactive CLI mode.

    Args:
        json_output: If True, emit machine-readable JSON; otherwise human-readable.
    """
    from agent.logging import configure_logging
    import json as json_mod
    configure_logging(log_level="INFO")

    agent = CustomerServiceAgent()

    if json_output:
        # JSON mode: read one line, process, emit JSON, exit
        import sys
        user_input = sys.stdin.read().strip()
        if not user_input:
            print(json_mod.dumps({"status": "error", "reason": "No input provided"}))
            return

        state = await agent.run(user_input)

        result = {
            "status": "ok",
            "request_id": state.request_id,
            "customer_id": state.customer_id,
            "customer_name": state.customer_name,
            "auth_level": state.auth_level.value,
            "intent": state.intent.value,
            "steps": state.step_count,
            "handoff": state.handoff_reason is not None,
            "handoff_reason": state.handoff_reason,
            "tool_trajectory": [t["name"] for t in state.tool_trace],
            "errors": state.errors,
            "final_response": next(
                (m.content for m in reversed(state.messages) if m.role == "assistant"),
                "",
            ),
            "conversation": [
                {"role": m.role, "content": m.content}
                for m in state.messages
            ],
        }
        print(json_mod.dumps(result, indent=2))
        return

    # Human-readable interactive mode
    print("=" * 60)
    print("  Rent-A-Car Customer Service Agent (CLI)")
    print("  Type 'exit' or 'quit' to stop.")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        state = await agent.run(user_input)

        for msg in state.messages:
            if msg.role == "assistant":
                print(f"\nAgent: {msg.content}\n")

        if state.tool_trace:
            print("  [Tools called:", " → ".join(t["name"] for t in state.tool_trace), "]")

        if state.handoff_reason:
            print(f"  [Handoff: {state.handoff_reason}]")

        if state.errors:
            print(f"  [Errors: {len(state.errors)}]")
        print()


def main() -> None:
    """Entry point for the CLI agent.

    Usage:
        python -m agent.cli                  # interactive mode
        python -m agent.cli --json < input.json  # JSON mode (for LLM)
    """
    import sys
    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")
    asyncio.run(run_cli(json_output=json_output))


if __name__ == "__main__":
    main()