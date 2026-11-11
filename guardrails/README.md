# Guardrails and Red-Team Suite

> **TL;DR** — Offline guardrail components for an LLM pipeline (regex PII redaction for 7 identifier types, a pattern-based prompt-injection detector, a Pydantic output validator) and a 36-case attack dataset that checks them, with a per-category pass/fail report and a CI gate.

> **Tags:** `guardrails`, `red-team`, `prompt-injection`, `pii-redaction`, `output-validation`, `attack-dataset`, `ci-gate`

## Why This Exists

Before an LLM feature ships, its input and output filters should be tested against known attack phrasings the same way code is tested against known bugs. This repo keeps the attacks in a checked-in JSONL file, runs them through the guardrails, and fails CI if the pass rate drops.

## What it is, and what it is not

- **It is** a set of cheap, deterministic, offline checks: regexes and keyword patterns. They run in microseconds and need no model.
- **It is not** an ML classifier or NER system. Injection detection is a list of regex patterns, so paraphrased or obfuscated attacks will get through. PII redaction catches formatted identifiers (emails, phone numbers, card numbers, keys), not names or free-text addresses.
- **The 100% pass rate is on the same dataset the patterns were written against.** It shows the components do what they claim on known cases; it is not a measured detection rate. A held-out attack set would be needed for that.

## Components

| Module | What it does |
|--------|--------------|
| `redactor.py` | `PatternRedactor`: detects and replaces email, phone, SSN, credit card, driver's licence (`DL-…`), IPv4 and API keys (`sk-…` or 32+ char tokens). |
| `injection.py` | `InjectionDetector`: word-boundary regexes for instruction overrides ("ignore … instructions"), role reassignment ("you are now"), system-prompt probes, jailbreak personas, verbatim extraction. |
| `validator.py` | `ContentSafetyValidator`: JSON + Pydantic schema check, minimum `[Document N]` citations, and keyword checks for prohibited content. |
| `suite.py` | `GuardrailSuite`: runs each dataset case through the matching component and builds the report. |

## Attack Dataset (36 cases)

| Category | Cases | How it is judged |
|----------|-------|------------------|
| `prompt_injection` | 13 | 10 attacks must be flagged; 3 benign look-alikes ("Can Jordan be added…", "override fee") must not be. |
| `pii_leakage` | 10 | 7 inputs containing PII must be fully redacted. 3 are *requests* for stored PII; they need a running pipeline and are skipped. |
| `output_validation` | 5 | Each case has a sample model output: one must match a reservation-change schema, two must pass the citation check, two (no citations) must be rejected. |
| `boundary_testing` | 5 | 10 KB input, empty, whitespace, `<script>`, null bytes: no component may raise. |
| `authorization` | 3 | Needs the booking API's access control; skipped. |

Skipped cases are counted separately and excluded from the pass rate.

## How to Run

```bash
cd guardrails
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                                                # unit tests + 80% coverage gate
python scripts/eval_guardrails.py --min-pass-rate 0.80          # human-readable summary
python scripts/eval_guardrails.py --min-pass-rate 0.80 --json   # JSON to stdout
```

The script writes `guardrail-report.json` and exits 1 if the pass rate is below `--min-pass-rate`.

### Report schema

```json
{
  "total_attacks": 36,
  "evaluated": 30,
  "skipped": 6,
  "passed": 30,
  "failed": 0,
  "pass_rate": 1.0,
  "by_category": {
    "prompt_injection": {"total": 13, "passed": 13, "skipped": 0},
    "authorization": {"total": 3, "passed": 0, "skipped": 3}
  },
  "results": [
    {"id": 1, "category": "prompt_injection", "input_preview": "Ignore your previous instructions...",
     "expected_guardrail": "injection_detected", "passed": true, "skipped": false, "details": "Matched ['instruction_override']"}
  ]
}
```

## Not built yet

- Running the skipped cases against a live pipeline (rag-local) and the booking API.
- An ML/NER-based detector (e.g. Presidio for PII, a classifier for injections).
- Runtime middleware; the components are plain functions, and the suite is eval-only.

## Related Repos

- [rag-local](../rag-local) — the pipeline the pipeline-only cases are written for.
- [mock-booking-api](../mock-booking-api) — the API the authorization cases target.
