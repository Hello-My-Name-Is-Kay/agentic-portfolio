"""MCP Server — Portfolio Project

An MCP server that exposes rental-booking tools for LLM agents.
Wraps the Mock Booking API into three tools with typed inputs,
precise docstrings, and structured error JSON (never raises).

Demonstrates: MCP tool design, typed input schemas, error resilience,
and the tool-as-a-service pattern for agentic systems.
"""

from __future__ import annotations

__version__ = "0.1.0"