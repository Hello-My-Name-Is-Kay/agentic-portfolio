#!/usr/bin/env python3
"""Check an eval report written by EvalSummary.to_json and fail if below the minimum score.

Usage:
    python scripts/check_eval_threshold.py eval-report.json --min-score 0.85
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Return 0 if both answer accuracy and recall meet the minimum score, else 1."""
    parser = argparse.ArgumentParser(description="Check eval threshold from JSON report")
    parser.add_argument("report", help="Path to eval JSON report (EvalSummary.to_json output)")
    parser.add_argument("--min-score", type=float, default=0.85, help="Minimum acceptable score")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.exists():
        if args.json:
            print(json.dumps({"status": "error", "reason": f"Report not found: {args.report}"}))
        else:
            print(f"Report not found: {args.report}", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text())
    answer_accuracy = float(report.get("answer_accuracy", 0.0))
    overall_recall = float(report.get("overall_recall", 0.0))
    passed = answer_accuracy >= args.min_score and overall_recall >= args.min_score

    if args.json:
        print(
            json.dumps(
                {
                    "answer_accuracy": answer_accuracy,
                    "overall_recall": overall_recall,
                    "min_score": args.min_score,
                    "passed": passed,
                },
                indent=2,
            )
        )
    else:
        print("\n  Eval Gate Check")
        print(f"  Answer accuracy: {answer_accuracy:.3f}  (threshold: {args.min_score})")
        print(f"  Overall recall:  {overall_recall:.3f}  (threshold: {args.min_score})")
        print(f"  Gate passed:     {'yes' if passed else 'NO'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
