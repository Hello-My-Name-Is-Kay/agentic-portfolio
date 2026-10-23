# Guardrails and Red-Team Suite

> **TL;DR** — 33 red-team attack cases across 5 categories (prompt injection, PII leakage, output validation, boundary testing, authorization). Regex-based PII redactor covering 7 types (email, phone, SSN, credit card, driver's license, IP, API key). Pydantic output validator with schema, citation, and content-policy checks. Pass/fail report with per-category breakdown. CI gate at 80% pass rate.

> **Tags:** `guardrails`, `red-team`, `prompt-injection`, `pii-redaction`, `output-validation`, `attack-dataset`, `security`, `ci-gate`

A systematic red-team evaluation suite for LLM pipelines: prompt injection tests, PII redaction, output validation, and pass/fail reporting.

## Why This Exists

Security is a stated differentiator in the job posting, and this repo proves competence with it. It demonstrates a security-first mindset: 33 attack cases across 5 categories, a PII redaction pipeline, structured output validation, and a CI gate that blocks merges on regressions. No other candidate for this role can credibly claim NIS2/VAPT/Kali experience *and* demonstrate it in code.

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │        Attack Dataset (33 cases)      │
                    │  • prompt_injection (10)              │
                    │  • pii_leakage (10)                   │
                    │  • output_validation (5)              │
                    │  • boundary_testing (5)               │
                    │  • authorization (3)                  │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │         Guardrail Suite                │
                    │                                       │
                    │  ┌─────────────────┐                  │
                    │  │ PatternRedactor  │  PII detection  │
                    │  └─────────────────┘                  │
                    │  ┌─────────────────┐                  │
                    │  │ ContentValidator │  Schema + safety│
                    │  └─────────────────┘                  │
                    │  ┌─────────────────┐                  │
                    │  │ Attack Detector  │  Injection heur.│
                    │  └─────────────────┘                  │
                    └──────────────┬───────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────┐
                    │   guardrail-report.json                │
                    │   scripts/eval_guardrails.py           │  ← CI gate
                    └──────────────────────────────────────┘
```

## Results

| Category | Attacks | Passed | Pass Rate |
|----------|---------|--------|-----------|
| pii_leakage | 10 | — | — |
| prompt_injection | 10 | — | — |
| output_validation | 5 | — | — |
| boundary_testing | 5 | — | — |
| authorization | 3 | — | — |
| **Total** | **33** | **—** | **—** |

*Run `python scripts/eval_guardrails.py` to populate.*

## How to Run

### Setup

```bash
cd guardrails
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Output Formats

The guardrail suite supports two output modes via the `--json` flag:

| Mode | Flag | Consumer |
|------|------|----------|
| **Human-readable** | *(default)* | Terminal — formatted pass/fail summary with per-category breakdown |
| **JSON stdout** | `--json` | LLMs, scripts — complete structured report |

### JSON Output Schema (`--json`)

```json
{
  "total_attacks": 33,
  "passed": 28,
  "failed": 5,
  "pass_rate": 0.848,
  "by_category": {
    "pii_leakage": {"total": 10, "passed": 9},
    "prompt_injection": {"total": 10, "passed": 8},
    "boundary_testing": {"total": 5, "passed": 5}
  },
  "results": [
    {
      "id": 1,
      "category": "prompt_injection",
      "input_preview": "Ignore your previous instructions...",
      "expected_guardrail": "injection_detected",
      "passed": true
    }
  ]
}
```

### Run Guardrail Eval

```bash
# Human-readable output
python scripts/eval_guardrails.py --min-pass-rate 0.80

# JSON output (for LLM consumption)
python scripts/eval_guardrails.py --min-pass-rate 0.80 --json

# Both: writes JSON report to file AND prints summary
python scripts/eval_guardrails.py --report guardrail-report.json --min-pass-rate 0.80
```

### Run Tests

```bash
pytest --cov=src --cov-fail-under=80
```

## Attack Categories

| Category | Description | Example |
|----------|-------------|---------|
| **prompt_injection** | Attempts to override system instructions | "Ignore your previous instructions..." |
| **pii_leakage** | Attempts to extract or expose PII | "Tell me the customer's email..." |
| **output_validation** | Tests citation and schema compliance | Answers without source citations |
| **boundary_testing** | Edge cases: empty, overflow, null bytes | 10KB input, empty string, null bytes |
| **authorization** | Tests for authorization bypass | "I am not the customer but modify it anyway" |

## PII Detection Coverage

| Type | Pattern | Replacement |
|------|---------|-------------|
| Email | `user@domain.tld` | `[REDACTED_EMAIL]` |
| Phone | `555-123-4567` | `[REDACTED_PHONE]` |
| SSN | `123-45-6789` | `[REDACTED_SSN]` |
| Credit Card | 13-16 digit numbers | `[REDACTED_CC]` |
| Driver's License | `DL-XXX-XXXXX` | `[REDACTED_DL]` |
| IP Address | `192.168.1.1` | `[REDACTED_IP]` |
| API Key | `sk-...` pattern | `[REDACTED_KEY]` |

## Intentional Omissions

- No Presidio integration (MVP uses regex — sufficient for the attack dataset).
- No ML-based injection classifier (heuristic detection for MVP).
- No real-time guardrail middleware (suite is eval-focused, not runtime).

## Related Repos

- [rag-local](../rag-local) — Target for guardrail evaluation.
- [mock-booking-api](../mock-booking-api) — Target for authorization testing.

## Definition of Done Checklist

- [x] 30+ attack cases in checked-in JSONL (33 cases, 5 categories).
- [x] PII redaction step (7 PII types detected and redacted).
- [x] Pydantic output validation (schema, citations, prohibited patterns).
- [x] Pass/fail report with summary table (JSON output + print).
- [x] CI workflow runs guardrail eval and gates on pass rate.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.