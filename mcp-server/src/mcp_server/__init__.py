"""MCP server exposing the mock booking API as three agent tools.

Typed, validated tool inputs; every booking-API outcome is returned to the
agent as a JSON string with ``status`` and, on failure, a machine-readable
``code``.
"""

from __future__ import annotations

__version__ = "0.1.0"
