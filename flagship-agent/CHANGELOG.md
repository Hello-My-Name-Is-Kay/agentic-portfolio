# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] — 2026-11-11

### Changed

- Agent now runs on a real LangGraph `StateGraph` (was a hand-written loop) with an in-memory checkpointer, so each `thread_id` keeps its conversation state between turns.
- Account actions require authentication; change/cancel require single-use step-up re-authentication.
- Reservations are looked up and checked against the authenticated customer before any read or write.
- Cancel idempotency key is now deterministic (`cancel-<reservation_id>`); it was random per call.
- Booking API error details are read from FastAPI's `detail` envelope.
- CI workflow moved to the repository root so GitHub runs it.

### Fixed

- `agent/__init__.py` had an unterminated docstring, so the package could not be imported.
- Lookups looped until the step limit forced a handoff; writes could never complete.
- Tests rewritten: 40 tests with real assertions on replies, API calls and tool trajectories.

### Removed

- Unused `errors.py` and unused Ollama/LLM settings.

## [0.1.0] — 2025-10-23

### Added

- LangGraph-inspired customer service agent with state machine loop.
- Graph nodes: authenticate → classify_intent → execute_tool (+ step-up auth) → respond.
- Step-up authentication for write operations (change/cancel require re-verification).
- Tool implementations: authenticate, lookup_reservation, change_reservation, cancel_reservation, ask_policy.
- Idempotency keys generated per write intent (change, cancel).
- Structured error responses from all tools (never raises).
- AgentState model with auth levels, intent classification, tool trace, and error tracking.
- Node-level step counter; handoff to human after 12 steps.
- `recursion_limit` set at graph level (25).
- Interactive CLI mode for testing.
- Unit tests: auth, lookup, policy, state model, args validation.
- Integration tests: full conversation, error recovery, handoff, multi-turn.