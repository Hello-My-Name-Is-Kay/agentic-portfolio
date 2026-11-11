"""Ollama (local) provider (generate API)."""

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


class OllamaProvider:
    """Provider wrapper for local Ollama models. Cost is reported as 0."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout_s: float = 60.0,
        max_retries: int = 2,
        retry_wait_s: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure the provider.

        Args:
            base_url: Ollama server URL.
            model: Local model name.
            timeout_s: Per-request timeout in seconds.
            max_retries: Retries after the first attempt for transient errors (timeouts, 429, 5xx, connection).
            retry_wait_s: Backoff multiplier in seconds (exponential, capped at 4s).
            transport: Optional httpx transport (tests use a mock transport).
        """
        self.name = "ollama"
        self.model = model
        self.timeout_s = timeout_s
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_wait_s = retry_wait_s
        self._transport = transport

        log.info("provider.configured", name=self.name, model=model, base_url=self._base_url, timeout_s=timeout_s)

    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Generate a response using an Ollama local model.

        Raises:
            ProviderTimeoutError: If every attempt timed out.
            RetryableProviderError: If Ollama stayed unreachable or kept returning 5xx.
            ProviderError: For empty prompts or other errors.
        """
        if not prompt or not prompt.strip():
            raise ProviderError("Cannot generate with empty prompt")

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024},
        }

        log.info("llm.call.start", provider=self.name, model=self.model, request_id=request_id, prompt_len=len(prompt))
        start = time.monotonic()

        data = await with_retries(
            lambda: post_json(
                provider=self.name,
                url=f"{self._base_url}/api/generate",
                payload=payload,
                timeout_s=self.timeout_s,
                transport=self._transport,
                request_id=request_id,
            ),
            max_retries=self._max_retries,
            wait_s=self._retry_wait_s,
        )

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        text = str(data.get("response", ""))
        # Ollama does not always return token counts; fall back to a ~4 chars/token estimate.
        tokens_in = int(data.get("prompt_eval_count", len(prompt) // 4))
        tokens_out = int(data.get("eval_count", len(text) // 4))

        log.info(
            "llm.call.ok",
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
            request_id=request_id,
        )

        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
        )
