"""Typed exception hierarchy for the LLM router."""

from __future__ import annotations


class RouterError(Exception):
    """Base for all router errors."""


class ConfigError(RouterError):
    """Invalid or missing configuration."""


class ProviderError(RouterError):
    """A provider call failed in a way that retrying will not fix (bad key, bad request)."""


class RetryableProviderError(ProviderError):
    """A transient provider failure: timeout, connection error, HTTP 429 or 5xx."""


class ProviderTimeoutError(RetryableProviderError):
    """Provider call exceeded its timeout."""


class AllProvidersFailedError(RouterError):
    """Every provider in the fallback chain failed."""

    def __init__(self, errors: list[str]) -> None:
        """Keep one error message per provider."""
        self.errors = errors
        super().__init__(f"All providers failed: {'; '.join(errors)}")


class BudgetExceededError(RouterError):
    """Token or cost budget has been exceeded."""

    def __init__(self, metric: str, limit: float, current: float) -> None:
        """Record which limit was hit."""
        self.metric = metric
        self.limit = limit
        self.current = current
        super().__init__(f"Budget exceeded: {metric}={current:.2f} > limit={limit:.2f}")


class CacheError(RouterError):
    """Response cache operation failed."""


class ValidationError(RouterError):
    """Input validation failure."""
