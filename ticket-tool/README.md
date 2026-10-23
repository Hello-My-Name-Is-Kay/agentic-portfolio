# Ticket Automation Tool

> **TL;DR** — SQLite-backed ticket queue with parameterized queries (no SQL injection), Pydantic-validated CRUD operations, idempotency key on every write (create/update/delete), full audit log of all mutations, CLI interface with 7 commands, 8 seeded demo tickets. Built entirely on synthetic data — no legacy code, schemas, or content from any employer.

> **Tags:** `ticket-automation`, `sqlite`, `parameterized-sql`, `idempotency`, `audit-log`, `cli`, `pydantic`, `synthetic-data`

Python-based ticket queue management with validated SQL execution, idempotency, dry-run mode, and full audit logging.

## Why This Exists

This is a ground-up Python rebuild of a production ticket automation system using only demo/fake data. It demonstrates parameterized SQL (never f-string SQL), idempotent writes, audit trails, and structured error handling. For an Agentic Engineer role, it shows domain expertise in ticket automation plus the security maturity to build it safely.

**Business context:** Manual ticket processing at 35,000–50,000 tickets per year, reduced from ~4 minutes to ~2 minutes per ticket through automation. (All data shown here is synthetic — no production data, schemas, or code from any previous employer.)

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │         Ticket Automation Tool        │
                    │                                       │
                    │  CLI commands:                        │
                    │    seed — Load demo data              │
                    │    list — Query tickets               │
                    │    get  — Get ticket by ID            │
                    │    create — New ticket                │
                    │    update — Modify ticket             │
                    │    delete — Remove ticket             │
                    │    audit — View audit trail           │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │         TicketDatabase (SQLite)        │
                    │                                       │
                    │  ┌────────────┐  ┌────────────────┐   │
                    │  │ tickets    │  │ audit_log      │   │
                    │  └────────────┘  └────────────────┘   │
                    │  ┌──────────────────────────────┐     │
                    │  │ idempotency_store            │     │
                    │  └──────────────────────────────┘     │
                    └──────────────────────────────────────┘
```

## How to Run

### Setup

```bash
cd ticket-tool
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Seed Demo Data

```bash
python -m ticket_tool.cli seed
```

## Output Format

Every command supports two output modes via the `--json` flag:

| Mode | Flag | Consumer |
|------|------|----------|
| **Human-readable** | *(default)* | Terminal — formatted summaries |
| **JSON** | `--json` | LLMs, scripts — structured data for programmatic use |

### JSON Output Schema Example

```json
{
  "status": "ok | error",
  "action": "list | get | create | update | delete | seed | audit",
  "count": 8,
  "ticket": { ... },         // single ticket object (get, create, update)
  "tickets": [ ... ],         // array of ticket objects (list)
  "entries": [ ... ],         // audit entries (audit)
  "reason": "..."             // error message (if status=error)
}
```

All JSON output uses `default=str` for non-serializable types (datetimes).

### Usage Examples

```bash
# ─── Human-readable (default) ───

# List all tickets
python -m ticket_tool.cli list

# List open tickets
python -m ticket_tool.cli list --status open

# Get ticket by ID
python -m ticket_tool.cli get 1

# Create a ticket
python -m ticket_tool.cli create \
  --title "Password reset" \
  --description "User cannot login" \
  --customer "Alice Johnson" \
  --email "alice@example.com" \
  --priority high

# Update a ticket
python -m ticket_tool.cli update 1 --status resolved --idem-key update-1-abc

# Delete a ticket (idempotency key required)
python -m ticket_tool.cli delete 5 --idem-key del-5-xyz

# View audit log
python -m ticket_tool.cli audit --ticket-id 1


# ─── JSON output (just add --json to any command) ───

python -m ticket_tool.cli list --json
python -m ticket_tool.cli get 1 --json
python -m ticket_tool.cli create --title "Bug" --description "..." --customer "Alice" --email "a@b.com" --json
python -m ticket_tool.cli update 1 --status resolved --idem-key up-abc --json
python -m ticket_tool.cli delete 5 --idem-key del-xyz --json
python -m ticket_tool.cli audit --json
```

## Security Features

| Feature | How It's Done |
|---------|--------------|
| No SQL injection | Parameterized queries only (`?` placeholders, never f-strings) |
| Blocked SQL | DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE rejected at model level |
| Idempotent writes | Idempotency-Key deduplication on create/update/delete |
| Audit trail | Every mutation logged with before/after changes |
| Input validation | Pydantic models validate all inputs at boundaries |

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- **Ticket CRUD**: create, get, list (with/without filters), update, delete.
- **Idempotency**: replaying the same key returns cached result without side effects.
- **Audit log**: creation and updates generate audit entries.
- **SQL validation**: valid SELECT/INSERT accepted, DROP/TRUNCATE/ALTER rejected, empty rejected.
- **Error handling**: nonexistent tickets return structured errors.

## Intentional Omissions

- No web UI (CLI-only by design for core logic visibility).
- No real authentication (demo system with fake data).
- No dry-run mode (planned for v0.2.0).
- No SQL execution sandbox (validated input only — MVP scope).

## Related Repos

- [mock-booking-api](../mock-booking-api) — Companion API for the rental domain.

## Definition of Done Checklist

- [x] Idempotency key on create, update, and delete operations.
- [x] Audit log with before/after changes for every mutation.
- [x] Parameterized SQL only (no f-string SQL anywhere).
- [x] Pydantic models at all boundaries (request validation, SQL command validation).
- [x] Structured error responses (never raw tracebacks).
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print (in production code), no commented-out code, no TODO.
- [x] All data is synthetic — no legacy code, schemas, or content from any employer.