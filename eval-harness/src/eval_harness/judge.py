"""LLM-as-judge: use an LLM to evaluate answer quality against a rubric.

This module sends the question, answer, and rubric to a judge LLM
and parses the judgment to produce a score.
"""

from __future__ import annotations

import json
from eval_harness.logging import get_logger
from typing import Any

from eval_harness.errors import ScorerError

log = get_logger(__name__)


_JUDGE_SYSTEM_PROMPT = """You are an expert evaluator of AI-generated answers.
You will be given a question, an answer, and a rubric.
Rate the answer on a scale of 0.0 to 1.0 based on the rubric criteria.

Return ONLY a JSON object with:
  - "score": float between 0.0 and 1.0
  - "reasoning": brief explanation of the score
  - "criteria_scores": dict of individual criteria and their scores

Do not include any text outside the JSON object.
"""


class LlmJudge:
    """LLM-as-judge evaluator using Ollama."""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout_s: int = 60,
        temperature: float = 0.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._temperature = temperature

    def evaluate(self, question: str, answer: str, rubric: dict[str, Any]) -> float:
        """Evaluate an answer against a rubric.

        Args:
            question: The original question.
            answer: The generated answer.
            rubric: Dict with at least "criteria" key mapping to list of criteria strings.

        Returns:
            Score between 0.0 and 1.0.

        Raises:
            ScorerError: If the judge LLM fails to evaluate.
        """
        rubric_text = json.dumps(rubric, indent=2)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Answer: {answer}\n\n"
            f"Rubric: {rubric_text}\n\n"
            "Score this answer according to the rubric."
        )

        try:
            result = self._call_llm(user_prompt, _JUDGE_SYSTEM_PROMPT)
        except Exception as exc:
            raise ScorerError(f"LLM judge call failed: {exc}") from exc

        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            log.warning("judge.non_json", preview=result[:100])
            return 0.0

        score = data.get("score", 0.0)
        try:
            score = float(score)
        except (ValueError, TypeError):
            score = 0.0

        return max(0.0, min(1.0, score))

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        """Call an LLM (via Ollama) for evaluation."""
        import httpx
        import time

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "stream": False,
        }

        url = f"{self._base_url}/api/chat"
        start = time.monotonic()

        try:
            response = httpx.post(url, json=payload, timeout=httpx.Timeout(self._timeout_s))
            response.raise_for_status()
        except Exception as exc:
            raise ScorerError(f"LLM call failed: {exc}") from exc

        elapsed = time.monotonic() - start
        data = response.json()

        content = data.get("message", {}).get("content", "")
        log.info("judge.call", model=self._model,
                 self._model, elapsed,
                 data.get("prompt_eval_count", 0),
                 data.get("eval_count", 0))
        return content