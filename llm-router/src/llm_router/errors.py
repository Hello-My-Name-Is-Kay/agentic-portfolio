"""Typed exception hierarchy for the LLM router."""

from __future__ import annotations


class RouterError(Exception):
    """Base for all router errors."""


class ConfigError(RouterError):
    """Invalid or missing configuration."""


class ProviderError(RouterError):
    """Base for provider call failures."""


class TimeoutError(ProviderError):
    """Provider call exceeded timeout."""


class RetryBudgetExhausted(ProviderError):
    """Provider failed after all retry attempts."""


class AllProvidersFailed(RouterError):
    """Every provider in the fallback chain failed."""
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"All providers failed: {'; '.join(errors)}")


class BudgetExceeded(RouterError):
    """Token or cost budget has been exceeded."""
    def __init__(self, metric: str, limit: float, current: float) -> None:
        self.metric = metric
        self.limit = limit
        self.current = current
        super().__init__(f"Budget exceeded: {metric}={current:.2f} > limit={limit:.2f}")


class CacheError(RouterError):
    """Response cache operation failed."""


class ValidationError(RouterError):
    """Input validation failure."""