"""Structured logging configuration using structlog.

Every log line is JSON with timestamp, level, and bound context, written to
stderr so that stdout stays clean for command output (e.g. ``--json``).
"""

from __future__ import annotations

import sys

import structlog


class _Stderr:
    """Write to whatever ``sys.stderr`` is at call time (it may be swapped, e.g. by pytest)."""

    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


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
        logger_factory=structlog.PrintLoggerFactory(_Stderr()),  # type: ignore[arg-type]
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    """Return a structlog logger bound with an optional module name."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name or __name__)
    return logger
