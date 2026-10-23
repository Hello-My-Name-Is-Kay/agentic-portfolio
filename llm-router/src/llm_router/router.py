"""Main LLM Router: fallback chain across multiple providers.

Orchestrates primary → secondary → tertiary provider fallback,
with response caching, budget enforcement, and comprehensive
observability.
"""

from __future__ import annotations

from llm_router.logging import get_logger
import time
from typing import Any

from llm_router.budget import Budget
from llm_router.cache import ResponseCache
from llm_router.config import RouterSettings
from llm_router.errors import AllProvidersFailed, BudgetExceeded, ProviderError
from llm_router.models import LLMResponse, Provider

log = get_logger(__name__)


class Router:
    """Multi-provider LLM router with fallback chain, caching, and budgets.

    Usage:
        router = Router()
        response = await router.generate("Hello", request_id="req-123")
    """

    def __init__(
        self,
        providers: list[Provider] | None = None,
        cache: ResponseCache | None = None,
        budget: Budget | None = None,
        settings: RouterSettings | None = None,
    ) -> None:
        config = settings or RouterSettings()
        self._providers = providers or []
        self._cache = cache or ResponseCache(
            ttl_s=config.cache_ttl_s,
            max_size=config.cache_max_size,
        )
        self._budget = budget or Budget(
            max_tokens_in=config.max_total_tokens_in,
            max_tokens_out=config.max_total_tokens_out,
            max_cost_usd=config.max_cost_usd,
        )

        log.info(
            "Router initialized with %d providers, cache.ttl=%ds, budget.max_cost=%.2f",
            len(self._providers),
            config.cache_ttl_s,
            config.max_cost_usd,
        )

    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Generate a response by trying each provider in order.

        Args:
            prompt: The input prompt.
            request_id: Optional correlation ID for tracing.

        Returns:
            LLMResponse from the first provider that succeeds.

        Raises:
            AllProvidersFailed: If every provider in the chain fails.
            BudgetExceeded: If the budget is exceeded.
        """
        if not prompt or not prompt.strip():
            raise ProviderError("Cannot generate with empty prompt")

        # Check cache first across all providers
        for provider in self._providers:
            cached = self._cache.get(provider.name, provider.model, prompt)
            if cached is not None:
                log.info("llm.cache.hit", provider=provider.name, request_id=request_id)
                return cached

        errors: list[str] = []
        for provider in self._providers:
            try:
                resp = await provider.generate(prompt, request_id=request_id)
            except ProviderError as exc:
                log.warning(
                    "llm.provider.failed",
                    provider=provider.name,
                    error=str(exc),
                    request_id=request_id,
                )
                errors.append(f"{provider.name}: {exc}")
                continue
            except Exception as exc:
                log.exception(
                    "llm.provider.unexpected_error",
                    provider=provider.name,
                    request_id=request_id,
                )
                errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
                continue

            # Success — cache and record budget
            self._cache.set(provider.name, provider.model, prompt, resp)

            try:
                self._budget.record(resp)
            except BudgetExceeded:
                log.error("llm.budget.exceeded", request_id=request_id)
                raise

            return resp

        # All providers failed
        log.error("llm.all_providers_failed", request_id=request_id, errors=errors)
        raise AllProvidersFailed(errors=errors)

    @property
    def providers(self) -> list[Provider]:
        """Return the list of configured providers."""
        return list(self._providers)

    def add_provider(self, provider: Provider) -> None:
        """Add a provider to the end of the fallback chain."""
        self._providers.append(provider)
        log.info("router.provider_added", name=provider.name)