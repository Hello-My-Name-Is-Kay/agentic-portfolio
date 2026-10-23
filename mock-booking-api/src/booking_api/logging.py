"""Structured logging configuration using structlog.

Every log line is JSON with timestamp, level, and bound context.
"""
from __future__ import annotations

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog once at startup.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level.upper()),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with an optional module name."""
    return structlog.get_logger(name or __name__)