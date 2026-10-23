# LLM Router — Portfolio Project
#
# Multi-provider LLM router with fallback chain, retry per provider,
# response caching, token/latency/cost tracking, and budget enforcement.
#
# Demonstrates: Provider Protocol pattern, fallback resilience,
# observability (structured logs with provider, latency, tokens, cost),
# and the principle that every provider call is traceable.

from __future__ import annotations

__version__ = "0.1.0"