"""Mock booking API: a small FastAPI service for a fictional car rental company.

Customer lookup and reservation get/change/cancel endpoints with Pydantic
validation, SQLite persistence, an optional API key, Idempotency-Key support
on writes, and a flat JSON error envelope.
"""

from __future__ import annotations

__version__ = "0.1.0"
