# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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