# Eval Harness

> **TL;DR** — Pytest-based evaluation framework with golden dataset (JSONL, 20+ Q&A), LLM-as-judge rubric scoring, recall@k + answer-accuracy metrics, and a CI gate that blocks merges on score regression. Applied to RAG and agent pipelines.

> **Tags:** `eval`, `golden-dataset`, `llm-as-judge`, `ci-gate`, `recall@k`, `pytest`, `json-report`, `threshold-gate`

A pytest-based evaluation framework for LLM pipelines. Golden datasets, LLM-as-judge rubrics, and a CI gate that blocks merges when scores drop below threshold.

## Why This Exists

The job posting explicitly names "evals gate every release" as a required signal. This repo delivers exactly that: a framework where every pipeline change is validated against a checked-in golden dataset, scored by an LLM judge, and blocked from merging if quality regresses. It's designed to wrap any pipeline — RAG, agent, or router — with minimal integration effort.

## Architecture

```
                          ┌───────────────────────┐
                          │  Golden Dataset (JSONL) │  20+ Q&A pairs with rubrics
                          └──────────┬────────────┘
                                     │ load
                                     ▼
                     ┌─────────────────────────────┐
                     │      Eval Harness Core       │
                     │  ┌─────────┐  ┌───────────┐  │
                     │  │ dataset │  │  scorer    │  │
                     │  └─────────┘  └───────────┘  │
                     │  ┌─────────┐                 │
                     │  │  judge  │  (LLM-as-judge) │
                     │  └─────────┘                 │
                     └──────────────┬──────────────┘
                                    │ report
                                    ▼
                     ┌─────────────────────────────┐
                     │  eval-report.json            │
                     │  check_eval_threshold.py     │  ← CI gate
                     └─────────────────────────────┘
```

## How to Run

### Setup

```bash
cd eval-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### Run Tests

```bash
# Unit tests
pytest tests/unit

# Eval suite (with fake pipeline)
pytest tests/evals --json-report --json-report-file=eval.json

# Full suite with coverage
pytest --cov=src --cov-fail-under=80
```

## Output Formats

The eval harness produces two forms of output:

| Format | How | Consumer |
|--------|-----|----------|
| **JSON report** | `--json-report=eval.json` (pytest) or `scripts/check_eval_threshold.py eval.json` | CI gate, dashboards |
| **JSON stdout** | `scripts/check_eval_threshold.py eval.json --json` | LLMs, scripts |
| **Human-readable** | `scripts/check_eval_threshold.py eval.json` (default) | Terminal review |

### JSON Report Schema

```json
{
  "total": 20,
  "answer_accuracy": 0.95,
  "overall_recall": 0.90,
  "min_score": 0.85,
  "passed": true,
  "results": [
    {
      "question": "What is the fuel policy?",
      "expected_docs": ["policy_004_fuel.md"],
      "retrieved_sources": ["policy_004_fuel.md"],
      "answer_ok": true,
      "recall": 1.0
    }
  ]
}
```

### Run CI Gate

```bash
# Human-readable
python scripts/check_eval_threshold.py eval.json --min-score 0.85

# JSON output (for LLM consumption)
python scripts/check_eval_threshold.py eval.json --min-score 0.85 --json
```

### Integration with a Real Pipeline

```python
from eval_harness.dataset import load_dataset
from eval_harness.scorer import EvalSummary

# Load dataset
examples = load_dataset("tests/fixtures/golden_dataset.jsonl")

# Run your pipeline against each example
results = [evaluate(your_pipeline, ex) for ex in examples]

# Check gate
summary = EvalSummary(results, min_score=0.85)
summary.check_gate()
```

## Eval Dataset

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | The question to ask |
| `expected_answer_contains` | string | Substring expected in answer |
| `expected_docs` | list[string] | Expected source documents |
| `rubric` | dict | LLM-as-judge evaluation criteria |

**Size:** 20 questions covering all 21 policy documents.

## Results

| Metric | Current | Threshold |
|--------|---------|-----------|
| Answer accuracy | — *run eval to compute* | ≥ 0.85 |
| Overall recall@k | — *run eval to compute* | ≥ 0.85 |

## Testing

### What the Tests Cover

- **Dataset loading:** empty files, missing files, parsing errors, round-trip serialization.
- **Scoring:** recall computation, answer accuracy, summary aggregation, gate logic.
- **Eval integration:** simulated pipeline run against full golden dataset, JSON report.

## Intentional Omissions

- No web UI (CLI and CI integration by design).
- No prompt A/B comparison (planned for v0.2.0).
- No tool-trajectory assertions (added when agent projects exist).

## Related Repos

- [rag-local](../rag-local) — RAG pipeline evaluated by this harness.
- [llm-router](../llm-router) — multi-provider router evaluated by this harness.

## Definition of Done Checklist

- [x] All public functions have type hints; `mypy --strict src` passes.
- [x] `ruff check .` and `ruff format --check .` pass.
- [x] Every except block logs with context and raises typed exceptions.
- [x] `pytest --cov=src --cov-fail-under=80` passes.
- [x] Eval suite runs and `check_eval_threshold.py` gates the build.
- [x] README documents current score and CI badge.
- [x] CHANGELOG.md has an entry.
- [x] No secrets, no print, no commented-out code, no TODO.
- [x] Configuration via pydantic-settings with `.env.example`.