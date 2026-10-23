"""Unit tests for the ticket automation tool."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from ticket_tool.engine import TicketDatabase
from ticket_tool.models import Ticket, TicketUpdate, SqlCommand


@pytest.fixture
def db() -> TicketDatabase:
    """Create a temporary database for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()
    db = TicketDatabase(db_path=db_path)
    yield db
    os.unlink(db_path)


class TestTicketCreation:
    """Tests for ticket CRUD operations."""

    def test_create_and_get_ticket(self, db: TicketDatabase) -> None:
        ticket = Ticket(
            title="Test ticket",
            description="This is a test",
            customer_name="Alice",
            customer_email="alice@test.com",
            priority="high",
        )
        result = db.create_ticket(ticket)
        assert result.success
        assert result.data[0]["title"] == "Test ticket"

        # Get it back
        get_result = db.get_ticket(result.data[0]["id"])
        assert get_result.success
        assert get_result.data[0]["title"] == "Test ticket"

    def test_create_ticket_with_idempotency(self, db: TicketDatabase) -> None:
        ticket = Ticket(
            title="Idempotent ticket",
            description="Test idempotency",
            customer_name="Bob",
            customer_email="bob@test.com",
        )
        key = "test-create-001"
        result1 = db.create_ticket(ticket, idem_key=key)
        result2 = db.create_ticket(ticket, idem_key=key)
        # Both should succeed but only one ticket created (idempotent)
        assert result1.success
        assert result2.success

    def test_get_nonexistent_ticket(self, db: TicketDatabase) -> None:
        result = db.get_ticket(99999)
        assert not result.success
        assert "not found" in (result.error or "")

    def test_list_tickets(self, db: TicketDatabase) -> None:
        db.seed_demo_data()
        result = db.list_tickets()
        assert result.success
        assert result.affected_rows >= 8  # 8 demo tickets seeded

    def test_list_with_status_filter(self, db: TicketDatabase) -> None:
        db.seed_demo_data()
        result = db.list_tickets(status="open")
        assert result.success
        for t in result.data:
            assert t["status"] == "open"


class TestTicketUpdates:
    """Tests for updating tickets."""

    def test_update_status(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Update test", description="Test", customer_name="C", customer_email="c@t.com")
        create_result = db.create_ticket(ticket)
        tid = create_result.data[0]["id"]

        update = TicketUpdate(status="resolved", resolution="Completed")
        result = db.update_ticket(tid, update)
        assert result.success

        get_result = db.get_ticket(tid)
        assert get_result.data[0]["status"] == "resolved"

    def test_update_nonexistent(self, db: TicketDatabase) -> None:
        update = TicketUpdate(status="resolved")
        result = db.update_ticket(99999, update)
        assert not result.success
        assert "not found" in (result.error or "")

    def test_update_with_idempotency(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Idem test", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        key = "test-update-001"
        update = TicketUpdate(status="resolved", resolution="Done")
        r1 = db.update_ticket(tid, update, idem_key=key)
        r2 = db.update_ticket(tid, update, idem_key=key)
        assert r1.success
        assert r2.success


class TestTicketDeletion:
    """Tests for deleting tickets."""

    def test_delete_ticket(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Delete me", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        result = db.delete_ticket(tid, idem_key="del-test-001")
        assert result.success

        get_result = db.get_ticket(tid)
        assert not get_result.success

    def test_delete_nonexistent(self, db: TicketDatabase) -> None:
        result = db.delete_ticket(99999, idem_key="del-test-002")
        assert not result.success

    def test_delete_with_idempotency(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Idem del", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        key = "del-test-003"
        r1 = db.delete_ticket(tid, idem_key=key)
        r2 = db.delete_ticket(tid, idem_key=key)  # Idempotent — should report success
        assert r1.success
        assert r2.success


class TestAuditLog:
    """Tests for the audit log."""

    def test_audit_logs_creation(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Audit test", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        log_result = db.get_audit_log(ticket_id=tid)
        assert log_result.success
        assert log_result.affected_rows >= 1

    def test_audit_logs_updates(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Audit update", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        db.update_ticket(tid, TicketUpdate(status="resolved"))
        log_result = db.get_audit_log(ticket_id=tid)
        actions = [e["action"] for e in log_result.data]
        assert "update" in actions


class TestSqlCommandValidation:
    """Tests for SQL command validation."""

    def test_valid_select(self) -> None:
        cmd = SqlCommand(sql="SELECT * FROM tickets", params={})
        assert cmd.sql == "SELECT * FROM tickets"

    def test_valid_insert(self) -> None:
        cmd = SqlCommand(sql="INSERT INTO tickets (title) VALUES (:title)", params={"title": "Test"})
        assert cmd.sql.startswith("INSERT")

    def test_rejects_drop(self) -> None:
        with pytest.raises(ValueError, match="unsupported keyword"):
            SqlCommand(sql="DROP TABLE tickets", params={})

    def test_rejects_truncate(self) -> None:
        with pytest.raises(ValueError, match="unsupported keyword"):
            SqlCommand(sql="TRUNCATE TABLE tickets", params={})

    def test_rejects_alter(self) -> None:
        with pytest.raises(ValueError, match="unsupported keyword"):
            SqlCommand(sql="ALTER TABLE tickets ADD COLUMN x", params={})

    def test_rejects_empty(self) -> None:
        import pydantic
        with pytest.raises((ValueError, pydantic.ValidationError)):
            SqlCommand(sql="", params={})