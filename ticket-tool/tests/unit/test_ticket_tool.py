"""Unit tests for the ticket automation tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pydantic
import pytest

from ticket_tool.engine import TicketDatabase
from ticket_tool.models import SqlCommand, Ticket, TicketUpdate
from ticket_tool.seed import DEMO_TICKETS

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db(tmp_path: Path) -> TicketDatabase:
    return TicketDatabase(db_path=str(tmp_path / "tickets.db"))


def _ticket(title: str = "T") -> Ticket:
    return Ticket(title=title, description="Test", customer_name="C", customer_email="c@t.com")


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
        assert result.data[0]["priority"] == "high"

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
        assert result1.success
        assert result2 == result1
        assert db.list_tickets().affected_rows == 1

    def test_idempotency_key_reused_for_different_ticket_fails(self, db: TicketDatabase) -> None:
        assert db.create_ticket(_ticket("first"), idem_key="k").success
        result = db.create_ticket(_ticket("second"), idem_key="k")
        assert not result.success
        assert "different operation" in (result.error or "")
        assert db.list_tickets().affected_rows == 1

    def test_execution_time_is_measured(self, db: TicketDatabase) -> None:
        assert db.create_ticket(_ticket()).execution_time_ms > 0

    def test_get_nonexistent_ticket(self, db: TicketDatabase) -> None:
        result = db.get_ticket(99999)
        assert not result.success
        assert "not found" in (result.error or "")

    def test_list_tickets(self, db: TicketDatabase) -> None:
        db.seed_demo_data()
        result = db.list_tickets()
        assert result.success
        assert result.affected_rows == len(DEMO_TICKETS) == 8

    def test_seed_twice_does_not_duplicate(self, db: TicketDatabase) -> None:
        assert db.seed_demo_data() == 8
        assert db.seed_demo_data() == 0
        assert db.list_tickets().affected_rows == 8

    def test_list_limit_and_priority_filter(self, db: TicketDatabase) -> None:
        db.seed_demo_data()
        assert db.list_tickets(limit=3).affected_rows == 3
        critical = db.list_tickets(priority="critical")
        assert {t["title"] for t in critical.data} == {"Payment not processed", "Lost key replacement"}

    def test_list_with_status_filter(self, db: TicketDatabase) -> None:
        db.seed_demo_data()
        result = db.list_tickets(status="open")
        assert result.affected_rows == 5
        assert {t["status"] for t in result.data} == {"open"}


class TestTicketUpdates:
    """Tests for updating tickets."""

    def test_update_status(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Update test", description="Test", customer_name="C", customer_email="c@t.com")
        create_result = db.create_ticket(ticket)
        tid = create_result.data[0]["id"]

        update = TicketUpdate(status="resolved", resolution="Completed")
        result = db.update_ticket(tid, update)
        assert result.success

        row = db.get_ticket(tid).data[0]
        assert (row["status"], row["resolution"]) == ("resolved", "Completed")
        assert row["resolved_at"] is not None

    def test_update_without_changes_is_a_noop(self, db: TicketDatabase) -> None:
        tid = db.create_ticket(_ticket()).data[0]["id"]
        result = db.update_ticket(tid, TicketUpdate(status="open", priority="medium"))
        assert (result.success, result.affected_rows) == (True, 0)
        assert [e["action"] for e in db.get_audit_log(ticket_id=tid).data] == ["create"]

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
        db.update_ticket(tid, TicketUpdate(status="reopened"))
        r2 = db.update_ticket(tid, update, idem_key=key)
        assert r2 == r1  # replayed, not re-applied
        assert db.get_ticket(tid).data[0]["status"] == "reopened"


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
        r2 = db.delete_ticket(tid, idem_key=key)  # replayed: reports the original success
        assert r1.success
        assert r2 == r1
        assert not db.delete_ticket(tid, idem_key="another-key").success

    def test_delete_keeps_audit_history(self, db: TicketDatabase) -> None:
        tid = db.create_ticket(_ticket()).data[0]["id"]
        db.update_ticket(tid, TicketUpdate(priority="high"))
        assert db.delete_ticket(tid).success
        assert [e["action"] for e in db.get_audit_log(ticket_id=tid).data] == ["delete", "update", "create"]


class TestAuditLog:
    """Tests for the audit log."""

    def test_audit_logs_creation(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Audit test", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        log_result = db.get_audit_log(ticket_id=tid)
        assert log_result.affected_rows == 1
        entry = log_result.data[0]
        assert (entry["action"], entry["changes"]) == ("create", {"title": "Audit test"})

    def test_audit_logs_updates(self, db: TicketDatabase) -> None:
        ticket = Ticket(title="Audit update", description="Test", customer_name="C", customer_email="c@t.com")
        cr = db.create_ticket(ticket)
        tid = cr.data[0]["id"]

        db.update_ticket(tid, TicketUpdate(status="resolved"), idem_key="u-1")
        newest = db.get_audit_log(ticket_id=tid).data[0]
        assert newest["action"] == "update"
        assert newest["changes"] == {"status": {"from": "open", "to": "resolved"}}
        assert newest["idempotency_key"] == "u-1"

    def test_audit_can_be_disabled(self, tmp_path: Path) -> None:
        db = TicketDatabase(db_path=str(tmp_path / "t.db"), enable_audit=False)
        db.create_ticket(_ticket())
        assert db.get_audit_log().affected_rows == 0


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
        with pytest.raises(pydantic.ValidationError):
            SqlCommand(sql="", params={})

    @pytest.mark.parametrize(
        "sql",
        ["SELECT 1;DROP TABLE tickets", "SELECT * FROM tickets; DELETE FROM tickets", "select 1 ; pragma x"],
    )
    def test_rejects_multiple_statements(self, sql: str) -> None:
        with pytest.raises(pydantic.ValidationError, match="single statement"):
            SqlCommand(sql=sql)

    def test_rejects_blocked_keyword_inside_dml(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="unsupported keyword: ATTACH"):
            SqlCommand(sql="SELECT * FROM tickets WHERE 1 = 1 ATTACH 'x.db'")

    def test_rejects_non_dml(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="must start with"):
            SqlCommand(sql="VACUUM")

    def test_trailing_semicolon_ok(self) -> None:
        assert SqlCommand(sql="SELECT * FROM tickets;").sql == "SELECT * FROM tickets"
