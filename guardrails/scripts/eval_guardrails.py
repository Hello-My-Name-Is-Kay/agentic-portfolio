"""Run the guardrail evaluation suite and generate a report.

Usage:
    python scripts/eval_guardrails.py [--dataset tests/fixtures/attack_dataset.jsonl]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from guardrails.logging import configure_logging, get_logger
from guardrails.suite import GuardrailSuite

log = get_logger("eval.guardrails")


def main() -> int:
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(description="Run guardrail evaluation suite")
    parser.add_argument("--dataset", default="tests/fixtures/attack_dataset.jsonl", help="Attack dataset path")
    parser.add_argument("--report", default="guardrail-report.json", help="Output report path")
    parser.add_argument("--min-pass-rate", type=float, default=0.8, help="Minimum acceptable pass rate")
    parser.add_argument("--json", action="store_true", help="Emit report to stdout as JSON for LLM consumption")
    args = parser.parse_args()

    import json

    suite = GuardrailSuite()
    results = suite.run_all(dataset_path=args.dataset)
    report = suite.generate_report(output_path=args.report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        suite.print_summary()

    pass_rate = report["pass_rate"]
    if pass_rate < args.min_pass_rate:
        log.error("guardrail.gate_failed", pass_rate=pass_rate, min_pass_rate=args.min_pass_rate)
        return 1

    log.info("guardrail.gate_passed", pass_rate=pass_rate, min_pass_rate=args.min_pass_rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())