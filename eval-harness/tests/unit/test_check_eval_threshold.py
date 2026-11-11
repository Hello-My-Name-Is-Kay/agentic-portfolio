"""Tests for scripts/check_eval_threshold.py (the CI gate)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_eval_threshold.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_eval_threshold", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(tmp_path: Path, accuracy: float, recall: float) -> str:
    path = tmp_path / "eval-report.json"
    path.write_text(json.dumps({"answer_accuracy": accuracy, "overall_recall": recall}))
    return str(path)


def test_passes_above_threshold(tmp_path: Path) -> None:
    assert _load().main([_report(tmp_path, 0.9, 0.9), "--min-score", "0.85"]) == 0


@pytest.mark.parametrize(("accuracy", "recall"), [(0.5, 0.9), (0.9, 0.5)])
def test_fails_below_threshold(tmp_path: Path, accuracy: float, recall: float) -> None:
    assert _load().main([_report(tmp_path, accuracy, recall), "--min-score", "0.85"]) == 1


def test_missing_report_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _load().main([str(tmp_path / "nope.json"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _load().main([_report(tmp_path, 1.0, 0.7), "--min-score", "0.8", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
