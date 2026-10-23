"""Demo script: shows an LLM calling the MCP tools.

This script simulates how an LLM agent would interact with the
MCP server's tools — calling each one and displaying the results.

Usage:
    python scripts/demo_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def demo() -> None:
    """Demonstrate all 3 MCP tools."""
    print("=" * 60)
    print("  MCP Server Demo")
    print("  Using the booking tools as an LLM agent would.")
    print("=" * 60)

    # Import tool implementations directly
    from mcp_server.server import _get_reservation, _change_reservation, _cancel_reservation

    print("\n\n--- 1. Get Reservation (not found example) ---")
    result = await _get_reservation("R-99999")
    data = json.loads(result)
    print(f"  Status: {data['status']}")
    print(f"  Code: {data.get('code', 'N/A')}")
    print(f"  Reason: {data.get('reason', 'N/A')}")

    print("\n\n--- 2. Get Reservation (success) ---")
    result = await _get_reservation("R-00001")
    data = json.loads(result)
    print(f"  Status: {data.get('status', 'N/A')}")
    if data.get("data"):
        print(f"  Reservation: {json.dumps(data['data'], indent=4)}")

    print("\n\n--- 3. Change Reservation (idempotent) ---")
    result = await _change_reservation("R-00001", "2025-11-14", "demo-change-001")
    data = json.loads(result)
    print(f"  Status: {data['status']}")
    if data.get("code"):
        print(f"  Code: {data['code']}")
        print(f"  Reason: {data.get('reason', 'N/A')}")

    print("\n\n--- 4. Cancel Reservation (idempotent) ---")
    result = await _cancel_reservation("R-00001", "Demo cancellation", "demo-cancel-001")
    data = json.loads(result)
    print(f"  Status: {data['status']}")
    if data.get("code"):
        print(f"  Code: {data['code']}")
        print(f"  Reason: {data.get('reason', 'N/A')}")

    print("\n\n--- 5. Cancel Already Cancelled ---")
    result = await _cancel_reservation("R-00001", "Trying again", "demo-cancel-002")
    data = json.loads(result)
    print(f"  Status: {data['status']}")
    print(f"  Code: {data.get('code', 'N/A')}")
    print(f"  Reason: {data.get('reason', 'N/A')}")

    print("\n" + "=" * 60)
    print("  Demo complete.")
    print("  All tools return structured JSON — never raise.")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    if "--json" in sys.argv:
        # JSON mode: run all tools and print structured results
        import json as json_mod

        async def json_demo() -> None:
            from mcp_server.server import _get_reservation
            results = {
                "tools": [
                    {"name": "get_reservation", "result": json.loads(await _get_reservation("R-00001"))},
                    {"name": "get_reservation_not_found", "result": json.loads(await _get_reservation("R-99999"))},
                ]
            }
            print(json_mod.dumps(results, indent=2))
        asyncio.run(json_demo())
    else:
        asyncio.run(demo())