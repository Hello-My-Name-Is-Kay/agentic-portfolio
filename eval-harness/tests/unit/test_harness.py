"""Unit tests for dataset loading and scoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from eval_harness.dataset import EvalExample, dump_dataset, load_dataset
from eval_harness.errors import DatasetError, ThresholdGateError
from eval_harness.scorer import EvalResult, EvalSummary, score_example

if TYPE_CHECKING:
    from pathlib import Path


class TestDataset:
    def test_load_empty_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        with pytest.raises(DatasetError, match="No valid examples"):
            load_dataset(str(f))

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(DatasetError, match="not found"):
            load_dataset("/nonexistent/file.jsonl")

    def test_load_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="not a file"):
            load_dataset(str(tmp_path))

    def test_only_malformed_lines_reports_parse_errors(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.jsonl"
        f.write_text('not json\n{"question": "missing fields"}\n')
        with pytest.raises(DatasetError, match="2 parse errors"):
            load_dataset(str(f))

    def test_skips_comments_blanks_and_bad_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.jsonl"
        f.write_text('# comment\n\nnot json\n{"question": "q", "expected_answer_contains": "a"}\n')
        loaded = load_dataset(str(f))
        assert [ex.question for ex in loaded] == ["q"]

    def test_single_example_roundtrip(self, tmp_path: Path) -> None:
        ex = EvalExample(
            question="Test question?",
            expected_answer_contains="test",
            expected_docs=["test.md"],
            rubric={"criteria": ["test"]},
        )
        p = tmp_path / "sub" / "test.jsonl"
        dump_dataset([ex], str(p))
        assert load_dataset(str(p)) == [ex]


class TestScoreExample:
    example = EvalExample(question="q", expected_answer_contains="21", expected_docs=["a.md", "b.md"])

    def test_partial_recall_and_case_insensitive_match(self) -> None:
        result = score_example(self.example, "The minimum age is 21.", ["a.md", "x.md"], latency_s=0.5)
        assert result.recall == 0.5
        assert result.answer_ok is True
        assert result.latency_s == 0.5

    def test_wrong_answer(self) -> None:
        result = score_example(self.example, "I don't know", [])
        assert result.recall == 0.0
        assert result.answer_ok is False

    def test_no_expected_docs_gives_zero_recall(self) -> None:
        ex = EvalExample(question="q", expected_answer_contains="x")
        assert score_example(ex, "x", ["a.md"]).recall == 0.0


class TestEvalSummary:
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
        assert summary.overall_recall == 2 / 3
        assert summary.passed

    def test_gate_fails_on_accuracy(self) -> None:
        summary = EvalSummary([EvalResult("q1", ["a.md"], ["a.md"], "wrong", "right", 1.0, False)], min_score=0.85)
        assert not summary.passed
        with pytest.raises(ThresholdGateError) as info:
            summary.check_gate()
        assert info.value.metric == "answer_accuracy"

    def test_gate_fails_on_recall(self) -> None:
        summary = EvalSummary([EvalResult("q1", ["a.md"], [], "right", "right", 0.0, True)], min_score=0.85)
        with pytest.raises(ThresholdGateError, match="overall_recall=0.000"):
            summary.check_gate()

    def test_gate_passes_silently(self) -> None:
        EvalSummary([EvalResult("q", ["a.md"], ["a.md"], "x", "x", 1.0, True)]).check_gate()

    def test_report_roundtrip(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import json

        result = EvalResult("q", ["a.md"], ["a.md"], "x", "x", 1.0, True, rubric_score=0.91234)
        summary = EvalSummary([result])
        out = tmp_path / "report.json"
        summary.to_json(str(out))
        data = json.loads(out.read_text())
        assert data["passed"] is True
        assert data["results"][0]["rubric_score"] == 0.912
        summary.print_report()
        assert "Gate passed:          yes" in capsys.readouterr().out
