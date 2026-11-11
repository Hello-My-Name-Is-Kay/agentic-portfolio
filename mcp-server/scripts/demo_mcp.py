"""Demo: talk to the MCP server the way an agent host does.

Starts ``python -m mcp_server.server`` as a subprocess, connects over stdio
with the MCP client, lists the tools and calls each one against the booking
API at BOOKING_API_BASE (start mock-booking-api first).

Usage:
    python scripts/demo_mcp.py          # human-readable
    python scripts/demo_mcp.py --json   # one JSON document
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client

CALLS: list[tuple[str, dict[str, Any]]] = [
    ("get_reservation", {"reservation_id": "R-99999"}),
    ("get_reservation", {"reservation_id": "R-00001"}),
    ("change_reservation", {"reservation_id": "R-00001", "new_dropoff_date": "2025-11-14"}),
    ("cancel_reservation", {"reservation_id": "R-00001", "reason": "Demo cancellation"}),
    ("cancel_reservation", {"reservation_id": "R-00001", "reason": "Trying again"}),
]


async def run() -> dict[str, Any]:
    """Run the scripted calls and return tool names plus each call's decoded result."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], env=dict(os.environ))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
        calls = []
        for name, args in CALLS:
            if name != "get_reservation":
                args = {**args, "idempotency_key": str(uuid.uuid4())}
            result = await session.call_tool(name, args)
            text = result.content[0].text if result.content else ""  # type: ignore[union-attr]
            calls.append({"tool": name, "arguments": args, "result": json.loads(text)})
        return {"tools": tools, "calls": calls}


def main() -> None:
    """Print the demo results."""
    report = asyncio.run(run())
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
        return
    print(f"Tools: {', '.join(report['tools'])}\n")
    for call in report["calls"]:
        result = call["result"]
        summary = result.get("code") or result.get("data", {}).get("status", "")
        print(f"{call['tool']}({call['arguments'].get('reservation_id')}) -> {result['status']} {summary}")


if __name__ == "__main__":
    main()
