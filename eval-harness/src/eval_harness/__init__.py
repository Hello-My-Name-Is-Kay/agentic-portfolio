"""Eval harness: golden-dataset evaluation for LLM pipelines.

Loads a JSONL golden dataset, scores pipeline answers (substring accuracy and
document recall, optionally an LLM-as-judge rubric score), and fails a CI job
when scores drop below a threshold.
"""

from __future__ import annotations

__version__ = "0.1.0"
