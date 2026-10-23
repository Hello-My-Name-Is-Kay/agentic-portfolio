# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- 33 attack cases in checked-in JSONL (prompt injection, PII leakage, output validation, boundary testing, authorization).
- PII redaction module with regex patterns for email, phone, SSN, credit card, driver's license, IP, and API keys.
- Content safety validator with schema validation, citation checks, and prohibited pattern detection.
- Guardrail evaluation suite: runs all attacks through guardrails, generates pass/fail report.
- `scripts/eval_guardrails.py` with CI gate (min 80% pass rate).
- Unit tests for redactor, validator, and suite.
- CI workflow: lint, type, test, coverage, audit, guardrail eval.