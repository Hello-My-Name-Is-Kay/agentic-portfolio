"""CLI entry points for the RAG pipeline.

Two commands:
  rag ingest   — Load and chunk policy documents into Chroma.
  rag query    — Ask a question against the ingested documents.

Usage:
  python -m rag_local.cli ingest --source docs/
  python -m rag_local.cli query "What is the fuel policy?"
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rag_local.config import Settings
from rag_local.errors import NoRelevantDocuments, RagError
from rag_local.loader import load_documents
from rag_local.logging import configure_logging, get_logger
from rag_local.pipeline import RagPipeline

log = get_logger("rag.cli")


def _add_ingest_parser(subparsers) -> None:
    p = subparsers.add_parser("ingest", help="Load documents into the vector store")
    p.add_argument("--source", "-s", default="./docs", help="Directory containing policy markdown files")
    p.add_argument("--persist-dir", "-p", default=None, help="Vector store persist directory")
    p.add_argument("--json", action="store_true", help="Output in JSON format for LLM consumption")
    p.set_defaults(func=_cmd_ingest)


def _add_query_parser(subparsers) -> None:
    p = subparsers.add_parser("query", help="Ask a question against the policy documents")
    p.add_argument("question", nargs="?", help="Your question (omit for interactive mode)")
    p.add_argument("--top-k", type=int, default=None, help="Number of documents to retrieve")
    p.add_argument("--interactive", "-i", action="store_true", help="Interactive Q&A session")
    p.add_argument("--json", action="store_true", help="Output in JSON format for LLM consumption")
    p.set_defaults(func=_cmd_query)


def _cmd_ingest(args) -> int:
    """Handle the 'ingest' command."""
    import json
    settings = Settings()
    if args.persist_dir:
        settings.chroma_persist_dir = args.persist_dir

    log.info("cli.ingest.start", source=args.source)

    docs = load_documents(args.source)
    log.info("cli.ingest.loaded", count=len(docs))

    pipeline = RagPipeline(settings)
    start = time.monotonic()
    count = pipeline.ingest(docs)
    elapsed = time.monotonic() - start

    log.info("cli.ingest.done", chunks=count, elapsed_s=round(elapsed, 1))

    if args.json:
        print(json.dumps({
            "status": "ok", "action": "ingest",
            "chunks_ingested": count, "documents_loaded": len(docs),
            "persist_dir": settings.chroma_persist_dir,
            "elapsed_s": round(elapsed, 1),
        }, indent=2))
    else:
        print(f"\n✓ Ingested {count} chunks from {len(docs)} documents into {settings.chroma_persist_dir}")
        print(f"  Elapsed: {elapsed:.1f}s")
    return 0


def _cmd_query(args) -> int:
    """Handle the 'query' command."""
    settings = Settings()
    pipeline = RagPipeline(settings)

    if args.interactive or not args.question:
        if args.json:
            # Interactive mode not supported with --json; require a direct question
            print(json.dumps({"status": "error", "reason": "--json requires a direct question, not interactive mode"}))
            return 1
        print("RAG Policy Assistant — Interactive Mode")
        print("Type 'exit', 'quit', or Ctrl+C to stop.\n")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q:
                continue
            if q.lower() in ("exit", "quit"):
                break
            _run_query(pipeline, q, args.top_k, args.json)
        return 0

    return _run_query(pipeline, args.question, args.top_k, args.json)


def _run_query(pipeline: RagPipeline, question: str, top_k: int | None,
               json_output: bool = False) -> int:
    """Run a single query and print the result.

    Args:
        pipeline: The RAG pipeline.
        question: The question to ask.
        top_k: Override number of documents to retrieve.
        json_output: If True, output JSON; otherwise human-readable.

    Returns:
        0 on success, 1 on error.
    """
    import json
    try:
        result = pipeline.query(question, top_k=top_k)
    except NoRelevantDocuments:
        if json_output:
            print(json.dumps({"status": "error", "code": "NO_RELEVANT_DOCS",
                              "reason": "No documents scored above the relevance threshold."}))
        else:
            print("\nI don't know based on the available policies.")
            print("(No documents scored above the relevance threshold.)\n")
        return 0
    except RagError as exc:
        log.error("query.failed", error=str(exc))
        if json_output:
            print(json.dumps({"status": "error", "code": "RAG_ERROR", "reason": str(exc)}))
        else:
            print(f"\nError: {exc}\n")
        return 1
    except Exception as exc:
        log.exception("query.unexpected_error")
        if json_output:
            print(json.dumps({"status": "error", "code": "INTERNAL", "reason": str(exc)}))
        else:
            print(f"\nUnexpected error: {exc}\n")
        return 1

    if json_output:
        print(json.dumps({
            "status": "ok",
            "question": question,
            "answer": result.answer,
            "confidence": result.confidence,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "citations": [
                {
                    "source": c.metadata.get("source", "unknown"),
                    "filename": Path(c.metadata.get("source", "")).name,
                    "score": round(c.score, 3),
                }
                for c in result.citations
            ],
        }, indent=2))
    else:
        print(f"\n{result.answer}\n")
        print(f"[confidence: {result.confidence:.3f} | model: {result.model} | "
              f"latency: {result.latency_ms:.0f}ms | tokens: {result.tokens_in}→{result.tokens_out}]")

        if result.citations:
            print("\nSources:")
            for c in result.citations:
                src = c.metadata.get("source", "unknown")
                print(f"  • score={c.score:.3f} — {Path(src).name}")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(
        description="RAG Policy Assistant — Retrieval-Augmented Generation over rental-policy documents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_ingest_parser(subparsers)
    _add_query_parser(subparsers)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())