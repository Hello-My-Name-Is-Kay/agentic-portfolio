"""Additional unit tests for config and judge modules."""

from __future__ import annotations

import pytest

from eval_harness.config import EvalSettings
from eval_harness.judge import LlmJudge


class TestEvalSettings:
    """Tests for the EvalSettings configuration."""

    def test_default_values(self) -> None:
        settings = EvalSettings()
        assert settings.eval_min_score == 0.85
        assert settings.dataset_path == "tests/fixtures/golden_dataset.jsonl"
        assert settings.llm_judge_model == "llama3.2"
        assert settings.llm_judge_url == "http://localhost:11434"

    def test_env_prefix(self) -> None:
        settings = EvalSettings()
        assert settings.model_config.get("env_prefix") == "EVAL_"

    def test_env_file_configured(self) -> None:
        settings = EvalSettings()
        assert "env_file" in settings.model_config

    def test_forbid_extra(self) -> None:
        settings = EvalSettings()
        assert settings.model_config.get("extra") == "forbid"


class TestLlmJudge:
    """Tests for the LLM judge (unit-level, not calling external)."""

    def test_judge_initializes(self) -> None:
        judge = LlmJudge(model="test-model", base_url="http://localhost:11434")
        assert judge._model == "test-model"
        assert judge._base_url == "http://localhost:11434"
        assert judge._temperature == 0.0
        assert judge._timeout_s == 60

    def test_judge_custom_timeout(self) -> None:
        judge = LlmJudge(model="m", base_url="http://localhost:11434", timeout_s=30, temperature=0.5)
        assert judge._timeout_s == 30
        assert judge._temperature == 0.5

    def test_judge_url_normalization(self) -> None:
        judge = LlmJudge(model="m", base_url="http://localhost:11434/")
        # Should strip trailing slash
        assert judge._base_url == "http://localhost:11434"