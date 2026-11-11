# Eval Harness

> **TL;DR** — A small pytest-based evaluation library for LLM pipelines: a JSONL golden dataset (20 Q&A pairs about car-rental policies), substring answer-accuracy and document-recall metrics, an optional LLM-as-judge rubric scorer (Ollama), and a gate script that fails CI when scores fall below a threshold.

> **Tags:** `eval`, `golden-dataset`, `llm-as-judge`, `ci-gate`, `recall`, `pytest`

## Why This Exists

Pipeline changes (prompts, retrieval settings, models) should be checked against a fixed set of questions before they ship. This repo is the scaffolding for that: load a checked-in golden dataset, score each answer, write a JSON report, and fail the build if quality drops.

## What's in the box

| Module | What it does |
|--------|--------------|
| `dataset.py` | Loads/writes the JSONL golden dataset with Pydantic validation; skips comments and reports malformed lines. |
| `scorer.py` | `score_example()` computes per-example recall (fraction of expected docs retrieved) and answer accuracy (case-insensitive substring match). `EvalSummary` aggregates, writes `eval-report.json`, and `check_gate()` raises `ThresholdGateError` below the threshold. |
| `judge.py` | `LlmJudge` sends question, answer and rubric to an Ollama model and returns a 0–1 score (clamped; non-JSON replies score 0). |
| `scripts/check_eval_threshold.py` | Reads `eval-report.json`, exits 1 if answer accuracy or recall is below `--min-score`. |

## Architecture

```
  Golden dataset (JSONL, 20 Q&A + rubrics)
              │ load_dataset()
              ▼
  your pipeline.answer(question) ──► score_example() ──► EvalSummary
                                        (optional LlmJudge      │ to_json()
                                         rubric score)          ▼
                                                     eval-report.json
                                                                │
                                          scripts/check_eval_threshold.py  ← CI gate (exit 1 on regression)
```

## How to Run

```bash
cd eval-harness
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# All tests with coverage (80% gate)
pytest

# Eval suite only; writes eval-report.json
pytest tests/evals

# Gate on the report
python scripts/check_eval_threshold.py eval-report.json --min-score 0.85
python scripts/check_eval_threshold.py eval-report.json --min-score 0.85 --json
```

### Evaluating a real pipeline

The eval suite in `tests/evals/` currently runs a stand-in pipeline that answers from the dataset itself, so it exercises the harness end to end (and a second test checks that a broken pipeline fails the gate). It does **not** evaluate a real RAG system yet. To evaluate one, replace the stand-in with your pipeline:

```python
from eval_harness.dataset import load_dataset
from eval_harness.scorer import EvalSummary, score_example

examples = load_dataset("tests/fixtures/golden_dataset.jsonl")
results = []
for ex in examples:
    answer, sources = my_pipeline.answer(ex.question)  # your code
    results.append(score_example(ex, answer, sources))

summary = EvalSummary(results, min_score=0.85)
summary.to_json("eval-report.json")
summary.check_gate()  # raises ThresholdGateError on regression
```

`LlmJudge(model=..., base_url=...).evaluate(question, answer, ex.rubric)` gives a rubric score you can pass as `score_example(..., rubric_score=...)`. It is reported per example but is not part of the gate.

## JSON Report Schema

```json
{
  "total": 20,
  "correct_answers": 20,
  "answer_accuracy": 1.0,
  "overall_recall": 1.0,
  "min_score": 0.85,
  "passed": true,
  "results": [
    {
      "question": "What is the minimum age to rent a vehicle?",
      "expected_docs": ["policy_006_driver_requirements.md"],
      "retrieved_sources": ["policy_006_driver_requirements.md"],
      "expected_answer_contains": "21",
      "recall": 1.0,
      "answer_ok": true,
      "rubric_score": null,
      "latency_s": 0.0,
      "error": null
    }
  ]
}
```

## Eval Dataset

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | The question to ask |
| `expected_answer_contains` | string | Substring expected in the answer |
| `expected_docs` | list[string] | Source documents that should be retrieved |
| `rubric` | dict | `{"criteria": [...]}` for the LLM judge |

20 questions, written against the policy documents in [rag-local](../rag-local).

## Testing

All tests run offline; the judge's HTTP calls go through `httpx.MockTransport`.

- Dataset loading: missing/empty/malformed files, comment skipping, round trip.
- Scoring: recall, substring matching, aggregation, gate failures on each metric.
- Judge: request shape sent to Ollama, score parsing and clamping, HTTP and connection errors.
- Gate script: pass, fail on each metric, missing report, JSON output.
- Eval suite: stand-in pipeline passes the gate; a broken pipeline fails it.

## Not built yet

- Running the suite against the real `rag-local` pipeline in CI.
- Prompt A/B comparison.
- Tool-trajectory assertions for agents.
- HTML reports.

## Related Repos

- [rag-local](../rag-local) — the RAG pipeline the golden dataset was written for.
