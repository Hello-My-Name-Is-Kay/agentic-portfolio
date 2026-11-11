"""LLM generation via Ollama's chat API.

Retries transient failures (timeouts, connection errors, 5xx), applies a
timeout, and logs latency and token counts for every call.
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from rag_local.config import Settings
from rag_local.errors import GenerationError
from rag_local.logging import get_logger

log = get_logger(__name__)


class TransientGenerationError(GenerationError):
    """A failure worth retrying: timeout, connection error, or HTTP 5xx."""


class LLMResponse:
    """Structured response from an LLM call."""

    def __init__(self, text: str, model: str, latency_ms: float, tokens_in: int, tokens_out: int) -> None:
        """Store the reply text and call metadata."""
        self.text = text
        self.model = model
        self.latency_ms = latency_ms
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out

    @property
    def cost_usd(self) -> float:
        """Cost of a local model call (always 0, tracked for parity with hosted providers)."""
        return 0.0

    def __repr__(self) -> str:
        """Return a short summary."""
        return f"LLMResponse(model={self.model}, latency={self.latency_ms:.0f}ms, tokens_out={self.tokens_out})"


class LLMGenerator(Protocol):
    """Protocol for LLM text generators."""

    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        """Generate a reply to ``prompt``."""
        ...


class OllamaGenerator:
    """Generates text using a model hosted on a local Ollama instance."""

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        """Read model, URL, timeout and sampling options from settings.

        Args:
            settings: Application settings (defaults to environment/.env).
            transport: Optional httpx transport (tests use a mock transport).
        """
        config = settings or Settings()
        self._base_url = config.ollama_base_url.rstrip("/")
        self._model = config.ollama_model
        self._timeout_s = config.llm_timeout_s
        self._max_new_tokens = config.max_new_tokens
        self._temperature = config.temperature
        self._transport = transport

        log.info("generator.configured", model=self._model, base_url=self._base_url, timeout_s=self._timeout_s)

    @retry(
        retry=retry_if_exception_type(TransientGenerationError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        """Generate text using the Ollama model (up to 3 attempts for transient errors).

        Raises:
            TransientGenerationError: Timeout, connection error or 5xx on every attempt.
            GenerationError: Empty prompt, other HTTP errors, or an unexpected response body.
        """
        if not prompt or not prompt.strip():
            raise GenerationError("Cannot generate with empty prompt")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "options": {"num_predict": self._max_new_tokens, "temperature": self._temperature},
            "stream": False,
        }

        log.info("llm.call.start", model=self._model, prompt_len=len(prompt))
        start = time.monotonic()

        try:
            with httpx.Client(transport=self._transport, timeout=httpx.Timeout(self._timeout_s)) as client:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            log.warning("llm.call.http_error", status_code=status, body=exc.response.text[:500])
            error_cls = TransientGenerationError if status >= 500 else GenerationError
            raise error_cls(f"Ollama returned HTTP {status}: {exc.response.text[:200]}") from exc
        except httpx.TimeoutException as exc:
            log.warning("llm.call.timeout", timeout_s=self._timeout_s)
            raise TransientGenerationError(f"Ollama timed out after {self._timeout_s}s") from exc
        except httpx.RequestError as exc:
            log.warning("llm.call.request_error", error=str(exc))
            raise TransientGenerationError(f"Ollama unreachable at {self._base_url}: {exc}") from exc

        latency_ms = round((time.monotonic() - start) * 1000, 1)

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise GenerationError(f"Ollama returned non-JSON response: {response.text[:200]}") from exc

        if not isinstance(data, dict) or "content" not in (data.get("message") or {}):
            raise GenerationError(f"Unexpected Ollama response format: {json.dumps(data)[:300]}")

        text = str(data["message"]["content"]).strip()
        # Ollama usually reports token counts; fall back to ~4 characters per token.
        tokens_in = int(data.get("prompt_eval_count", len(prompt) // 4))
        tokens_out = int(data.get("eval_count", len(text) // 4))

        log.info("llm.call.ok", model=self._model, latency_ms=latency_ms, tokens_in=tokens_in, tokens_out=tokens_out)

        return LLMResponse(
            text=text,
            model=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
