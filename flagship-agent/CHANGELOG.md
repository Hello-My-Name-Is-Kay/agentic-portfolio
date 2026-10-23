# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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