# Flagship Agent — Portfolio Project
#
# A LangGraph-based customer service agent for a fictional car rental
# company. Authenticates customers, looks up/modifies reservations via
# tools, answers policy questions via RAG, and hands off to humans.
#
# This is the pinned repo -- the one that demonstrates every skill
# from the job posting: LangGraph, tool design, error recovery,
# step-up auth, idempotency, observability, and evals.
#
# Architecture:
#   authenticate → intent → tools | handoff → respond
"""

from __future__ import annotations

__version__ = "0.1.0"