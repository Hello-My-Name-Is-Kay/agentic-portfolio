"""Structured JSON logging; ``request_id`` and ``thread_id`` are bound per turn."""

from __future__ import annotations

from typing import cast

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Emit one JSON object per log line."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level.upper()),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    """Return a module logger."""
    return cast("structlog.typing.FilteringBoundLogger", structlog.get_logger(name or __name__))
