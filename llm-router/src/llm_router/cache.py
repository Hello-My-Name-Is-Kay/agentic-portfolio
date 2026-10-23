"""Response cache for LLM calls.

Caches responses keyed by (provider, model, prompt) to avoid
redundant API calls for identical requests within the TTL window.
"""

from __future__ import annotations

import hashlib
import json
from llm_router.logging import get_logger
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_router.models import LLMResponse

log = get_logger(__name__)


class ResponseCache:
    """Simple in-memory LRU cache for LLM responses.

    Keys are hashed (provider + model + prompt) for fast lookup.
    Entries expire after TTL seconds.
    """

    def __init__(self, ttl_s: int = 300, max_size: int = 1000) -> None:
        if ttl_s < 0:
            raise ValueError("ttl_s must be non-negative")
        if max_size < 1:
            raise ValueError("max_size must be >= 1")

        self._ttl_s = ttl_s
        self._max_size = max_size
        self._cache: OrderedDict[str, tuple[float, "LLMResponse"]] = OrderedDict()

    def _make_key(self, provider: str, model: str, prompt: str) -> str:
        raw = f"{provider}::{model}::{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, provider: str, model: str, prompt: str) -> "LLMResponse | None":
        """Get a cached response if it exists and hasn't expired."""
        key = self._make_key(provider, model, prompt)
        entry = self._cache.get(key)
        if entry is None:
            return None

        timestamp, response = entry
        if time.monotonic() - timestamp > self._ttl_s:
            del self._cache[key]
            return None

        # Mark as recently used
        self._cache.move_to_end(key)
        log.info("cache.hit", provider=provider, model=model)
        return response

    def set(self, provider: str, model: str, prompt: str, response: "LLMResponse") -> None:
        """Cache a response."""
        if self._ttl_s <= 0:
            return  # TTL of 0 disables caching

        key = self._make_key(provider, model, prompt)

        # Evict oldest if over max size
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (time.monotonic(), response)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        log.info("Cache cleared")

    @property
    def size(self) -> int:
        return len(self._cache)