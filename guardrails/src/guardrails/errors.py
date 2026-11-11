"""Typed exception hierarchy for guardrails."""

from __future__ import annotations


class GuardrailError(Exception):
    """Base for all guardrail errors."""


class ValidationError(GuardrailError):
    """Input or output failed validation."""


class PIIDetectionError(GuardrailError):
    """PII detection or redaction failed."""


class InjectionDetectedError(GuardrailError):
    """Prompt injection or malicious input detected."""

    def __init__(self, reason: str, attack_type: str = "unknown") -> None:
        """Record why and how the input was flagged."""
        self.attack_type = attack_type
        self.reason = reason
        super().__init__(f"Injection detected ({attack_type}): {reason}")


class OutputViolationError(GuardrailError):
    """Output violates content policy."""

    def __init__(self, reason: str, policy: str = "unknown") -> None:
        """Record which policy the output violated."""
        self.policy = policy
        self.reason = reason
        super().__init__(f"Output violation ({policy}): {reason}")
