"""Configuration for the LLM router via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class RouterSettings(BaseSettings):
    """Router configuration.

    Override via environment variables (ROUTER_* prefix) or .env file.
    """

    # Provider API keys (set via env vars only, never in code)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Provider timeouts (seconds)
    anthropic_timeout_s: float = 30.0
    openai_timeout_s: float = 30.0
    ollama_timeout_s: float = 60.0

    # Retry settings
    max_retries: int = 3
    retry_min_wait_s: float = 0.5
    retry_max_wait_s: float = 4.0

    # Cache
    cache_ttl_s: int = 300  # 5 minutes
    cache_max_size: int = 1000

    # Budget
    max_total_tokens_in: int = 1_000_000
    max_total_tokens_out: int = 100_000
    max_cost_usd: float = 10.0

    model_config = {"env_file": ".env", "extra": "forbid", "env_prefix": "ROUTER_"}


class ProviderConfig(BaseSettings):
    """Per-provider configuration."""

    name: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_s: float = 30.0
    max_retries: int = 3

    model_config = {"extra": "forbid"}