"""Ticket automation tool: a SQLite-backed support-ticket queue with a CLI.

Fixed parameterized SQL for every operation, idempotency keys on writes,
an audit log of every mutation, and synthetic demo data only.
"""

from __future__ import annotations

__version__ = "0.1.0"
