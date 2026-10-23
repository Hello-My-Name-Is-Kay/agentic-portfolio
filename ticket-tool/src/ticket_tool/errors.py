"""Typed exception hierarchy for the ticket tool."""

from __future__ import annotations


class TicketError(Exception):
    """Base for all ticket tool errors."""


class ConfigError(TicketError):
    """Invalid configuration."""


class ValidationError(TicketError):
    """Input validation failure."""


class ExecutionError(TicketError):
    """SQL execution failure."""


class DryRunError(TicketError):
    """Error during dry-run mode."""


class IdempotencyError(TicketError):
    """Idempotency key conflict."""


class AuditError(TicketError):
    """Audit logging failure."""