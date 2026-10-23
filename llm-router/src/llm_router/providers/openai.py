"""OpenAI provider implementation.

Calls the OpenAI Chat Completions API with retry logic, timeout,
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


_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
    """Provider wrapper for OpenAI's models."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_s: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ProviderError("OpenAI API key is required")

        self.name = "openai"
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
        """Generate a response using OpenAI's API.

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
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }

        log.info("llm.call.start", provider=self.name, model=self.model, request_id=request_id, prompt_len=len(prompt))
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s)) as client:
                response = await client.post(
                    _OPENAI_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            log.warning("llm.call.timeout", provider=self.name, timeout_s=self.timeout_s, request_id=request_id)
            raise TimeoutError(f"OpenAI timeout after {self.timeout_s}s") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:500]
            log.error("llm.call.http_error", provider=self.name, status_code=status, request_id=request_id)
            if status == 401:
                raise ProviderError("OpenAI authentication failed") from exc
            if status == 429:
                raise ProviderError("OpenAI rate limited") from exc
            raise ProviderError(f"OpenAI HTTP {status}: {body}") from exc
        except httpx.RequestError as exc:
            log.warning("llm.call.connection_error", provider=self.name, request_id=request_id, error=str(exc))
            raise ProviderError(f"OpenAI connection failed: {exc}") from exc

        elapsed = time.monotonic() - start
        latency_ms = round(elapsed * 1000, 1)

        choice = data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        # Rough cost: GPT-4o-mini ~$0.15/M in, $0.60/M out
        cost_per_m_in = 0.15
        cost_per_m_out = 0.60
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