"""Configuration loading via pydantic-settings with env var support.

Fails fast at startup if required configuration is missing.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All paths are relative to the project root unless absolute.
    """

    # --- Vector store ---
    chroma_persist_dir: str = "./data/vectorstore"
    collection_name: str = "rental_policies"

    # --- Embedding model (sentence-transformers, CPU) ---
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # --- Chunking ---
    chunk_size: int = 512
    chunk_overlap: int = 64

    # --- Ollama LLM ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    llm_timeout_s: int = 60

    # --- Generation ---
    max_new_tokens: int = 512
    temperature: float = 0.1

    # --- Retrieval guardrails ---
    min_relevance_score: float = 0.35
    top_k: int = 5

    # --- Evaluation ---
    eval_min_score: float = 0.85

    model_config = {"env_file": ".env", "extra": "forbid", "env_prefix": "RAG_"}