"""Ollama (local) provider implementation.

Calls a local Ollama instance for LLM generation with retry logic,
timeout, and structured logging.
"""

from __future__ import annotations

from llm_router.logging import get_logger
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from llm_router.errors import ProviderError, TimeoutError
from llm_router.models import LLMResponse

log = get_logger(__name__)


class OllamaProvider:
    """Provider wrapper for local Ollama models."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout_s: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.name = "ollama"
        self.model = model
        self.timeout_s = timeout_s
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries

        log.info("provider.configured", name=self.name, model=model,
                 self.name, model, self._base_url, timeout_s)

    @retry(
        retry=retry_if_exception_type((TimeoutError, httpx.TimeoutException, httpx.TransportError, httpx.RemoteProtocolError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    async def generate(self, prompt: str, request_id: str | None = None) -> LLMResponse:
        """Generate a response using an Ollama local model.

        Args:
            prompt: The input prompt.
            request_id: Optional correlation ID.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            TimeoutError: If the local call times out.
            ProviderError: If Ollama returns an error or is unavailable.
        """
        if not prompt or not prompt.strip():
            raise ProviderError("Cannot generate with empty prompt")

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1024,
            },
        }

        url = f"{self._base_url}/api/generate"

        log.info("llm.call.start", provider=self.name, model=self.model, request_id=request_id, prompt_len=len(prompt))
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s)) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            log.warning("llm.call.timeout", provider=self.name, timeout_s=self.timeout_s, request_id=request_id)
            raise TimeoutError(f"Ollama timeout after {self.timeout_s}s") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:500]
            log.error("llm.call.http_error", provider=self.name, status_code=status, request_id=request_id)
            raise ProviderError(f"Ollama HTTP {status}: {body}") from exc
        except httpx.RequestError as exc:
            log.warning("llm.call.connection_error", provider=self.name, request_id=request_id, error=str(exc))
            raise ProviderError(f"Ollama unavailable at {self._base_url}: {exc}") from exc

        elapsed = time.monotonic() - start
        latency_ms = round(elapsed * 1000, 1)

        text = data.get("response", "")

        # Ollama doesn't always return token counts; estimate
        tokens_in = data.get("prompt_eval_count", len(prompt) // 4)
        tokens_out = data.get("eval_count", len(text) // 4)

        # Local model: essentially free
        cost_usd = 0.0

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
            cost_usd=cost_usd,
        )