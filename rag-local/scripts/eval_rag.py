"""Evaluate the RAG pipeline on the 20 golden questions.

Two modes:
  --retrieval-only  Ingest docs/ into a temporary Chroma index with the real
                    embedding model and measure recall@k. No LLM needed; this
                    is what CI gates on.
  (default)         Full pipeline against an existing index and a running
                    Ollama: recall@k plus answer accuracy (expected substring).

Usage:
    python scripts/eval_rag.py --retrieval-only --min-score 0.85
    python scripts/eval_rag.py --data-dir ./data/vectorstore --min-score 0.85
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from rag_local.config import Settings
from rag_local.errors import NoRelevantDocumentsError
from rag_local.loader import load_documents
from rag_local.logging import configure_logging, get_logger
from rag_local.pipeline import RagPipeline

log = get_logger("eval")

ROOT = Path(__file__).resolve().parent.parent


def _load_questions() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("eval_questions", ROOT / "tests" / "fixtures" / "eval_questions.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    questions: list[dict[str, Any]] = module.EVAL_QUESTIONS
    return questions


def main(argv: list[str] | None = None) -> int:
    """Run the eval; return 1 if recall (and, in full mode, answer accuracy) is below --min-score."""
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline recall@k and answer quality")
    parser.add_argument("--data-dir", default=None, help="Vector store persist directory (full mode)")
    parser.add_argument("--retrieval-only", action="store_true", help="Index docs/ in a temp dir; skip the LLM")
    parser.add_argument("--top-k", type=int, default=5, help="Chunks retrieved per question")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum acceptable score for the gate")
    parser.add_argument("--json-report", default="eval-report.json", help="Output JSON report path")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON to stdout")
    args = parser.parse_args(argv)

    settings = Settings()
    min_score = args.min_score if args.min_score is not None else settings.eval_min_score

    tmp: tempfile.TemporaryDirectory[str] | None = None
    if args.retrieval_only:
        tmp = tempfile.TemporaryDirectory()
        settings.chroma_persist_dir = tmp.name
    elif args.data_dir:
        settings.chroma_persist_dir = args.data_dir

    pipeline = RagPipeline(settings)
    if args.retrieval_only:
        pipeline.ingest(load_documents(str(ROOT / "docs")))

    questions = _load_questions()
    results: list[dict[str, Any]] = []
    hits_total = expected_total = correct_answers = 0

    for item in questions:
        start = time.monotonic()
        answer = ""
        try:
            if args.retrieval_only:
                chunks = pipeline.retrieve(item["question"], top_k=args.top_k)
            else:
                result = pipeline.query(item["question"], top_k=args.top_k)
                chunks, answer = result.citations, result.answer
        except NoRelevantDocumentsError:
            chunks = []
        except Exception as exc:
            log.error("eval.question_failed", question=item["question"], error=str(exc))
            chunks = []

        retrieved = [str(c.metadata.get("filename", "")) for c in chunks]
        expected = set(item["expected_docs"])
        hits = len(expected & set(retrieved))
        hits_total += hits
        expected_total += len(expected)
        answer_ok = None if args.retrieval_only else item["expected_answer_contains"].lower() in answer.lower()
        correct_answers += bool(answer_ok)

        results.append(
            {
                "question": item["question"],
                "expected_docs": item["expected_docs"],
                "retrieved_sources": retrieved,
                "recall": round(hits / len(expected), 3) if expected else 0.0,
                "top_score": round(chunks[0].score, 3) if chunks else 0.0,
                "answer_ok": answer_ok,
                "latency_s": round(time.monotonic() - start, 2),
            }
        )

    overall_recall = hits_total / expected_total if expected_total else 0.0
    answer_accuracy = None if args.retrieval_only else correct_answers / len(questions)
    passed = overall_recall >= min_score and (answer_accuracy is None or answer_accuracy >= min_score)

    report = {
        "mode": "retrieval-only" if args.retrieval_only else "full",
        "top_k": args.top_k,
        "total_questions": len(questions),
        "overall_recall": round(overall_recall, 3),
        "answer_accuracy": None if answer_accuracy is None else round(answer_accuracy, 3),
        "min_score": min_score,
        "passed": passed,
        "results": results,
    }
    Path(args.json_report).write_text(json.dumps(report, indent=2))
    if tmp is not None:
        tmp.cleanup()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'=' * 60}\n  RAG Evaluation Report ({report['mode']}, k={args.top_k})\n{'=' * 60}")
        print(f"  Questions:         {len(questions)}")
        print(f"  Overall recall@k:  {overall_recall:.3f}")
        if answer_accuracy is not None:
            print(f"  Answer accuracy:   {answer_accuracy:.3f}")
        print(f"  Min score gate:    {min_score}  ->  {'passed' if passed else 'FAILED'}\n{'=' * 60}\n")
        for r in results:
            print(f"  recall={r['recall']:.2f} top={r['top_score']:.2f}  {r['question'][:60]}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
