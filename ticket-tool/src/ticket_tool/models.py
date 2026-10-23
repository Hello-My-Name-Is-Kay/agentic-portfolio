"""Data models for the ticket automation tool."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TicketStatus(str, Enum):
    """Status of a support ticket."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class TicketPriority(str, Enum):
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
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
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
    changes: dict = Field(default_factory=dict)
    performed_by: str = Field(default="system", max_length=200)
    idempotency_key: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SqlCommand(BaseModel):
    """A validated SQL command to execute."""

    sql: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)

    @field_validator("sql")
    @classmethod
    def no_unsafe_patterns(cls, v: str) -> str:
        """Reject known dangerous patterns."""
        v_upper = v.upper().strip()
        # Only allow SELECT, INSERT, UPDATE, DELETE
        allowed = ("SELECT", "INSERT", "UPDATE", "DELETE")
        if not any(v_upper.startswith(a) for a in allowed):
            raise ValueError(f"SQL must start with one of: {', '.join(allowed)}")
        # Block DROP, TRUNCATE, ALTER, CREATE, GRANT
        blocked = ("DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE")
        for b in blocked:
            if b in v_upper.split():
                raise ValueError(f"SQL contains unsupported keyword: {b}")
        return v.strip()


class ExecutionResult(BaseModel):
    """Result of a SQL execution."""

    success: bool
    affected_rows: int = 0
    data: list[dict] = Field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0