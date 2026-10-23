# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- Golden dataset loader with Pydantic validation (JSONL format, 20+ examples).
- Scorer module: recall@k, answer accuracy, and aggregated EvalSummary.
- LLM-as-judge evaluator via Ollama (rubric-based scoring).
- `check_eval_threshold.py` script: CI gate that fails the build on low scores.
- pytest integration with `--json-report` output.
- CI workflow: lint, type, test, coverage, audit, and eval gate.
- Unit tests for dataset loading and scoring logic.
- Eval tests that simulate pipeline runs against the golden dataset.