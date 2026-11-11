"""Deterministic fakes shared by the tests (no model download, no network)."""

from __future__ import annotations

import hashlib
import math

from rag_local.generator import LLMResponse


class HashEmbedder:
    """Bag-of-words embedder: each word hashes to a dimension; vectors are L2-normalised.

    Texts that share words get a high cosine similarity, which is enough to
    test retrieval end to end against a real Chroma index.
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in text.lower().split():
            word = word.strip(".,?!:;()[]#*'\"")
            if word:
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self._dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class EchoGenerator:
    """Returns the first line of the first document in the prompt, with a citation."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, system_prompt: str | None = None) -> LLMResponse:  # noqa: ARG002
        self.prompts.append(prompt)
        first_doc = prompt.split("--- Document 1", 1)[1].split("---\n", 1)[1].split("\n")[0]
        return LLMResponse(text=f"{first_doc} [Document 1]", model="echo", latency_ms=1.0, tokens_in=10, tokens_out=5)
