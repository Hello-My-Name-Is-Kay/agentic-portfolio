"""Eval suite: run a pipeline over the golden dataset and gate on the scores.

The pipeline here is a stand-in that answers from the dataset itself, so the
suite checks the harness end to end; swap in a real pipeline's ``answer``
method to evaluate it. The run writes ``eval-report.json`` for
``scripts/check_eval_threshold.py``.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from eval_harness.dataset import EvalExample, load_dataset
from eval_harness.scorer import EvalResult, EvalSummary, score_example

DATASET = Path(__file__).resolve().parents[1] / "fixtures" / "golden_dataset.jsonl"


class FakePipeline:
    """Answers each golden question with its expected answer and documents."""

    def __init__(self, examples: list[EvalExample]) -> None:
        self._examples = {ex.question: ex for ex in examples}

    def answer(self, question: str) -> tuple[str, list[str]]:
        ex = self._examples.get(question)
        if ex is None:
            return "I don't know", []
        return f"According to policy: {ex.expected_answer_contains}.", ex.expected_docs


class IgnorantPipeline:
    """A broken pipeline: never retrieves anything, never answers."""

    def answer(self, question: str) -> tuple[str, list[str]]:  # noqa: ARG002
        return "I don't know", []


def run_eval(pipeline: FakePipeline | IgnorantPipeline, dataset: list[EvalExample]) -> EvalSummary:
    results: list[EvalResult] = []
    for ex in dataset:
        start = time.monotonic()
        answer, sources = pipeline.answer(ex.question)
        results.append(score_example(ex, answer, sources, latency_s=time.monotonic() - start))
    return EvalSummary(results, min_score=0.85)


@pytest.fixture
def dataset() -> list[EvalExample]:
    return load_dataset(str(DATASET))


def test_pipeline_against_golden_dataset(dataset: list[EvalExample]) -> None:
    summary = run_eval(FakePipeline(dataset), dataset)
    summary.to_json("eval-report.json")
    summary.print_report()
    assert summary.answer_accuracy == 1.0
    assert summary.overall_recall == 1.0
    summary.check_gate()


def test_broken_pipeline_fails_gate(dataset: list[EvalExample]) -> None:
    summary = run_eval(IgnorantPipeline(), dataset)
    assert summary.answer_accuracy == 0.0
    assert summary.overall_recall == 0.0
    assert not summary.passed


def test_dataset_loads_correctly(dataset: list[EvalExample]) -> None:
    assert len(dataset) == 20
    for ex in dataset:
        assert ex.question
        assert ex.expected_answer_contains
        assert ex.expected_docs
        assert ex.rubric.get("criteria"), f"missing rubric criteria: {ex.question}"
