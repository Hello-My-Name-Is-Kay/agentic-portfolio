"""Unit tests for the eval harness modules."""

from __future__ import annotations

from eval_harness.dataset import load_dataset, EvalExample
from eval_harness.scorer import EvalResult, EvalSummary
from eval_harness.errors import DatasetError


class TestDataset:
    """Tests for dataset loading."""

    def test_load_empty_file_raises(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        import logging
        try:
            load_dataset(str(f))
            assert False, "Should have raised"
        except DatasetError:
            pass

    def test_load_missing_file_raises(self) -> None:
        try:
            load_dataset("/nonexistent/file.jsonl")
            assert False
        except DatasetError:
            pass

    def test_single_example_roundtrip(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        ex = EvalExample(
            question="Test question?",
            expected_answer_contains="test",
            expected_docs=["test.md"],
            rubric={"criteria": ["test"]},
        )
        from eval_harness.dataset import dump_dataset
        p = tmp_path / "test.jsonl"
        dump_dataset([ex], str(p))
        loaded = load_dataset(str(p))
        assert len(loaded) == 1
        assert loaded[0].question == "Test question?"


class TestEvalSummary:
    """Tests for the eval summary logic."""

    def test_summary_with_results(self) -> None:
        results = [
            EvalResult("q1", ["a.md"], ["a.md"], "yes", "yes", 1.0, True),
            EvalResult("q2", ["b.md"], ["b.md"], "no", "yes", 1.0, False),
            EvalResult("q3", ["c.md"], ["other.md"], "yes", "yes", 0.0, True),
        ]
        summary = EvalSummary(results, min_score=0.5)
        assert summary.total == 3
        assert summary.correct_answers == 2
        assert summary.answer_accuracy == 2 / 3
        # recall: 3 expected docs, 2 hits (a.md, b.md)
        assert summary.overall_recall == 2 / 3

    def test_gate_fails_when_below_threshold(self) -> None:
        results = [
            EvalResult("q1", ["a.md"], ["a.md"], "wrong", "right", 1.0, False),
        ]
        summary = EvalSummary(results, min_score=0.85)
        assert not summary.passed