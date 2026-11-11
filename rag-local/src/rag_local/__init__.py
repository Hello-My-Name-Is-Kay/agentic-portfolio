"""RAG on local models: answer rental-policy questions from a Chroma index.

Embeddings come from a local sentence-transformers model and answers from an
Ollama-hosted model. Answers cite the retrieved documents, and the pipeline
refuses when no chunk passes a similarity threshold.
"""

from __future__ import annotations

__version__ = "0.1.0"
