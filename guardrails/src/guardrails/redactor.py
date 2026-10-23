"""PII detection and redaction using pattern matching.

Scans text for common PII patterns (emails, phones, SSNs, credit cards,
driver's license numbers) and replaces them with redacted placeholders.
"""

from __future__ import annotations

from guardrails.logging import get_logger
import re
from typing import Protocol

from guardrails.errors import PIIDetectionError

log = get_logger(__name__)


# ─── PII Patterns ──────────────────────────────────────────────────

PII_PATTERNS: list[tuple[str, str, str]] = [
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]"),
    ("ssn", r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
    ("credit_card", r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED_CC]"),
    ("phone", r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED_PHONE]"),
    ("drivers_license", r"\bDL-\w{3,10}-\d{3,10}\b", "[REDACTED_DL]"),
    ("ip_address", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[REDACTED_IP]"),
    ("api_key", r"\b(sk-[a-zA-Z0-9]{10,}|[A-Za-z0-9]{32,})\b", "[REDACTED_KEY]"),
]

PII_PATTERN_LOOKUP = {name: pattern for name, pattern, _ in PII_PATTERNS}


class Redactor(Protocol):
    """Protocol for PII redactors."""

    def redact(self, text: str) -> str: ...

    def detect(self, text: str) -> list[dict]: ...


class PatternRedactor:
    """Redacts PII using regex pattern matching.

    Not a replacement for a proper NER-based system (Presidio) but
    sufficient for MVP — catches the most common PII types.
    """

    def __init__(self, patterns: list[tuple[str, str, str]] | None = None) -> None:
        self._patterns = patterns or PII_PATTERNS

    def detect(self, text: str) -> list[dict]:
        """Detect PII in text.

        Args:
            text: Input text to scan.

        Returns:
            List of dicts with keys: type, start, end, match.

        Raises:
            PIIDetectionError: If detection fails.
        """
        if not text:
            return []

        findings: list[dict] = []
        for pii_type, pattern, _ in self._patterns:
            try:
                for match in re.finditer(pattern, text):
                    findings.append({
                        "type": pii_type,
                        "start": match.start(),
                        "end": match.end(),
                        "match": match.group(),
                    })
            except re.error as exc:
                log.warning("redactor.regex_error", pii_type=pii_type, error=str(exc))

        return findings

    def redact(self, text: str) -> str:
        """Redact all PII in text.

        Args:
            text: Input text with potential PII.

        Returns:
            Text with PII replaced by placeholders.

        Raises:
            PIIDetectionError: If redaction fails.
        """
        if not text:
            return text

        result = text
        for pii_type, pattern, replacement in self._patterns:
            try:
                result = re.sub(pattern, replacement, result)
            except re.error as exc:
                log.warning("redactor.redact_error", pii_type=pii_type, error=str(exc))
                raise PIIDetectionError(f"Redaction failed for pattern {pii_type}: {exc}") from exc

        return result