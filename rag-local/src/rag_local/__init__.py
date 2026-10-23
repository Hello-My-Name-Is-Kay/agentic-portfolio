# RAG on Local Models — Portfolio Project
#
# Retrieval-Augmented Generation engine using Chroma vector store and
# Ollama-hosted local language models. Answers questions by grounding
# them in a corpus of rental-policy documents.
#
# This project demonstrates:
#   - Local-first RAG pipeline (no external API dependencies)
#   - Citations in every answer for auditability
#   - Confidence-threshold guardrails (refuses when unsure)
#   - Measured retrieval quality (recall@k)
#   - Structured logging, typed errors, and exhaustive tests
"""

from __future__ import annotations

__version__ = "0.1.0"