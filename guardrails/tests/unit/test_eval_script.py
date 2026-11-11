"""Tests for scripts/eval_guardrails.py (the CI gate)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_guardrails.py"


def _main(argv: list[str]) -> int:
    spec = importlib.util.spec_from_file_location("eval_guardrails", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result: int = module.main(argv)
    return result


def test_gate_passes_on_checked_in_dataset(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    assert _main(["--report", str(report), "--min-pass-rate", "0.8"]) == 0
    assert json.loads(report.read_text())["pass_rate"] == 1.0


def test_gate_fails_below_threshold(tmp_path: Path) -> None:
    dataset = tmp_path / "attacks.jsonl"
    dataset.write_text(
        json.dumps(
            {"id": 1, "category": "prompt_injection", "input": "hello", "expected_guardrail": "injection_detected"}
        )
        + "\n"
    )
    assert _main(["--dataset", str(dataset), "--report", str(tmp_path / "r.json"), "--json"]) == 1
