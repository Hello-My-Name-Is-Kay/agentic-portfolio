"""Input screening with Amazon Bedrock Guardrails (``ApplyGuardrail``), before a message enters the graph.

Personal data (cards, emails, phone numbers) is masked before it reaches the conversation state, the checkpointer or
the logs. Prompt attacks, harmful content and denied topics are refused without running any tool. The guardrail fails
open: if Bedrock is unavailable the message passes unscreened, because writes are protected in code regardless.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from agent.logging import get_logger

if TYPE_CHECKING:
    from agent.config import AgentSettings

log = get_logger(__name__)


@dataclass(frozen=True)
class Screened:
    """The message as it may be stored, and whether the guardrail blocked it."""

    text: str
    blocked_by: str | None = None  # comma-separated filter names, e.g. "PROMPT_ATTACK"


class InputGuardrail(Protocol):
    """Screens one customer message."""

    async def __call__(self, text: str) -> Screened:
        """Return the (possibly masked) text, or the filters that blocked it."""
        ...


class NoGuardrail:
    """Pass-through used when no guardrail is configured (tests, local runs)."""

    async def __call__(self, text: str) -> Screened:
        """Return the message unchanged."""
        return Screened(text)


def _blocking_filters(assessments: Any) -> list[str]:
    """Collect the names of every filter whose action is ``BLOCKED`` in an ApplyGuardrail assessment."""
    found: list[str] = []
    if isinstance(assessments, dict):
        if assessments.get("action") == "BLOCKED":
            found.append(str(assessments.get("name") or assessments.get("type") or "UNKNOWN"))
        for value in assessments.values():
            found += _blocking_filters(value)
    elif isinstance(assessments, list):
        for value in assessments:
            found += _blocking_filters(value)
    return found


class BedrockGuardrail:
    """Calls ``ApplyGuardrail`` on the customer's message (source ``INPUT``) with a pinned guardrail version."""

    def __init__(self, settings: AgentSettings, client: Any = None) -> None:
        """Use an injected ``bedrock-runtime`` client (tests), or create one on first use."""
        self._settings = settings
        self._client = client

    def _bedrock(self) -> Any:
        import boto3
        from botocore.config import Config

        return boto3.client(
            "bedrock-runtime",
            region_name=self._settings.aws_region,
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "adaptive"}),
        )

    async def __call__(self, text: str) -> Screened:
        """Screen the message; any error lets it through unscreened and is logged."""
        s = self._settings
        try:
            if self._client is None:
                self._client = self._bedrock()
            response = await asyncio.to_thread(
                self._client.apply_guardrail,
                guardrailIdentifier=s.guardrail_id,
                guardrailVersion=s.guardrail_version,
                source="INPUT",
                content=[{"text": {"text": text}}],
            )
        except Exception as exc:  # fail open: auth, step-up and ownership checks still protect every write
            log.warning("guardrail.unavailable", error=type(exc).__name__, detail=str(exc)[:200])
            return Screened(text)

        if response.get("action") != "GUARDRAIL_INTERVENED":
            return Screened(text)
        blocked = sorted(set(_blocking_filters(response.get("assessments", []))))
        if blocked:
            log.info("guardrail.blocked", filters=blocked)
            return Screened("[message blocked by guardrail]", blocked_by=",".join(blocked))
        outputs = response.get("outputs") or [{"text": text}]
        log.info("guardrail.masked")
        return Screened(str(outputs[0]["text"]))


def make_guardrail(settings: AgentSettings) -> InputGuardrail:
    """Return the Bedrock guardrail when ``AGENT_GUARDRAIL_ID`` is set, otherwise a pass-through."""
    return BedrockGuardrail(settings) if settings.guardrail_id else NoGuardrail()
