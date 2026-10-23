"""Typed exception hierarchy for the eval harness."""

from __future__ import annotations


class EvalError(Exception):
    """Base for all eval harness errors."""


class ConfigError(EvalError):
    """Invalid configuration."""


class DatasetError(EvalError):
    """Golden dataset loading or validation error."""


class ScorerError(EvalError):
    """Error during scoring or rubric evaluation."""


class ThresholdGateError(EvalError):
    """Eval score fell below the minimum threshold."""
    def __init__(self, score: float, threshold: float, metric: str) -> None:
        self.score = score
        self.threshold = threshold
        self.metric = metric
        super().__init__(f"Eval gate FAILED: {metric}={score:.3f} < threshold={threshold:.3f}")