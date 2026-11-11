# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `__init__.py` had an unterminated docstring; the package could not be imported.
- Reservation IDs were random hex (`R-3FA2B`), which broke the model's `R-\d{5}` pattern and meant the seeded `R-00001` from the README never existed. IDs are now sequential, and restarting no longer seeds a duplicate reservation.
- Errors were returned nested under `detail` instead of the documented `{"status": "error", ...}` envelope; validation errors and unhandled exceptions now use the envelope too (`BAD_INPUT`, `INTERNAL`).
- An `Idempotency-Key` reused for a different request or reservation silently returned the other request's response. It now returns 409 `IDEMPOTENCY_CONFLICT`. The 24h expiry was stored but never checked; it is now enforced.
- The drop-off date could be changed to before the pickup date.
- Thread-local SQLite connections gave each thread its own empty database with `:memory:`; the store now uses one locked connection.
- API key comparison is constant-time and no longer logs part of the rejected key. CORS no longer combines `*` origins with credentials.
- Tests created `TestClient(app)` without running the lifespan, so the store was never initialised; several asserts accepted either 200 or 404.

### Added

- Tests for change/cancel success paths, idempotent replay and conflict, API key enforcement, error envelope, and the store.

## [0.1.0] — 2025-10-23

### Added

- FastAPI application with customer lookup and get/change/cancel reservation endpoints, SQLite store, API key, Idempotency-Key, seeded data.
