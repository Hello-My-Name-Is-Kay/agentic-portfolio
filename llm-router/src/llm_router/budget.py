"""Token and cost budget tracker.

Enforces limits on total tokens in, tokens out, and cost across
all provider calls. Used to prevent runaway spending.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm_router.errors import BudgetExceededError
from llm_router.logging import get_logger

if TYPE_CHECKING:
    from llm_router.models import LLMResponse

log = get_logger(__name__)


class Budget:
    """Tracks and enforces token/cost budgets across provider calls."""

    def __init__(
        self,
        max_tokens_in: int = 1_000_000,
        max_tokens_out: int = 100_000,
        max_cost_usd: float = 10.0,
    ) -> None:
        """Set the limits; all counters start at zero."""
        self.max_tokens_in = max_tokens_in
        self.max_tokens_out = max_tokens_out
        self.max_cost_usd = max_cost_usd

        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._total_cost_usd = 0.0

    @property
    def total_tokens_in(self) -> int:
        """Input tokens recorded so far."""
        return self._total_tokens_in

    @property
    def total_tokens_out(self) -> int:
        """Output tokens recorded so far."""
        return self._total_tokens_out

    @property
    def total_cost_usd(self) -> float:
        """Estimated cost recorded so far."""
        return self._total_cost_usd

    def ensure_available(self) -> None:
        """Raise before a call if any limit has already been reached.

        Raises:
            BudgetExceededError: If tokens in, tokens out or cost is at or over its limit.
        """
        if self._total_tokens_in >= self.max_tokens_in:
            raise BudgetExceededError("total_tokens_in", self.max_tokens_in, self._total_tokens_in)
        if self._total_tokens_out >= self.max_tokens_out:
            raise BudgetExceededError("total_tokens_out", self.max_tokens_out, self._total_tokens_out)
        if self._total_cost_usd >= self.max_cost_usd:
            raise BudgetExceededError("total_cost_usd", self.max_cost_usd, self._total_cost_usd)

    def record(self, response: LLMResponse) -> None:
        """Record a response and check if budgets are still within limits.

        Args:
            response: The LLM response to record.

        Raises:
            BudgetExceededError: If recording this response pushes any metric over its limit.
        """
        self._total_tokens_in += response.tokens_in
        self._total_tokens_out += response.tokens_out
        self._total_cost_usd += response.cost_usd

        if self._total_tokens_in > self.max_tokens_in:
            raise BudgetExceededError("total_tokens_in", self.max_tokens_in, self._total_tokens_in)
        if self._total_tokens_out > self.max_tokens_out:
            raise BudgetExceededError("total_tokens_out", self.max_tokens_out, self._total_tokens_out)
        if self._total_cost_usd > self.max_cost_usd:
            raise BudgetExceededError("total_cost_usd", self.max_cost_usd, self._total_cost_usd)

        log.info(
            "budget.record",
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
            total_tokens_in=self._total_tokens_in,
            total_tokens_out=self._total_tokens_out,
            total_cost_usd=round(self._total_cost_usd, 6),
        )

    def reset(self) -> None:
        """Reset all counters."""
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._total_cost_usd = 0.0
