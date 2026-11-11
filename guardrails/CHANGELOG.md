# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `__init__.py` had an unterminated docstring; the package could not be imported.
- Attack case 26 was not valid JSON (`"..." + "!" * 10000`), so the eval script crashed while loading the dataset.
- Injection detection matched bare substrings ("dan", "override", "hacked"), flagging ordinary words like "Jordan". It now uses word-boundary regexes in a separate `InjectionDetector`.
- Output-validation cases validated a hard-coded sample instead of the case, so they always passed. Each case now carries its own output, and two must be rejected.
- Authorization cases passed by matching phrases copied from the dataset. They, and requests for stored PII, are now reported as skipped (they need a running pipeline).
- API keys containing `-` (e.g. `sk-test-abc-…`) were not redacted.
- PII cases now fail if any detected value survives redaction.

### Added

- 3 benign prompts to catch injection false positives (36 cases total).
- Tests for every PII type, the injection detector, schema validation and the gate script.

## [0.1.0] — 2025-10-23

### Added

- 33 attack cases, regex PII redactor, content validator, evaluation suite and `scripts/eval_guardrails.py`.
