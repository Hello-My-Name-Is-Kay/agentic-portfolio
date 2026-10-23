"""Configuration for the flagship agent."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    """Agent configuration from environment variables."""

    # --- API endpoints ---
    booking_api_base: str = "http://localhost:8000"
    booking_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # --- Agent limits ---
    max_steps: int = 12
    recursion_limit: int = 25

    # --- Step-up auth ---
    step_up_required_for: list[str] = ["change_reservation", "cancel_reservation"]

    # --- Generation ---
    llm_timeout_s: int = 30
    llm_temperature: float = 0.1

    model_config = {"env_file": ".env", "extra": "forbid", "env_prefix": "AGENT_"}