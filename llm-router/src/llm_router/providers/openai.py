"""OpenAI provider (Chat Completions API)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from llm_router.errors import ProviderError
from llm_router.logging import get_logger
from llm_router.models import LLMResponse
from llm_router.providers._http import post_json, with_retries

if TYPE_CHECKING:
    import httpx

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
        retry_wait_s: float = 0.5,
        cost_per_m_in: float = 0.15,
        cost_per_m_out: float = 0.60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure the provider.

        Args:
            api_key: OpenAI API key.
            model: Model ID.
            timeout_s: Per-request timeout in seconds.
            max_retries: Retries after the first attempt for transient errors (timeouts, 429, 5xx, connection).
            retry_wait_s: Backoff multiplier in seconds (exponential, capped at 4s).
            cost_per_m_in: USD per million input tokens, used for the cost estimate.
            cost_per_m_out: USD per million output tokens, used for the cost estimate.
            transport: Optional httpx transport (tests use a mock transport).
        """
        if not api_key:
            raise ProviderError("OpenAI API key is required")

        self.name = "openai"
        self.model = model
        self.timeout_s = timeout_s
        self._api_key = api_key
        self._max_retries = max_retries
        self._retry_wait_s = retry_wait_s
        self._cost_per_m_in = cost_per_m_in
        self._cost_per_m_out = cost_per_m_out
        self._transport = transport

        log.info("provider.configured", name=self.name, model=model, timeout_s=timeout_s)

    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Generate a response using OpenAI's API.

        Raises:
            ProviderTimeoutError: If every attempt timed out.
            RetryableProviderError: If transient errors persisted through all retries.
            ProviderError: For empty prompts, authentication or other client errors.
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

        data = await with_retries(
            lambda: post_json(
                provider=self.name,
                url=_OPENAI_URL,
                payload=payload,
                headers=headers,
                timeout_s=self.timeout_s,
                transport=self._transport,
                request_id=request_id,
            ),
            max_retries=self._max_retries,
            wait_s=self._retry_wait_s,
        )

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        choices = data.get("choices") or [{}]
        text = str(choices[0].get("message", {}).get("content") or "")
        usage = data.get("usage", {})
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        cost_usd = tokens_in / 1_000_000 * self._cost_per_m_in + tokens_out / 1_000_000 * self._cost_per_m_out

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
