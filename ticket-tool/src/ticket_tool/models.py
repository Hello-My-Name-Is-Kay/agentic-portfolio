"""Data models for the ticket automation tool."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TicketStatus(StrEnum):
    """Status of a support ticket."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class TicketPriority(StrEnum):
    """Priority of a support ticket."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Ticket(BaseModel):
    """A support ticket in the queue."""

    id: int | None = Field(default=None, description="Auto-generated ticket ID")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    status: str = Field(default="open", pattern=r"^(open|in_progress|resolved|closed|reopened)$")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    category: str = Field(default="general", max_length=100)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        """Strip the title and reject a blank one."""
        if not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()


class TicketUpdate(BaseModel):
    """Fields that can be updated on a ticket."""

    status: str | None = Field(default=None, pattern=r"^(open|in_progress|resolved|closed|reopened)$")
    priority: str | None = Field(default=None, pattern=r"^(low|medium|high|critical)$")
    resolution: str | None = Field(default=None, max_length=2000)


class AuditEntry(BaseModel):
    """An audit log entry for ticket operations."""

    id: int | None = None
    ticket_id: int
    action: str = Field(pattern=r"^(create|update|resolve|close|reopen|delete)$")
    changes: dict[str, Any] = Field(default_factory=dict)
    performed_by: str = Field(default="system", max_length=200)
    idempotency_key: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


_BLOCKED_SQL = re.compile(r"\b(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA)\b", re.IGNORECASE)
_ALLOWED_SQL_START = ("SELECT", "INSERT", "UPDATE", "DELETE")


class SqlCommand(BaseModel):
    """A validated ad-hoc SQL statement with named parameters.

    A guard for SQL that comes from outside the tool (e.g. an agent): one
    statement only, DML only, no DDL or connection-level keywords. The CLI's
    own operations use fixed parameterized statements and do not go through it.
    """

    sql: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sql")
    @classmethod
    def no_unsafe_patterns(cls, v: str) -> str:
        """Reject multiple statements, DDL/admin keywords, and anything that is not SELECT/INSERT/UPDATE/DELETE."""
        stripped = v.strip().rstrip(";").strip()
        if ";" in stripped:
            raise ValueError("SQL must be a single statement")
        blocked = _BLOCKED_SQL.search(stripped)
        if blocked:
            raise ValueError(f"SQL contains unsupported keyword: {blocked.group(1).upper()}")
        if not stripped.upper().startswith(_ALLOWED_SQL_START):
            raise ValueError(f"SQL must start with one of: {', '.join(_ALLOWED_SQL_START)}")
        return stripped


class ExecutionResult(BaseModel):
    """Result of a SQL execution."""

    success: bool
    affected_rows: int = 0
    data: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
