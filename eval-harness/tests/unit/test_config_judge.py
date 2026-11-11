"""Unit tests for config and the LLM judge (HTTP is mocked, no network)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from eval_harness.config import EvalSettings
from eval_harness.errors import ScorerError
from eval_harness.judge import LlmJudge


class TestEvalSettings:
    def test_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_EVAL_MIN_SCORE", raising=False)
        settings = EvalSettings(_env_file=None)  # type: ignore[call-arg]
        assert settings.eval_min_score == 0.85
        assert settings.llm_judge_model == "llama3.2"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVAL_EVAL_MIN_SCORE", "0.5")
        assert EvalSettings(_env_file=None).eval_min_score == 0.5  # type: ignore[call-arg]


def _judge(reply: Any, status: int = 200, seen: list[httpx.Request] | None = None) -> LlmJudge:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = {"message": {"content": reply}, "prompt_eval_count": 10, "eval_count": 5}
        return httpx.Response(status, json=body)

    return LlmJudge(model="judge-model", base_url="http://ollama.test/", transport=httpx.MockTransport(handler))


class TestLlmJudge:
    def test_sends_ollama_chat_request(self) -> None:
        seen: list[httpx.Request] = []
        score = _judge('{"score": 0.8, "reasoning": "ok"}', seen=seen).evaluate("Q?", "A.", {"criteria": ["c1"]})
        assert score == 0.8
        assert str(seen[0].url) == "http://ollama.test/api/chat"
        payload = json.loads(seen[0].content)
        assert payload["model"] == "judge-model"
        assert payload["options"] == {"temperature": 0.0}
        assert payload["stream"] is False
        assert "Q?" in payload["messages"][1]["content"]
        assert "c1" in payload["messages"][1]["content"]

    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ('{"score": 1.7}', 1.0),
            ('{"score": -2}', 0.0),
            ('{"score": "high"}', 0.0),
            ('{"reasoning": "no score"}', 0.0),
            ("not json at all", 0.0),
            ("[0.9]", 0.0),
        ],
    )
    def test_score_parsing_and_clamping(self, reply: str, expected: float) -> None:
        assert _judge(reply).evaluate("q", "a", {}) == expected

    def test_http_error_raises_scorer_error(self) -> None:
        with pytest.raises(ScorerError, match="LLM judge call failed"):
            _judge("", status=500).evaluate("q", "a", {})

    def test_connection_error_raises_scorer_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        judge = LlmJudge(transport=httpx.MockTransport(handler))
        with pytest.raises(ScorerError):
            judge.evaluate("q", "a", {})
