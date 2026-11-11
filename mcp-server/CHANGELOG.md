# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- The server could not be imported: `stdio_server` was imported from the wrong module, and the low-level `Server` decorators it used do not exist in `mcp` 2.x (which `mcp>=1.0.0` installs). Ported to `mcp.server.mcpserver.MCPServer` and pinned `mcp>=2.3,<3`.
- `main()` called `server.run(stdio_server())` without awaiting it or passing the streams; the server never started.
- Logs were written to stdout, which would corrupt the stdio JSON-RPC stream; they now go to stderr.
- `reservation_id` was put into the URL path unvalidated (`../admin` would reach other endpoints); it must now match `R-#####`. Dates must be `YYYY-MM-DD`.
- Booking API error codes (`IDEMPOTENCY_CONFLICT`, `BAD_INPUT`, `AUTH_FAILED`) were collapsed into `INTERNAL`.
- Tests called a live `localhost:8000` and accepted either outcome; they now use a mocked transport and assert exact results.

### Changed

- The demo script now drives the server over stdio with the MCP client instead of importing private functions.

## [0.1.0] — 2025-10-23

### Added

- MCP server with 3 tools: get_reservation, change_reservation, cancel_reservation.
- Typed input schemas via Pydantic (all tools validate input).
- Structured error JSON responses (never raises — tools survive failures).
- Idempotency key support on write tools (change, cancel).
- Logging with structlog for every tool call.
- Demo script showing LLM-style tool invocation.
- Tests: each tool returns error JSON on injected failure, valid args.