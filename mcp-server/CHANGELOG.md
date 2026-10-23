# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- MCP server with 3 tools: get_reservation, change_reservation, cancel_reservation.
- Typed input schemas via Pydantic (all tools validate input).
- Structured error JSON responses (never raises — tools survive failures).
- Idempotency key support on write tools (change, cancel).
- Logging with structlog for every tool call.
- Demo script showing LLM-style tool invocation.
- Tests: each tool returns error JSON on injected failure, valid args.