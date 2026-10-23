# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- FastAPI application with 4 endpoints: customer lookup, get reservation, change reservation, cancel reservation.
- Pydantic v2 request/response models with validation.
- SQLite persistence with WAL mode for concurrent access.
- Idempotency-Key header support on change and cancel endpoints.
- API key authentication via X-API-Key header (configurable).
- Structured error responses (never raw tracebacks).
- Auto-generated OpenAPI spec at /openapi.json.
- Health check endpoint.
- Seeded test data (2 customers, 1 reservation).
- API tests for all endpoints.