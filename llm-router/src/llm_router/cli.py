"""CLI entry point for the LLM router.

Usage:
  python -m llm_router.cli "Hello, world!" --json
  python -m llm_router.cli --help

The fallback chain is built from ROUTER_* settings: Anthropic and OpenAI are
added when their API keys are set, and the local Ollama provider is always last.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any

from llm_router.config import RouterSettings
from llm_router.logging import configure_logging, get_logger
from llm_router.providers import AnthropicProvider, OllamaProvider, OpenAIProvider
from llm_router.router import Router

if TYPE_CHECKING:
    from llm_router.models import Provider

log = get_logger("router.cli")


def build_providers(settings: RouterSettings, timeout_s: float | None = None) -> list[Provider]:
    """Build the fallback chain from settings: Anthropic, OpenAI (if keys are set), then Ollama."""
    providers: list[Provider] = []
    if settings.anthropic_api_key:
        providers.append(
            AnthropicProvider(
                api_key=settings.anthropic_api_key,
                timeout_s=timeout_s or settings.anthropic_timeout_s,
                max_retries=settings.max_retries,
            )
        )
    if settings.openai_api_key:
        providers.append(
            OpenAIProvider(
                api_key=settings.openai_api_key,
                timeout_s=timeout_s or settings.openai_timeout_s,
                max_retries=settings.max_retries,
            )
        )
    providers.append(
        OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_s=timeout_s or settings.ollama_timeout_s,
            max_retries=settings.max_retries,
        )
    )
    return providers


def main(argv: list[str] | None = None) -> int:
    """Run the router against a prompt."""
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(description="LLM Router — multi-provider fallback chain")
    parser.add_argument("prompt", nargs="?", help="Prompt to send to the LLM providers")
    parser.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    parser.add_argument("--timeout", type=float, default=None, help="Per-provider timeout in seconds")
    args = parser.parse_args(argv)

    if not args.prompt:
        parser.print_help()
        return 1

    settings = RouterSettings()
    router = Router(providers=build_providers(settings, args.timeout), settings=settings)

    async def _run() -> dict[str, Any]:
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
            log.warning("cli.generate_failed", error=str(exc))
            return {"status": "error", "error": str(exc)}

    result = asyncio.run(_run())

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["status"] == "ok":
            print(f"\n[{result['provider']}/{result['model']}]")
            print(f"\n{result['text']}\n")
            print(
                f"[latency: {result['latency_ms']:.0f}ms | "
                f"tokens: {result['tokens_in']}→{result['tokens_out']} | "
                f"cost: ${result['cost_usd']:.6f}]"
            )
            if result.get("cached"):
                print("[cached]")
        else:
            print(f"Error: {result.get('error', 'Unknown')}")
        print()

    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
