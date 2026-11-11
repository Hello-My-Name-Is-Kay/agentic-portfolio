"""Scoring logic: compute metrics from evaluation results.

Includes:
  - recall (fraction of expected documents that were retrieved)
  - answer_accuracy (does the answer contain the expected substring?)
  - an optional rubric score slot, filled by eval_harness.judge.LlmJudge
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eval_harness.errors import ThresholdGateError

if TYPE_CHECKING:
    from eval_harness.dataset import EvalExample


class EvalResult:
    """Result of evaluating a single example."""

    def __init__(
        self,
        question: str,
        expected_docs: list[str],
        retrieved_sources: list[str],
        answer: str,
        expected_answer_contains: str,
        recall: float,
        answer_ok: bool,
        rubric_score: float | None = None,
        latency_s: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Store the outcome of one example."""
        self.question = question
        self.expected_docs = expected_docs
        self.retrieved_sources = retrieved_sources
        self.answer = answer
        self.expected_answer_contains = expected_answer_contains
        self.recall = recall
        self.answer_ok = answer_ok
        self.rubric_score = rubric_score
        self.latency_s = latency_s
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "question": self.question,
            "expected_docs": self.expected_docs,
            "retrieved_sources": self.retrieved_sources,
            "expected_answer_contains": self.expected_answer_contains,
            "recall": round(self.recall, 3),
            "answer_ok": self.answer_ok,
            "rubric_score": round(self.rubric_score, 3) if self.rubric_score is not None else None,
            "latency_s": round(self.latency_s, 2),
            "error": self.error,
        }


class EvalSummary:
    """Aggregated evaluation results."""

    def __init__(self, results: list[EvalResult], min_score: float = 0.85) -> None:
        """Aggregate results against a minimum score."""
        self.results = results
        self.min_score = min_score

    @property
    def total(self) -> int:
        """Number of examples."""
        return len(self.results)

    @property
    def correct_answers(self) -> int:
        """Number of answers that contained the expected substring."""
        return sum(1 for r in self.results if r.answer_ok)

    @property
    def answer_accuracy(self) -> float:
        """Fraction of correct answers."""
        return self.correct_answers / self.total if self.total else 0.0

    @property
    def overall_recall(self) -> float:
        """Micro-averaged recall over all expected documents."""
        total_hits = 0
        total_possible = 0
        for r in self.results:
            expected = set(r.expected_docs)
            retrieved = set(r.retrieved_sources)
            total_hits += len(expected & retrieved)
            total_possible += len(expected)
        return total_hits / total_possible if total_possible else 0.0

    @property
    def passed(self) -> bool:
        """True if both accuracy and recall meet the minimum score."""
        return self.answer_accuracy >= self.min_score and self.overall_recall >= self.min_score

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict including per-example results."""
        return {
            "total": self.total,
            "correct_answers": self.correct_answers,
            "answer_accuracy": round(self.answer_accuracy, 3),
            "overall_recall": round(self.overall_recall, 3),
            "min_score": self.min_score,
            "passed": self.passed,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, path: str) -> None:
        """Write the summary as JSON (the format check_eval_threshold.py reads)."""
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def print_report(self) -> None:
        """Print a human-readable summary to stdout."""
        print(f"\n{'=' * 60}")
        print("  Eval Summary")
        print(f"{'=' * 60}")
        print(f"  Total examples:       {self.total}")
        print(f"  Answer accuracy:      {self.answer_accuracy:.3f}")
        print(f"  Overall recall:       {self.overall_recall:.3f}")
        print(f"  Min score threshold:  {self.min_score}")
        print(f"  Gate passed:          {'yes' if self.passed else 'NO'}")
        print(f"{'=' * 60}\n")
        for i, r in enumerate(self.results):
            status = "✓" if r.answer_ok else "✗"
            print(f"  {i + 1:2d}. {status} recall={r.recall:.2f} | {r.question[:60]}")

    def check_gate(self) -> None:
        """Raise ThresholdGateError if the score is below the minimum."""
        if not self.passed:
            if self.answer_accuracy < self.min_score:
                raise ThresholdGateError(self.answer_accuracy, self.min_score, "answer_accuracy")
            raise ThresholdGateError(self.overall_recall, self.min_score, "overall_recall")


def score_example(
    example: EvalExample,
    answer: str,
    retrieved_sources: list[str],
    latency_s: float = 0.0,
    rubric_score: float | None = None,
    error: str | None = None,
) -> EvalResult:
    """Score one pipeline output against its golden example.

    Recall is the fraction of the example's expected documents found in
    ``retrieved_sources``. The answer is correct when it contains
    ``expected_answer_contains`` (case-insensitive).
    """
    expected = set(example.expected_docs)
    hits = len(expected & set(retrieved_sources))
    recall = hits / len(expected) if expected else 0.0
    answer_ok = example.expected_answer_contains.lower() in answer.lower()
    return EvalResult(
        question=example.question,
        expected_docs=example.expected_docs,
        retrieved_sources=retrieved_sources,
        answer=answer,
        expected_answer_contains=example.expected_answer_contains,
        recall=recall,
        answer_ok=answer_ok,
        rubric_score=rubric_score,
        latency_s=latency_s,
        error=error,
    )
