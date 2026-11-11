"""Pattern-based prompt-injection detection.

A heuristic, not a classifier: it flags common instruction-override and
prompt-extraction phrasings. Patterns use word boundaries so ordinary words
("Jordan", "override fee") are not flagged on substrings alone.
"""

from __future__ import annotations

import re

INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("instruction_override", r"\b(ignore|disregard|forget)\b[^.\n]{0,30}\b(instructions|prompt|rules|policies)\b"),
    ("role_reassignment", r"\b(you are now|new role|new instructions)\b"),
    ("system_prompt_probe", r"\bsystem\W{0,3}(prompt|instructions|override|leak)\b"),
    ("jailbreak_persona", r"\b(do anything now|uncensored|jailbreak)\b"),
    ("verbatim_extraction", r"\brepeat everything\b"),
]


class InjectionDetector:
    """Flags text that matches known prompt-injection patterns."""

    def __init__(self, patterns: list[tuple[str, str]] | None = None) -> None:
        """Compile the given (name, regex) patterns, or the defaults."""
        self._patterns = [(name, re.compile(p, re.IGNORECASE)) for name, p in (patterns or INJECTION_PATTERNS)]

    def detect(self, text: str) -> list[str]:
        """Return the names of all patterns that match ``text``."""
        return [name for name, pattern in self._patterns if pattern.search(text)]
