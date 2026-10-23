"""LLM response data model and provider protocol.

Defines the Provider Protocol that all provider implementations must satisfy,
and the LLMResponse data class for structured results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    text: str
    provider: str
    model: str
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: bool = False

    def __post_init__(self) -> None:
        self.cost_usd = round(self.cost_usd, 6)

    def __repr__(self) -> str:
        return (
            f"LLMResponse(provider={self.provider}, model={self.model}, "
            f"latency={self.latency_ms:.0f}ms, tokens={self.tokens_in}→{self.tokens_out}, "
            f"cost=${self.cost_usd:.6f})"
        )


class Provider(Protocol):
    """Protocol that every LLM provider must implement."""

    name: str
    model: str
    timeout_s: float

    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Send a prompt to the provider's model and return the response.

        Args:
            prompt: The input prompt for the model.
            request_id: Optional correlation ID for tracing.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            TimeoutError: If the call exceeds the configured timeout.
            ProviderError: For other provider-specific failures.
        """
        ...