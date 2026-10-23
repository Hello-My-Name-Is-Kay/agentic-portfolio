"""Anthropic Claude provider implementation.

Calls the Anthropic Messages API with retry logic, timeout,
and structured logging.
"""

from __future__ import annotations

from llm_router.logging import get_logger
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from llm_router.errors import ProviderError, TimeoutError
from llm_router.models import LLMResponse, Provider

log = get_logger(__name__)


_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider:
    """Provider wrapper for Anthropic's Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5",
        timeout_s: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ProviderError("Anthropic API key is required")

        self.name = "anthropic"
        self.model = model
        self.timeout_s = timeout_s
        self._api_key = api_key
        self._max_retries = max_retries

        log.info("provider.configured", name=self.name, model=model, timeout_s=timeout_s)

    @retry(
        retry=retry_if_exception_type((TimeoutError, httpx.TimeoutException, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Generate a response using Anthropic's API.

        Args:
            prompt: The input prompt.
            request_id: Optional correlation ID.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            TimeoutError: If the API call times out.
            ProviderError: For authentication, rate limiting, or server errors.
        """
        if not prompt or not prompt.strip():
            raise ProviderError("Cannot generate with empty prompt")

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }

        log.info("llm.call.start", provider=self.name, model=self.model, request_id=request_id, prompt_len=len(prompt))
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s)) as client:
                response = await client.post(
                    _ANTHROPIC_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            log.warning("llm.call.timeout", provider=self.name, timeout_s=self.timeout_s, request_id=request_id)
            raise TimeoutError(f"Anthropic timeout after {self.timeout_s}s") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:500]
            log.error("llm.call.http_error", provider=self.name, status_code=status, request_id=request_id)
            if status == 401:
                raise ProviderError("Anthropic authentication failed") from exc
            if status == 429:
                raise ProviderError("Anthropic rate limited") from exc
            raise ProviderError(f"Anthropic HTTP {status}: {body}") from exc
        except httpx.RequestError as exc:
            log.warning("llm.call.connection_error", provider=self.name, request_id=request_id, error=str(exc))
            raise ProviderError(f"Anthropic connection failed: {exc}") from exc

        elapsed = time.monotonic() - start
        latency_ms = round(elapsed * 1000, 1)

        text = ""
        if data.get("content"):
            for block in data["content"]:
                if block.get("type") == "text":
                    text += block.get("text", "")

        tokens_in = data.get("usage", {}).get("input_tokens", 0)
        tokens_out = data.get("usage", {}).get("output_tokens", 0)

        # Rough cost estimate: Claude Sonnet ~$3/M in, ~$15/M out
        cost_per_m_in = 3.0
        cost_per_m_out = 15.0
        cost_usd = (tokens_in / 1_000_000 * cost_per_m_in) + (tokens_out / 1_000_000 * cost_per_m_out)

        log.info(
            "llm.call.ok",
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost_usd, 6),
            request_id=request_id,
        )

        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )