"""Configuration for the eval harness via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class EvalSettings(BaseSettings):
    """Eval harness settings.

    Override via environment variables (EVAL_* prefix) or .env file.
    """

    # Dataset
    dataset_path: str = "tests/fixtures/golden_dataset.jsonl"
    dataset_encoding: str = "utf-8"

    # Scoring
    llm_judge_model: str = "llama3.2"
    llm_judge_url: str = "http://localhost:11434"
    llm_judge_timeout_s: int = 60
    llm_judge_temperature: float = 0.0

    # Thresholds
    eval_min_score: float = 0.85

    # Reporting
    json_report_path: str = "eval-report.json"
    html_report_path: str = "eval-report.html"

    model_config = {"env_file": ".env", "extra": "forbid", "env_prefix": "EVAL_"}