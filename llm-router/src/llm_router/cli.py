"""CLI entry point for the LLM router.

Usage:
  python -m llm_router.cli "Hello, world!" --json
  python -m llm_router.cli --help
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from llm_router.logging import configure_logging, get_logger
from llm_router.router import Router

log = get_logger("router.cli")


def main(argv: list[str] | None = None) -> int:
    """Run the router against a prompt."""
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(description="LLM Router — multi-provider fallback chain")
    parser.add_argument("prompt", nargs="?", help="Prompt to send to the LLM providers")
    parser.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-provider timeout in seconds")
    args = parser.parse_args(argv)

    if not args.prompt:
        parser.print_help()
        return 1

    async def _run() -> dict:
        from llm_router.providers import OllamaProvider
        router = Router(providers=[
            OllamaProvider(timeout_s=args.timeout),
        ])
        try:
            resp = await router.generate(args.prompt, request_id="cli-demo")
            return {
                "status": "ok",
                "provider": resp.provider,
                "model": resp.model,
                "text": resp.text,
                "latency_ms": resp.latency_ms,
                "tokens_in": resp.tokens_in,
                "tokens_out": resp.tokens_out,
                "cost_usd": round(resp.cost_usd, 6),
                "cached": resp.cached,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
            }

    result = asyncio.run(_run())

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["status"] == "ok":
            print(f"\n[{result['provider']}/{result['model']}]")
            print(f"\n{result['text']}\n")
            print(f"[latency: {result['latency_ms']:.0f}ms | "
                  f"tokens: {result['tokens_in']}→{result['tokens_out']} | "
                  f"cost: ${result['cost_usd']:.6f}]")
            if result.get("cached"):
                print("[cached]")
        else:
            print(f"Error: {result.get('error', 'Unknown')}")
        print()

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())