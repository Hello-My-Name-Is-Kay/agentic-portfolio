# Eval Harness — Portfolio Project
#
# A pytest-based evaluation framework for LLM pipelines.
# Supports golden datasets, LLM-as-judge rubrics, tool-trajectory
# assertions, and prompt A/B comparison.
#
# Integrates with GitHub Actions: failing the build when eval
# scores drop below a configurable threshold.
#
# Designed to gate every release — the "evals gate every release"
# signal from the job posting.

from __future__ import annotations

__version__ = "0.1.0"