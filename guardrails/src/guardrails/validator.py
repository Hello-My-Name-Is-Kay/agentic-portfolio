"""Output validation using Pydantic models.

Validates that outputs from LLM pipelines conform to expected schemas,
content policies, and safety constraints.
"""

from __future__ import annotations

import json
from guardrails.logging import get_logger
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError as PydanticValidationError

from guardrails.errors import OutputViolation, ValidationError

log = get_logger(__name__)


class SafetyCheck(BaseModel):
    """Result of a single safety check."""

    passed: bool
    name: str
    detail: str = ""


class ValidationReport(BaseModel):
    """Report of all validation checks for an output."""

    passed: bool
    checks: list[SafetyCheck]
    output: str = ""


class OutputValidator(Protocol):
    """Protocol for output validators."""

    def validate(self, output: str, expected_schema: type[BaseModel] | None = None) -> ValidationReport: ...


class ContentSafetyValidator:
    """Validates LLM outputs for safety and schema compliance.

    Checks:
      - JSON parseability (if expected_schema is provided)
      - Schema compliance via Pydantic
      - Presence of prohibited patterns
      - Contains required citations
    """

    def __init__(self) -> None:
        # Prohibited content patterns
        self._prohibited_patterns: list[tuple[str, str]] = [
            ("hate_speech", r"\b(hate|discriminate|racial slur)\b"),
            ("personal_info_request", r"\b(give me.*(ssn|credit card|password))\b"),
            ("dangerous_instruction", r"\b(how to (make|build|create) (bomb|weapon|drug))\b"),
        ]

    def validate(
        self,
        output: str,
        expected_schema: type[BaseModel] | None = None,
        min_citations: int = 0,
    ) -> ValidationReport:
        """Run all validation checks on the output.

        Args:
            output: The generated output string.
            expected_schema: Optional Pydantic model class to validate against.
            min_citations: Minimum number of [Document N] citations expected.

        Returns:
            ValidationReport with individual check results.

        Raises:
            ValidationError: If a critical check fails (when raise_on_fail=True).
        """
        if not output:
            return ValidationReport(passed=False, checks=[
                SafetyCheck(passed=False, name="non_empty", detail="Output is empty"),
            ], output=output)

        checks: list[SafetyCheck] = []

        # Check 1: JSON parseability (if schema expected)
        if expected_schema is not None:
            try:
                data = json.loads(output)
                try:
                    expected_schema(**data)
                    checks.append(SafetyCheck(passed=True, name="schema_valid", detail="Output matches schema"))
                except PydanticValidationError as exc:
                    checks.append(SafetyCheck(
                        passed=False, name="schema_valid",
                        detail=f"Schema validation failed: {exc.errors()}"
                    ))
            except json.JSONDecodeError:
                checks.append(SafetyCheck(passed=False, name="json_parseable", detail="Output is not valid JSON"))

        # Check 2: Prohibited patterns
        for name, pattern in self._prohibited_patterns:
            import re
            if re.search(pattern, output, re.IGNORECASE):
                checks.append(SafetyCheck(passed=False, name=f"no_{name}", detail=f"Output contains prohibited pattern: {name}"))

        # Check 3: Minimum citations
        if min_citations > 0:
            import re
            citations = re.findall(r'\[Document \d+\]', output)
            if len(citations) < min_citations:
                checks.append(SafetyCheck(
                    passed=False, name="min_citations",
                    detail=f"Expected >= {min_citations} citations, found {len(citations)}"
                ))

        if not checks:
            checks.append(SafetyCheck(passed=True, name="no_checks_configured", detail="No validation checks were configured"))

        passed = all(c.passed for c in checks)
        return ValidationReport(passed=passed, checks=checks, output=output)