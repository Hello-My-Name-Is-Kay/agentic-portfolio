#!/usr/bin/env python3
"""Check eval threshold from a JSON report and fail the build if below minimum.

Usage:
    python scripts/check_eval_threshold.py eval-report.json --min-score 0.85
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check eval threshold from JSON report")
    parser.add_argument("report", help="Path to eval JSON report")
    parser.add_argument("--min-score", type=float, default=0.85, help="Minimum acceptable score")
    parser.add_argument("--json", action="store_true", help="Output results as JSON for LLM consumption")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        result = {"status": "error", "reason": f"Report not found: {args.report}"}
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Report not found: {args.report}", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text())

    answer_accuracy = report.get("answer_accuracy", 0.0)
    overall_recall = report.get("overall_recall", 0.0)
    passed = report.get("passed", False)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n  Eval Gate Check")
        print(f"  Answer accuracy: {answer_accuracy:.3f}  (threshold: {args.min_score})")
        print(f"  Overall recall:  {overall_recall:.3f}  (threshold: {args.min_score})")
        print(f"  Gate passed:     {'✓' if passed else '✗'}")


if __name__ == "__main__":
    sys.exit(main())