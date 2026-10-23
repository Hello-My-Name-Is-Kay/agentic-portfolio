"""Typed exception hierarchy for the booking API."""

from __future__ import annotations


class BookingError(Exception):
    """Base for all booking API errors."""


class NotFoundError(BookingError):
    """Resource not found."""


class ValidationError(BookingError):
    """Input validation failure."""


class IdempotencyConflict(BookingError):
    """Idempotency key conflict detected."""


class AuthError(BookingError):
    """Authentication or authorization failure."""


class UpstreamError(BookingError):
    """External dependency failure."""