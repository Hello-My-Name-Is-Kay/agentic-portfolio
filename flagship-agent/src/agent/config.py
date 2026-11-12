"""Configuration for the flagship agent, read from ``AGENT_*`` environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent configuration."""

    booking_api_base: str = "http://localhost:8000"
    booking_api_key: str = ""

    max_steps: int = 12  # user turns per conversation before handing off to a human
    max_auth_failures: int = 3
    recursion_limit: int = 25  # LangGraph super-step limit for a single turn

    llm: Literal["keyword", "bedrock"] = "keyword"  # intent classifier; keyword keeps tests offline
    bedrock_model_id: str = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"  # EU cross-region inference profile
    aws_region: str = "eu-north-1"
    llm_max_tokens: int = 100

    guardrail_id: str = ""  # Bedrock guardrail screening every message; empty = no screening
    guardrail_version: str = "1"  # always a pinned version, never DRAFT

    model_config = SettingsConfigDict(env_file=".env", extra="forbid", env_prefix="AGENT_")
