# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Create, get and update crashed: they returned a single row where `ExecutionResult.data` requires a list. They now return a one-row list.
- Deleting any ticket with audit history failed with a foreign-key error, and delete audit entries could never be written. The audit log no longer references `tickets`, so history survives deletes.
- `SqlCommand` accepted chained statements such as `SELECT 1;DROP TABLE tickets`, and rejected `DROP ...` with the wrong error. It now allows one statement only and checks blocked keywords on word boundaries.
- An idempotency key reused for a different write silently returned the other write's result; it is now refused.
- `execution_time_ms` was hard-coded to 0; it is now measured.
- `seed` duplicated the demo tickets on every run.
- `TICKET_DB_PATH` and `TICKET_ENABLE_AUDIT` in `.env.example` were ignored; the CLI now reads them.
- Logs went to stdout and corrupted `--json` output; they now go to stderr.

### Removed

- "Dry-run mode" from the description and the unused `DryRunError`; it was never implemented.

### Added

- CLI tests and tests for audit contents, idempotency conflicts and SQL validation edge cases.

## [0.1.0] — 2025-10-23

### Added

- Ticket CRUD operations (create, read, update, delete) via parameterized SQL.
- SQLite database with WAL mode and foreign keys.
- Idempotency key support on create, update, and delete operations.
- Full audit log of all operations (create, update, delete) with before/after changes.
- SQL command validation: only SELECT/INSERT/UPDATE/DELETE allowed, no DDL.
- 8 demo tickets seeded for testing.
- CLI interface with commands: seed, list, get, create, update, delete, audit.
- Unit tests: CRUD, idempotency, audit logging, SQL validation, error handling.