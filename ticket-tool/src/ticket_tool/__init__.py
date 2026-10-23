# Ticket Automation Tool — Portfolio Project
#
# Python-based ticket queue automation tool with validated SQL
# execution against SQLite, dry-run mode, audit logging, and
# idempotency.
#
# This is a ground-up rebuild of a production ticket automation
# system, built entirely on fake/demo data. No legacy code,
# schemas, or content from any previous employer.
#
# Demonstrates: SQL injection prevention (parameterized queries),
# idempotent execution, audit trails, dry-run safety, and
# structured error handling.
#
# Business impact context: manual ticket processing at scale
# (35,000-50,000 tickets/year, 4 min → 2 min per ticket).

from __future__ import annotations

__version__ = "0.1.0"