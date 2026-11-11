"""Guardrails: offline checks for LLM pipeline inputs and outputs.

Regex-based PII redaction, a pattern-based prompt-injection detector, an
output validator (schema, citations, prohibited content), and an attack
dataset that exercises them with a pass/fail report.
"""

from __future__ import annotations

__version__ = "0.1.0"
