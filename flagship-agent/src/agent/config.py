"""Configuration for the flagship agent, read from ``AGENT_*`` environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent configuration."""

    booking_api_base: str = "http://localhost:8000"
    booking_api_key: str = ""

    max_steps: int = 12  # user turns per conversation before handing off to a human
    max_auth_failures: int = 3
    recursion_limit: int = 25  # LangGraph super-step limit for a single turn

    model_config = SettingsConfigDict(env_file=".env", extra="forbid", env_prefix="AGENT_")
