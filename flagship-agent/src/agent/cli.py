"""Command-line entry point.

agent                       # interactive chat
echo "What is the fuel policy?" | agent --json   # one turn, JSON out
"""

from __future__ import annotations

import asyncio
import json
import sys

from agent.agent import CustomerServiceAgent, last_reply, trajectory
from agent.logging import configure_logging


async def run_json(agent: CustomerServiceAgent, text: str) -> str:
    """Run one turn and return a machine-readable summary."""
    if not text:
        return json.dumps({"status": "error", "reason": "No input provided"})
    state = await agent.run(text, thread_id="cli-json")
    return json.dumps(
        {
            "status": "ok",
            "request_id": state["request_id"],
            "customer_id": state["customer_id"],
            "auth_level": state["auth_level"],
            "intent": state["intent"],
            "handoff_reason": state["handoff_reason"],
            "tool_trajectory": trajectory(state),
            "errors": state["errors"],
            "reply": last_reply(state),
        },
        indent=2,
    )


async def chat(agent: CustomerServiceAgent) -> None:  # pragma: no cover - interactive loop
    """Interactive chat until 'exit' or EOF."""
    print("Rent-A-Car customer service agent. Type 'exit' to quit.\n")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("exit", "quit"):
            break
        if text:
            state = await agent.run(text, thread_id="cli")
            print(f"Agent: {last_reply(state)}\n")


def main() -> None:  # pragma: no cover - process entry point
    """Parse ``--json`` and run the agent."""
    configure_logging("WARNING")
    agent = CustomerServiceAgent()
    if "--json" in sys.argv:
        print(asyncio.run(run_json(agent, sys.stdin.read().strip())))
    else:
        asyncio.run(chat(agent))


if __name__ == "__main__":  # pragma: no cover
    main()
