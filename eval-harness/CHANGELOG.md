# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `judge.py` had a syntax error in its log call; the package could not be imported.
- The judge sent `temperature` at the top level, which Ollama ignores; it now goes in `options`.
- `check_eval_threshold.py` always exited 0, so the CI gate could never fail. It now exits 1 below the threshold.
- CI ran the gate against pytest-json-report output, which has none of the fields the gate reads. It now reads `eval-report.json` written by the eval suite.

### Added

- `score_example()` helper for scoring one pipeline output.
- Tests for the judge (mocked HTTP), the gate script, and a broken-pipeline case.

## [0.1.0] — 2025-10-23

### Added

- Golden dataset loader with Pydantic validation (JSONL, 20 examples).
- Scorer: recall, answer accuracy, aggregated `EvalSummary`.
- LLM-as-judge evaluator via Ollama.
- `check_eval_threshold.py` gate script.
