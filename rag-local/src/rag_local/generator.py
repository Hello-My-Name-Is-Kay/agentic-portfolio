"""LLM generation via Ollama's HTTP API.

Wraps calls to a locally-hosted Ollama model with retry logic,
timeout, structured logging of latency/tokens, and validation
of the generated output.
"""

from __future__ import annotations

import json
from rag_local.logging import get_logger
from typing import Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from rag_local.config import Settings
from rag_local.errors import GenerationError

log = get_logger(__name__)


class LLMResponse:
    """Structured response from an LLM call."""

    def __init__(self, text: str, model: str, latency_ms: float, tokens_in: int, tokens_out: int) -> None:
        self.text = text
        self.model = model
        self.latency_ms = latency_ms
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out

    @property
    def cost_usd(self) -> float:
        """Estimated cost for a local model (essentially free but tracked)."""
        return 0.0

    def __repr__(self) -> str:
        return f"LLMResponse(model={self.model}, latency={self.latency_ms:.0f}ms, tokens_out={self.tokens_out})"


class LLMGenerator(Protocol):
    """Protocol for LLM text generators."""

    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse: ...


class OllamaGenerator:
    """Generates text using a model hosted on a local Ollama instance."""

    def __init__(self, settings: Settings | None = None) -> None:
        config = settings or Settings()
        self._base_url = config.ollama_base_url.rstrip("/")
        self._model = config.ollama_model
        self._timeout_s = config.llm_timeout_s
        self._max_new_tokens = config.max_new_tokens
        self._temperature = config.temperature

        log.info(
            "Ollama generator configured: model=%s url=%s timeout=%ds",
            self._model,
            self._base_url,
            self._timeout_s,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, httpx.RemoteProtocolError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        """Generate text using the Ollama model.

        Args:
            prompt: The user/instruction prompt.
            system_prompt: Optional system message prepended to the context.

        Returns:
            LLMResponse with generated text and metadata.

        Raises:
            GenerationError: If the model fails or returns invalid output.
        """
        if not prompt or not prompt.strip():
            raise GenerationError("Cannot generate with empty prompt")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_new_tokens,
            "temperature": self._temperature,
            "stream": False,
        }

        url = f"{self._base_url}/api/chat"
        log.info("llm.call.start", model=self._model, prompt_len=len(prompt))

        import time
        start = time.monotonic()

        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=httpx.Timeout(self._timeout_s),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("llm.call.http_error", status_code=exc.response.status_code, body=exc.response.text[:500])
            raise GenerationError(f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except httpx.TimeoutException as exc:
            log.warning("llm.call.timeout", timeout_s=self._timeout_s)
            raise
        except httpx.RequestError as exc:
            log.warning("llm.call.request_error", error=str(exc))
            raise

        elapsed = time.monotonic() - start
        latency_ms = round(elapsed * 1000, 1)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise GenerationError(f"Ollama returned non-JSON response: {response.text[:200]}") from exc

        if "message" not in data or "content" not in data["message"]:
            raise GenerationError(f"Unexpected Ollama response format: {json.dumps(data)[:300]}")

        text = data["message"]["content"].strip()

        # Estimate tokens (rough: 4 chars per token for English)
        tokens_in = data.get("prompt_eval_count", len(prompt) // 4)
        tokens_out = data.get("eval_count", len(text) // 4)

        log.info(
            "llm.call.ok",
            model=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        return LLMResponse(
            text=text,
            model=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )