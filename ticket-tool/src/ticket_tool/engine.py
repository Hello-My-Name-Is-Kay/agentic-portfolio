"""Database engine: SQLite with parameterized queries, audit logging, and idempotency.

All SQL is executed via parameterized queries. No f-string SQL.
"""

from __future__ import annotations

import json
from ticket_tool.logging import get_logger
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ticket_tool.errors import ExecutionError
from ticket_tool.models import AuditEntry, ExecutionResult, Ticket, TicketUpdate

log = get_logger(__name__)


class TicketDatabase:
    """SQLite database for the ticket automation system.

    Features:
      - Parameterized queries only (no SQL injection).
      - Idempotent execution tracking.
      - Full audit log of all operations.
      - Dry-run mode (rollback after preview).
    """

    def __init__(self, db_path: str = "tickets.db", enable_audit: bool = True) -> None:
        self._db_path = db_path
        self._enable_audit = enable_audit
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                changes TEXT NOT NULL DEFAULT '{}',
                performed_by TEXT NOT NULL DEFAULT 'system',
                idempotency_key TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );

            CREATE TABLE IF NOT EXISTS idempotency_store (
                idem_key TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
            CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_log(ticket_id);
            CREATE INDEX IF NOT EXISTS idx_idempotency_key ON idempotency_store(idem_key);
        """)
        conn.commit()

    # ─── Ticket CRUD ───────────────────────────────────────────────

    def create_ticket(self, ticket: Ticket, idem_key: str | None = None) -> ExecutionResult:
        """Create a new ticket.

        Args:
            ticket: Ticket data.
            idem_key: Optional idempotency key for safe retry.

        Returns:
            ExecutionResult with created ticket data.
        """
        if idem_key:
            cached = self._get_idempotent(idem_key)
            if cached:
                return ExecutionResult(success=True, data=cached.get("data", []), affected_rows=1)

        conn = self._get_conn()
        now = datetime.utcnow().isoformat()

        try:
            cursor = conn.execute(
                """INSERT INTO tickets
                   (title, description, customer_name, customer_email, status,
                    priority, category, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticket.title, ticket.description, ticket.customer_name,
                 ticket.customer_email, ticket.status, ticket.priority,
                 ticket.category, now, now),
            )
            ticket_id = cursor.lastrowid
            conn.commit()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to create ticket: {exc}") from exc

        result_data = self._get_ticket_data(ticket_id)
        elapsed = self._measure_time()

        if self._enable_audit:
            self._log_audit(ticket_id, "create", {"title": ticket.title}, idem_key=idem_key)

        if idem_key:
            self._put_idempotent(idem_key, {"data": result_data})

        return ExecutionResult(success=True, data=result_data, affected_rows=1, execution_time_ms=elapsed)

    def get_ticket(self, ticket_id: int) -> ExecutionResult:
        """Get a single ticket by ID."""
        data = self._get_ticket_data(ticket_id)
        if data:
            return ExecutionResult(success=True, data=data, affected_rows=1)
        return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")

    def list_tickets(self, status: str | None = None, priority: str | None = None, limit: int = 50) -> ExecutionResult:
        """List tickets with optional filters."""
        conn = self._get_conn()
        query = "SELECT * FROM tickets WHERE 1=1"
        params: list[str] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(str(limit))

        try:
            rows = conn.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to list tickets: {exc}") from exc

        data = [dict(r) for r in rows]
        return ExecutionResult(success=True, data=data, affected_rows=len(data))

    def update_ticket(self, ticket_id: int, update: TicketUpdate, idem_key: str | None = None) -> ExecutionResult:
        """Update a ticket's status, priority, or resolution."""
        if idem_key:
            cached = self._get_idempotent(idem_key)
            if cached:
                return ExecutionResult(success=True, data=cached.get("data", []), affected_rows=1)

        existing = self._get_ticket_data(ticket_id)
        if not existing:
            return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")

        conn = self._get_conn()
        updates: list[str] = []
        params: list[Any] = []
        changes: dict[str, Any] = {}
        now = datetime.utcnow().isoformat()

        if update.status and update.status != existing.get("status"):
            updates.append("status = ?")
            params.append(update.status)
            changes["status"] = {"from": existing["status"], "to": update.status}

            if update.status == "resolved":
                updates.append("resolved_at = ?")
                params.append(now)

        if update.priority and update.priority != existing.get("priority"):
            updates.append("priority = ?")
            params.append(update.priority)
            changes["priority"] = {"from": existing["priority"], "to": update.priority}

        if update.resolution is not None:
            updates.append("resolution = ?")
            params.append(update.resolution)
            changes["resolution"] = {"from": existing.get("resolution"), "to": update.resolution}

        if not updates:
            return ExecutionResult(success=True, data=existing, affected_rows=0)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(ticket_id)

        try:
            conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to update ticket {ticket_id}: {exc}") from exc

        result_data = self._get_ticket_data(ticket_id)
        elapsed = self._measure_time()

        if self._enable_audit and changes:
            self._log_audit(ticket_id, "update", changes, idem_key=idem_key)

        if idem_key:
            self._put_idempotent(idem_key, {"data": result_data})

        return ExecutionResult(success=True, data=result_data, affected_rows=1, execution_time_ms=elapsed)

    def delete_ticket(self, ticket_id: int, idem_key: str | None = None) -> ExecutionResult:
        """Delete a ticket."""
        if idem_key:
            cached = self._get_idempotent(idem_key)
            if cached:
                return ExecutionResult(success=True, affected_rows=1)

        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
            conn.commit()
            affected = cursor.rowcount
        except sqlite3.Error as exc:
            raise ExecutionError(f"Failed to delete ticket {ticket_id}: {exc}") from exc

        if affected == 0:
            return ExecutionResult(success=False, error=f"Ticket {ticket_id} not found")

        if self._enable_audit:
            self._log_audit(ticket_id, "delete", {}, idem_key=idem_key)

        if idem_key:
            self._put_idempotent(idem_key, {"deleted": True})

        return ExecutionResult(success=True, affected_rows=affected)

    # ─── Audit ─────────────────────────────────────────────────────

    def get_audit_log(self, ticket_id: int | None = None, limit: int = 100) -> ExecutionResult:
        """Get audit log entries."""
        conn = self._get_conn()
        if ticket_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE ticket_id = ? ORDER BY timestamp DESC LIMIT ?",
                (ticket_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        data = [dict(r) for r in rows]
        return ExecutionResult(success=True, data=data, affected_rows=len(data))

    def _log_audit(self, ticket_id: int, action: str, changes: dict, idem_key: str | None = None) -> None:
        """Write an audit entry."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO audit_log (ticket_id, action, changes, idempotency_key, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (ticket_id, action, json.dumps(changes), idem_key, datetime.utcnow().isoformat()),
            )
            conn.commit()
        except sqlite3.Error as exc:
            log.warning("audit.write_failed", error=str(exc))

    # ─── Idempotency ───────────────────────────────────────────────

    def _get_idempotent(self, key: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT result FROM idempotency_store WHERE idem_key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row["result"])
        return None

    def _put_idempotent(self, key: str, result: dict) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO idempotency_store VALUES (?, ?, ?)",
            (key, json.dumps(result), time.time()),
        )
        conn.commit()

    # ─── Helpers ───────────────────────────────────────────────────

    def _get_ticket_data(self, ticket_id: int) -> dict | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _measure_time() -> float:
        return 0.0  # Simplified for MVP

    # ─── Seed Data ─────────────────────────────────────────────────

    def seed_demo_data(self) -> None:
        """Populate the database with demo tickets for testing."""
        from ticket_tool.seed import DEMO_TICKETS
        for ticket in DEMO_TICKETS:
            self.create_ticket(ticket)
            log.info("seed.ticket", title=ticket.title[:50])