"""Guardrail evaluation suite.

Loads the attack dataset, runs each case through the matching guardrail
(PII redaction, injection detection, output validation, boundary handling)
and produces a pass/fail report.

Cases marked ``requires_pipeline`` (for example authorization checks, or
requests for PII that is not in the input) can only be judged against a
running pipeline; they are reported as skipped, not passed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from guardrails.injection import InjectionDetector
from guardrails.logging import get_logger
from guardrails.redactor import PatternRedactor
from guardrails.validator import ContentSafetyValidator

log = get_logger(__name__)

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "attack_dataset.jsonl"


class ReservationChangeOutput(BaseModel):
    """Schema the output-validation cases expect for a reservation change."""

    reservation_id: str
    new_return_date: str
    status: str


class AttackResult:
    """Result of evaluating a single attack case."""

    def __init__(
        self,
        attack_id: int,
        category: str,
        input_text: str,
        expected_guardrail: str,
        passed: bool,
        details: str = "",
        skipped: bool = False,
    ) -> None:
        """Store the outcome of one case."""
        self.attack_id = attack_id
        self.category = category
        self.input_text = input_text
        self.expected_guardrail = expected_guardrail
        self.passed = passed
        self.details = details
        self.skipped = skipped

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "id": self.attack_id,
            "category": self.category,
            "input_preview": self.input_text[:80],
            "expected_guardrail": self.expected_guardrail,
            "passed": self.passed,
            "skipped": self.skipped,
            "details": self.details,
        }


class GuardrailSuite:
    """Runs the attack dataset through the guardrail components."""

    def __init__(self) -> None:
        """Create the redactor, injection detector and output validator."""
        self._redactor = PatternRedactor()
        self._detector = InjectionDetector()
        self._validator = ContentSafetyValidator()
        self._results: list[AttackResult] = []

    def load_dataset(self, path: str | Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
        """Load attack cases from a JSONL file (blank lines and # comments are skipped)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Attack dataset not found: {path}")

        cases: list[dict[str, Any]] = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cases.append(json.loads(line))
        return cases

    def run_case(self, case: dict[str, Any]) -> AttackResult:
        """Run a single attack case through the relevant guardrail."""
        attack_id = int(case.get("id", 0))
        category = str(case.get("category", "unknown"))
        input_text = str(case.get("input", ""))
        expected = str(case.get("expected_guardrail", "handled_gracefully"))

        if case.get("requires_pipeline"):
            return AttackResult(
                attack_id, category, input_text, expected, False, "Needs a running pipeline to judge", skipped=True
            )

        try:
            if category == "pii_leakage":
                return self._test_pii_redaction(attack_id, category, input_text, expected)
            if category == "prompt_injection":
                return self._test_injection_detection(attack_id, category, input_text, expected)
            if category == "output_validation":
                output = str(case.get("output", ""))
                return self._test_output_validation(attack_id, category, input_text, output, expected)
            if category == "boundary_testing":
                return self._test_boundary(attack_id, category, input_text, expected)
            return AttackResult(attack_id, category, input_text, expected, False, f"Unknown category: {category}")
        except Exception as exc:
            log.exception("suite.attack_error", attack_id=attack_id)
            return AttackResult(attack_id, category, input_text, expected, False, f"Unexpected error: {exc}")

    def _test_pii_redaction(self, attack_id: int, category: str, text: str, expected: str) -> AttackResult:
        """Pass if every PII match is found and none survives redaction."""
        findings = self._redactor.detect(text)
        redacted = self._redactor.redact(text)
        leaked = [f["match"] for f in findings if f["match"] in redacted]

        if expected == "pii_redacted":
            passed = bool(findings) and not leaked
            details = f"Redacted {len(findings)} PII items" if passed else f"Findings: {findings}, leaked: {leaked}"
        else:
            passed = not findings
            details = "No PII found" if passed else f"Unexpected PII findings: {findings}"
        return AttackResult(attack_id, category, text, expected, passed, details)

    def _test_injection_detection(self, attack_id: int, category: str, text: str, expected: str) -> AttackResult:
        """Pass if the detector flags injections and leaves benign prompts alone."""
        matched = self._detector.detect(text)
        if expected == "injection_detected":
            passed = bool(matched)
            details = f"Matched {matched}" if passed else "Injection not detected"
        else:
            passed = not matched
            details = "No injection detected" if passed else f"False positive: {matched}"
        return AttackResult(attack_id, category, text, expected, passed, details)

    def _test_output_validation(
        self, attack_id: int, category: str, text: str, output: str, expected: str
    ) -> AttackResult:
        """Validate the case's sample output; pass if the verdict matches the expectation."""
        if expected == "schema_valid":
            report = self._validator.validate(output, expected_schema=ReservationChangeOutput)
            should_pass = True
        else:
            report = self._validator.validate(output, min_citations=1)
            should_pass = expected == "citations_present"

        passed = report.passed == should_pass
        failed_checks = [c.name for c in report.checks if not c.passed]
        details = f"Validator {'accepted' if report.passed else 'rejected'} output; failed checks: {failed_checks}"
        return AttackResult(attack_id, category, text, expected, passed, details)

    def _test_boundary(self, attack_id: int, category: str, text: str, expected: str) -> AttackResult:
        """Pass if the redactor, detector and validator all handle the input without raising."""
        try:
            self._redactor.redact(text)
            self._detector.detect(text)
            self._validator.validate(text)
        except Exception as exc:
            return AttackResult(attack_id, category, text, expected, False, f"Guardrail crashed: {exc}")
        return AttackResult(attack_id, category, text, expected, True, "Boundary input handled gracefully")

    def run_all(self, dataset_path: str | Path = DEFAULT_DATASET) -> list[AttackResult]:
        """Run all attack cases through the guardrail suite."""
        cases = self.load_dataset(dataset_path)
        log.info("suite.start", count=len(cases))
        self._results = [self.run_case(case) for case in cases]
        log.info("suite.results", passed=sum(r.passed for r in self._results), total=len(self._results))
        return self._results

    def generate_report(self, output_path: str | Path = "guardrail-report.json") -> dict[str, Any]:
        """Write and return a pass/fail report. The pass rate excludes skipped cases."""
        evaluated = [r for r in self._results if not r.skipped]
        passed = sum(1 for r in evaluated if r.passed)
        by_category: dict[str, dict[str, int]] = {}

        for r in self._results:
            stats = by_category.setdefault(r.category, {"total": 0, "passed": 0, "skipped": 0})
            stats["total"] += 1
            if r.skipped:
                stats["skipped"] += 1
            elif r.passed:
                stats["passed"] += 1

        report: dict[str, Any] = {
            "total_attacks": len(self._results),
            "evaluated": len(evaluated),
            "skipped": len(self._results) - len(evaluated),
            "passed": passed,
            "failed": len(evaluated) - passed,
            "pass_rate": round(passed / len(evaluated), 3) if evaluated else 0.0,
            "by_category": by_category,
            "results": [r.to_dict() for r in self._results],
        }

        Path(output_path).write_text(json.dumps(report, indent=2))
        log.info("suite.report_written", path=str(output_path))
        return report

    def print_summary(self) -> None:
        """Print a human-readable summary of results."""
        evaluated = [r for r in self._results if not r.skipped]
        passed = sum(1 for r in evaluated if r.passed)

        print(f"\n{'=' * 60}")
        print("  Guardrail Evaluation Report")
        print(f"{'=' * 60}")
        print(f"  Total cases:      {len(self._results)}")
        print(f"  Skipped:          {len(self._results) - len(evaluated)} (need a running pipeline)")
        print(f"  Passed:           {passed}/{len(evaluated)}")
        print(f"  Pass rate:        {passed / len(evaluated):.1%}" if evaluated else "  Pass rate:        N/A")
        print(f"{'=' * 60}\n")

        by_category: dict[str, list[AttackResult]] = {}
        for r in self._results:
            by_category.setdefault(r.category, []).append(r)

        for cat, items in sorted(by_category.items()):
            cat_passed = sum(1 for r in items if r.passed)
            print(f"  {cat}: {cat_passed}/{len(items)} passed")
            for r in items:
                status = "skip" if r.skipped else ("pass" if r.passed else "FAIL")
                print(f"    {status:4} [{r.attack_id}] {r.input_text[:60].replace(chr(10), ' ')}")
                if not r.passed and not r.skipped:
                    print(f"         {r.details}")
            print()
