"""Golden dataset loader for JSONL format.

Each line is a JSON object with:
  - question: str
  - expected_answer_contains: str (substring expected in answer)
  - expected_docs: list[str] (expected source documents)
  - rubric: dict (optional, LLM-as-judge evaluation criteria)
"""

from __future__ import annotations

import json
from eval_harness.logging import get_logger
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eval_harness.errors import DatasetError

log = get_logger(__name__)


class EvalExample(BaseModel):
    """A single evaluation example from the golden dataset."""

    question: str = Field(..., description="The question to ask the pipeline")
    expected_answer_contains: str = Field(..., description="Substring expected in the answer")
    expected_docs: list[str] = Field(default_factory=list, description="Expected source document filenames")
    rubric: dict = Field(default_factory=dict, description="LLM-as-judge rubric criteria")
    metadata: dict = Field(default_factory=dict, description="Arbitrary metadata")


def load_dataset(path: str) -> list[EvalExample]:
    """Load a golden dataset from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of EvalExample objects.

    Raises:
        DatasetError: If the file is missing, malformed, or empty.
    """
    p = Path(path)

    if not p.exists():
        raise DatasetError(f"Dataset file not found: {path}")
    if not p.is_file():
        raise DatasetError(f"Dataset path is not a file: {path}")

    examples: list[EvalExample] = []
    errors: list[str] = []

    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue  # skip blanks and comments
        try:
            data = json.loads(line)
            example = EvalExample(**data)
            examples.append(example)
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"Line {lineno}: {exc}")

    if not examples:
        raise DatasetError(f"No valid examples found in {path}" +
                           (f" ({len(errors)} parse errors)" if errors else ""))

    log.info("dataset.loaded", count=len(examples), path=path)
    return examples


def dump_dataset(examples: list[EvalExample], path: str) -> None:
    """Write a list of examples to a JSONL file.

    Args:
        examples: List of EvalExample objects.
        path: Output file path.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = [json.dumps(ex.model_dump(), ensure_ascii=False) for ex in examples]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("dataset.dumped", count=len(examples), path=path)