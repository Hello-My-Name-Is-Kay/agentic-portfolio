"""Shared HTTP call and retry logic for the providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from llm_router.errors import ProviderError, ProviderTimeoutError, RetryableProviderError
from llm_router.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

log = get_logger(__name__)

T = TypeVar("T")


async def post_json(
    *,
    provider: str,
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
    headers: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """POST a JSON payload and return the decoded JSON object.

    Raises:
        ProviderTimeoutError: The call timed out (retryable).
        RetryableProviderError: Connection error, HTTP 429 or 5xx.
        ProviderError: Any other HTTP error, or a body that is not a JSON object.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), transport=transport) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        log.warning("llm.call.timeout", provider=provider, timeout_s=timeout_s, request_id=request_id)
        raise ProviderTimeoutError(f"{provider} timeout after {timeout_s}s") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:500]
        log.error("llm.call.http_error", provider=provider, status_code=status, request_id=request_id)
        if status == 401:
            raise ProviderError(f"{provider} authentication failed") from exc
        if status == 429:
            raise RetryableProviderError(f"{provider} rate limited") from exc
        if status >= 500:
            raise RetryableProviderError(f"{provider} HTTP {status}: {body}") from exc
        raise ProviderError(f"{provider} HTTP {status}: {body}") from exc
    except httpx.RequestError as exc:
        log.warning("llm.call.connection_error", provider=provider, request_id=request_id, error=str(exc))
        raise RetryableProviderError(f"{provider} connection failed: {exc}") from exc
    except ValueError as exc:
        raise ProviderError(f"{provider} returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise ProviderError(f"{provider} returned an unexpected response body")
    return data


async def with_retries(call: Callable[[], Awaitable[T]], *, max_retries: int, wait_s: float) -> T:
    """Run ``call``, retrying RetryableProviderError up to ``max_retries`` times with exponential backoff."""
    retrying = AsyncRetrying(
        retry=retry_if_exception_type(RetryableProviderError),
        stop=stop_after_attempt(max(0, max_retries) + 1),
        wait=wait_exponential(multiplier=wait_s, max=4),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            return await call()
    raise AssertionError("unreachable: tenacity re-raises the last error")  # pragma: no cover
