# Ticket Automation Tool

> **TL;DR** — SQLite-backed ticket queue with parameterized queries, Pydantic-validated CRUD, idempotency keys on every write (a repeated key replays the result; a reused key for a different write is refused), an audit log that survives deletes, a 7-command CLI, and 8 seeded demo tickets. Built entirely on synthetic data — no legacy code, schemas, or content from any employer.

> **Tags:** `ticket-automation`, `sqlite`, `parameterized-sql`, `idempotency`, `audit-log`, `cli`, `pydantic`, `synthetic-data`

Python-based ticket queue management with parameterized SQL, idempotent writes, and full audit logging.

## Why This Exists

A ground-up rebuild, on synthetic data, of the kind of ticket automation I built in production: the safety properties matter more than the features. Every value goes through `?` placeholders, every write can be retried safely with an idempotency key, and every mutation leaves an audit entry with before/after values. These are the properties an agent needs before it is allowed to write to a ticket queue.

**Context:** the production system this is modelled on handled 35,000–50,000 tickets per year and cut handling time from about 4 to about 2 minutes per ticket. Those figures describe that earlier system; nothing in this repo measures them. (All data here is synthetic — no production data, schemas, or code from any previous employer.)

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
python -m ticket_tool.cli seed     # safe to run twice
```

The database file is `TICKET_DB_PATH` (default `./tickets.db`). Set `TICKET_ENABLE_AUDIT=false` to turn off the audit log.

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
  "ticket": [ { ... } ],     // one-row list (get, create, update)
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
| No SQL injection | Values always go through `?` placeholders. The only dynamic SQL is the `SET` clause of an update, built from a fixed list of column names. |
| Ad-hoc SQL guard | `SqlCommand` accepts one SELECT/INSERT/UPDATE/DELETE statement and rejects `;`-chained statements and DDL/admin keywords (DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, ATTACH, DETACH, PRAGMA). It is a validator for SQL coming from outside (e.g. an agent); the CLI itself never runs ad-hoc SQL. |
| Idempotent writes | Each key is stored with a hash of the operation. Same key + same operation replays the stored result; same key + different operation is refused. |
| Audit trail | Every create/update/delete is logged with before/after values and the idempotency key, and kept after the ticket is deleted. |
| Input validation | Pydantic models validate ticket fields, status and priority values. |

## Testing

```bash
pytest --cov=src --cov-fail-under=80
```

### What the Tests Cover

- **Ticket CRUD**: create, get, list (status/priority filters, limit), update (including no-op updates), delete.
- **Idempotency**: replay returns the original result and does not re-apply; a reused key for a different write is refused; seeding twice does not duplicate.
- **Audit log**: exact before/after changes for creates and updates; history kept after delete; can be disabled.
- **SQL validation**: SELECT/INSERT accepted; DROP/TRUNCATE/ALTER, chained statements and blocked keywords inside DML rejected.
- **CLI**: every command in JSON and text mode against a temp database; not-found errors and exit codes.

## Not built yet

- No web UI (CLI only).
- No authentication or per-user audit attribution (`performed_by` is always `system`).
- No dry-run mode.
- No executor for `SqlCommand`: ad-hoc SQL is validated, not run.

## Related Repos

- [mock-booking-api](../mock-booking-api) — Companion API for the rental domain.
