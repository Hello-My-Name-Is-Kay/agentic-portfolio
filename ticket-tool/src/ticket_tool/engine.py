"""Database engine: SQLite with parameterized queries, audit logging, and idempotency.

Every statement uses ``?`` placeholders for values. The only dynamic SQL is
the SET clause in ``update_ticket``, built from a fixed set of column names.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ticket_tool.errors import ExecutionError
from ticket_tool.logging import get_logger
from ticket_tool.models import ExecutionResult

if TYPE_CHECKING:
    from ticket_tool.models import Ticket, TicketUpdate

log = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(operation: str, payload: Any) -> str:
    raw = json.dumps({"op": operation, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class TicketDatabase:
    """SQLite database for the ticket automation system.

    - Parameterized queries only.
    - Idempotency keys: repeating a write with the same key returns the stored
      result without writing again; reusing a key for a different write fails.
    - Audit log of every create, update and delete (kept after a ticket is deleted).
    """

    def __init__(self, db_path: str = "tickets.db", enable_audit: bool = True) -> None:
        """Open (or create) the database at ``db_path``."""
        self._db_path = db_path
        self._enable_audit = enable_audit
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'medium',
                category TEXT NOT NULL DEFAULT 'general',
                resolution TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                resolved_at TEXT
            );

            -- No foreign key to tickets: audit entries must survive the ticket's deletion.
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                changes TEXT NOT NULL DEFAULT '{}',
                performed_by TEXT NOT NULL DEFAULT 'system',
                idempotency_key TEXT,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS idempotency_records (
                idem_key TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
            CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_log(ticket_id);
            """
        )
        conn.commit()

    # ─── Ticket CRUD ───────────────────────────────────────────────

    def create_ticket(self, ticket: Ticket, idem_key: str | None = None) -> ExecutionResult:
        """Create a new ticket.

        Args:
            ticket: Ticket data.
            idem_key: Optional idempotency key for safe retry.

        Returns:
            ExecutionResult whose ``data`` holds the created ticket row.
        """
        start = time.perf_counter()
        fingerprint = _fingerprint("create", ticket.model_dump(exclude={"id", "created_at", "updated_at"}))
        replay = self._replay(idem_key, fingerprint)
        if replay is not None:
            return replay

        conn = self._get_conn()
        now = _now()
        try:
            cursor = conn.execute(
                """INSERT INTO tickets
                   (title, description, customer_name, customer_email, status,
                    priority, category, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket.title,
                    ticket.description,
                    ticket.customer_name,
                    ticket.customer_email,
                    ticket.status,
                    ticket.priority,
                    ticket.category,
                    now,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to create ticket: {exc}") from exc

        ticket_id = int(cursor.lastrowid or 0)
        rows = self._ticket_rows(ticket_id)
        if self._enable_audit:
            self._log_audit(ticket_id, "create", {"title": ticket.title}, idem_key=idem_key)
        result = ExecutionResult(success=True, data=rows, affected_rows=1, execution_time_ms=self._ms_since(start))
        self._remember(idem_key, fingerprint, result)
        return result

    def get_ticket(self, ticket_id: int) -> ExecutionResult:
        """Get a single ticket by ID (``data`` is a one-row list)."""
        rows = self._ticket_rows(ticket_id)
        if rows:
            return ExecutionResult(success=True, data=rows, affected_rows=1)
        return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")

    def list_tickets(self, status: str | None = None, priority: str | None = None, limit: int = 50) -> ExecutionResult:
        """List tickets, newest first, with optional status/priority filters."""
        start = time.perf_counter()
        query = "SELECT * FROM tickets WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        try:
            rows = self._get_conn().execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to list tickets: {exc}") from exc

        data = [dict(r) for r in rows]
        return ExecutionResult(
            success=True, data=data, affected_rows=len(data), execution_time_ms=self._ms_since(start)
        )

    def update_ticket(self, ticket_id: int, update: TicketUpdate, idem_key: str | None = None) -> ExecutionResult:
        """Update a ticket's status, priority, or resolution; the audit entry records before/after values."""
        start = time.perf_counter()
        fingerprint = _fingerprint("update", {"id": ticket_id, **update.model_dump()})
        replay = self._replay(idem_key, fingerprint)
        if replay is not None:
            return replay

        existing_rows = self._ticket_rows(ticket_id)
        if not existing_rows:
            return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")
        existing = existing_rows[0]

        columns: dict[str, Any] = {}
        changes: dict[str, Any] = {}
        now = _now()

        if update.status and update.status != existing["status"]:
            columns["status"] = update.status
            changes["status"] = {"from": existing["status"], "to": update.status}
            if update.status == "resolved":
                columns["resolved_at"] = now
        if update.priority and update.priority != existing["priority"]:
            columns["priority"] = update.priority
            changes["priority"] = {"from": existing["priority"], "to": update.priority}
        if update.resolution is not None and update.resolution != existing["resolution"]:
            columns["resolution"] = update.resolution
            changes["resolution"] = {"from": existing["resolution"], "to": update.resolution}

        if not columns:
            return ExecutionResult(success=True, data=existing_rows, affected_rows=0)

        columns["updated_at"] = now
        assignments = ", ".join(f"{name} = ?" for name in columns)  # names come from the fixed set above
        try:
            conn = self._get_conn()
            conn.execute(f"UPDATE tickets SET {assignments} WHERE id = ?", [*columns.values(), ticket_id])
            conn.commit()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to update ticket {ticket_id}: {exc}") from exc

        if self._enable_audit:
            self._log_audit(ticket_id, "update", changes, idem_key=idem_key)
        rows = self._ticket_rows(ticket_id)
        result = ExecutionResult(success=True, data=rows, affected_rows=1, execution_time_ms=self._ms_since(start))
        self._remember(idem_key, fingerprint, result)
        return result

    def delete_ticket(self, ticket_id: int, idem_key: str | None = None) -> ExecutionResult:
        """Delete a ticket. Its audit history is kept."""
        start = time.perf_counter()
        fingerprint = _fingerprint("delete", {"id": ticket_id})
        replay = self._replay(idem_key, fingerprint)
        if replay is not None:
            return replay

        try:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            conn.commit()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to delete ticket {ticket_id}: {exc}") from exc

        if cursor.rowcount == 0:
            return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")

        if self._enable_audit:
            self._log_audit(ticket_id, "delete", {}, idem_key=idem_key)
        result = ExecutionResult(success=True, affected_rows=cursor.rowcount, execution_time_ms=self._ms_since(start))
        self._remember(idem_key, fingerprint, result)
        return result

    # ─── Audit ─────────────────────────────────────────────────────

    def get_audit_log(self, ticket_id: int | None = None, limit: int = 100) -> ExecutionResult:
        """Get audit log entries, newest first; ``changes`` is decoded from JSON."""
        conn = self._get_conn()
        if ticket_id is not None:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE ticket_id = ? ORDER BY id DESC LIMIT ?", (ticket_id, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        data = [{**dict(r), "changes": json.loads(r["changes"])} for r in rows]
        return ExecutionResult(success=True, data=data, affected_rows=len(data))

    def _log_audit(self, ticket_id: int, action: str, changes: dict[str, Any], idem_key: str | None = None) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO audit_log (ticket_id, action, changes, idempotency_key, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (ticket_id, action, json.dumps(changes), idem_key, _now()),
            )
            conn.commit()
        except sqlite3.Error as exc:
            log.warning("audit.write_failed", ticket_id=ticket_id, action=action, error=str(exc))

    # ─── Idempotency ───────────────────────────────────────────────

    def _replay(self, idem_key: str | None, fingerprint: str) -> ExecutionResult | None:
        """Return the stored result for a repeated key, or an error if the key was used for another write."""
        if not idem_key:
            return None
        row = (
            self._get_conn()
            .execute("SELECT fingerprint, result FROM idempotency_records WHERE idem_key = ?", (idem_key,))
            .fetchone()
        )
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            return ExecutionResult(
                success=False, error=f"Idempotency key '{idem_key}' was used for a different operation"
            )
        log.info("idempotency.replay", key=idem_key)
        return ExecutionResult.model_validate_json(row["result"])

    def _remember(self, idem_key: str | None, fingerprint: str, result: ExecutionResult) -> None:
        if not idem_key:
            return
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO idempotency_records VALUES (?, ?, ?, ?)",
            (idem_key, fingerprint, result.model_dump_json(), time.time()),
        )
        conn.commit()

    # ─── Helpers ───────────────────────────────────────────────────

    def _ticket_rows(self, ticket_id: int) -> list[dict[str, Any]]:
        row = self._get_conn().execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return [dict(row)] if row else []

    @staticmethod
    def _ms_since(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 3)

    # ─── Seed Data ─────────────────────────────────────────────────

    def seed_demo_data(self) -> int:
        """Insert the demo tickets; safe to run twice. Returns how many tickets are new."""
        from ticket_tool.seed import DEMO_TICKETS

        before = self.list_tickets(limit=10_000).affected_rows
        for i, ticket in enumerate(DEMO_TICKETS):
            self.create_ticket(ticket, idem_key=f"seed-demo-{i}")
        return self.list_tickets(limit=10_000).affected_rows - before
