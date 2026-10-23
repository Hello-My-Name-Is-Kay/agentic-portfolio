"""Eval runner: compute recall@k and answer quality.

Usage:
    python scripts/eval_rag.py [--data-dir ./data/vectorstore]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_local.config import Settings
from rag_local.errors import NoRelevantDocuments
from rag_local.logging import configure_logging, get_logger
from rag_local.pipeline import RagPipeline

log = get_logger("eval")


def main() -> int:
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline recall@k and answer quality")
    parser.add_argument("--data-dir", default=None, help="Vector store persist directory")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum acceptable score for CI gate")
    parser.add_argument("--json-report", default="eval-report.json", help="Output JSON report path")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON to stdout (for LLM consumption)")
    args = parser.parse_args()

    settings = Settings()
    if args.data_dir:
        settings.chroma_persist_dir = args.data_dir
    if args.min_score is not None:
        settings.eval_min_score = args.min_score

    pipeline = RagPipeline(settings)

    # Import questions from fixtures
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "fixtures"))
    from eval_questions import EVAL_QUESTIONS

    results = []
    correct_retrievals = 0
    total_retrievals = 0
    correct_answers = 0
    total_questions = len(EVAL_QUESTIONS)

    log.info("Starting eval on %d questions", total_questions)

    for i, item in enumerate(EVAL_QUESTIONS):
        q = item["question"]
        expected_docs = item["expected_docs"]
        expected_contains = item["expected_answer_contains"]

        start = time.monotonic()

        try:
            result = pipeline.query(q, top_k=5)
            retrieved_sources = [c.metadata.get("filename", "") for c in result.citations]
            answer = result.answer
            confidence = result.confidence
        except NoRelevantDocuments:
            retrieved_sources = []
            answer = ""
            confidence = 0.0
        except Exception as exc:
            log.error("Eval error on question %d: %s", i, exc)
            retrieved_sources = []
            answer = ""
            confidence = 0.0

        elapsed = time.monotonic() - start

        # recall@k: fraction of expected_docs found in retrieved_sources
        retrieved_set = set(retrieved_sources)
        expected_set = set(expected_docs)
        hits = len(expected_set & retrieved_set) if expected_set else 0
        recall = hits / len(expected_set) if expected_set else 0.0
        correct_retrievals += hits
        total_retrievals += len(expected_set)

        # Answer check: does the answer contain the expected substring?
        answer_ok = expected_contains.lower() in answer.lower()
        if answer_ok:
            correct_answers += 1

        results.append({
            "question": q,
            "expected_docs": expected_docs,
            "retrieved_sources": retrieved_sources,
            "recall": round(recall, 3),
            "answer_ok": answer_ok,
            "confidence": round(confidence, 3),
            "latency_s": round(elapsed, 2),
        })

    overall_recall = correct_retrievals / total_retrievals if total_retrievals else 0.0
    answer_accuracy = correct_answers / total_questions if total_questions else 0.0

    report = {
        "total_questions": total_questions,
        "overall_recall": round(overall_recall, 3),
        "answer_accuracy": round(answer_accuracy, 3),
        "results": results,
    }

    # Write report
    report_path = Path(args.json_report)
    report_path.write_text(json.dumps(report, indent=2))
    log.info("Eval report written", path=str(report_path))

    if args.json:
        print(json.dumps(report, indent=2))

    # Print summary
    print(f"\n{'='*60}")
    print(f"  RAG Evaluation Report")
    print(f"{'='*60}")
    print(f"  Questions:         {total_questions}")
    print(f"  Overall recall@k:  {overall_recall:.3f}")
    print(f"  Answer accuracy:   {answer_accuracy:.3f}")
    print(f"  Min score gate:    {settings.eval_min_score}")
    print(f"{'='*60}\n")

    for r in results:
        status = "✓" if r["answer_ok"] else "✗"
        print(f"  {status} recall={r['recall']:.2f} conf={r['confidence']:.2f} "
              f"({r['latency_s']:.1f}s) {r['question'][:60]}")

    # Gate check
    if overall_recall < settings.eval_min_score:
        log.error("Eval gate FAILED: recall %0.3f < min score %0.3f", overall_recall, settings.eval_min_score)
        return 1

    log.info("Eval gate PASSED: recall %0.3f >= min score %0.3f", overall_recall, settings.eval_min_score)
    return 0


if __name__ == "__main__":
    sys.exit(main())