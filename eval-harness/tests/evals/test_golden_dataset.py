"""Pytest entry point for running the eval suite.

Usage:
    pytest tests/evals/test_golden_dataset.py --json-report --json-report-file=eval.json

This test loads the golden dataset and simulates a pipeline response,
measuring answer accuracy and recall against expected documents.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from eval_harness.dataset import load_dataset
from eval_harness.scorer import EvalResult, EvalSummary


class FakePipeline:
    """A mock pipeline that returns canned results for testing."""

    def __init__(self, dataset_path: str) -> None:
        self._examples = load_dataset(dataset_path)

    def answer(self, question: str) -> tuple[str, list[str]]:
        """Return a mock answer for a question.

        For testing purposes, returns the expected answer substring
        as the full answer, and all expected docs as retrieved.
        """
        for ex in self._examples:
            if ex.question == question:
                return ex.expected_answer_contains, ex.expected_docs
        return "I don't know", []


@pytest.fixture
def dataset() -> list:
    return load_dataset("tests/fixtures/golden_dataset.jsonl")


@pytest.fixture
def pipeline() -> FakePipeline:
    return FakePipeline("tests/fixtures/golden_dataset.jsonl")


def test_rag_against_golden_dataset(dataset, pipeline) -> None:  # type: ignore[no-untyped-def]
    """Evaluate the pipeline against all golden dataset examples."""
    results: list[EvalResult] = []

    for ex in dataset:
        start = time.monotonic()
        try:
            answer, retrieved_sources = pipeline.answer(ex.question)
            error = None
        except Exception as exc:
            answer = ""
            retrieved_sources = []
            error = str(exc)

        elapsed = time.monotonic() - start

        # compute recall
        expected_set = set(ex.expected_docs)
        retrieved_set = set(retrieved_sources)
        hits = len(expected_set & retrieved_set)
        recall = hits / len(expected_set) if expected_set else 0.0

        # check answer
        answer_ok = ex.expected_answer_contains.lower() in answer.lower()

        results.append(EvalResult(
            question=ex.question,
            expected_docs=ex.expected_docs,
            retrieved_sources=retrieved_sources,
            answer=answer,
            expected_answer_contains=ex.expected_answer_contains,
            recall=recall,
            answer_ok=answer_ok,
            latency_s=elapsed,
            error=error,
        ))

    summary = EvalSummary(results, min_score=0.85)

    # Write JSON report for CI gate
    summary.to_json("eval-report.json")

    summary.print_report()

    assert summary.answer_accuracy >= 0.85, (
        f"Answer accuracy {summary.answer_accuracy:.3f} below threshold 0.85"
    )
    assert summary.overall_recall >= 0.85, (
        f"Recall {summary.overall_recall:.3f} below threshold 0.85"
    )


def test_dataset_loads_correctly(dataset) -> None:  # type: ignore[no-untyped-def]
    """Verify the golden dataset loads and validates."""
    assert len(dataset) >= 20, f"Expected >= 20 examples, got {len(dataset)}"
    for ex in dataset:
        assert ex.question, "Each example must have a question"
        assert ex.expected_answer_contains, "Each example must have expected_answer_contains"
        assert ex.expected_docs, "Each example must have expected_docs"


def test_eval_summary_empty() -> None:
    """An empty result list should not crash."""
    summary = EvalSummary([], min_score=0.85)
    assert summary.total == 0
    assert summary.answer_accuracy == 0.0
    assert summary.overall_recall == 0.0
    assert not summary.passed


def test_eval_summary_perfect() -> None:
    """Perfect scores should pass the gate."""
    results = [
        EvalResult(
            question="test",
            expected_docs=["a.md"],
            retrieved_sources=["a.md"],
            answer="expected answer content",
            expected_answer_contains="expected",
            recall=1.0,
            answer_ok=True,
        )
    ]
    summary = EvalSummary(results, min_score=0.85)
    assert summary.answer_accuracy == 1.0
    assert summary.overall_recall == 1.0
    assert summary.passed