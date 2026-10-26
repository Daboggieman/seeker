"""Engine configuration.

Environment-driven settings for which backend serves embeddings and LLM calls.
The universal `openai` kind covers Ollama, LM Studio, OpenRouter, Groq, vLLM,
etc. — only the base URL, key, and model name differ (the user's call:
a universal setup that accepts any endpoint).

Env vars (all optional; defaults make the engine runnable with zero setup):
    SEEKER_EMBEDDING_BACKEND   mock | openai          (default: mock)
    SEEKER_EMBEDDING_MODEL     e.g. nomic-embed-text  (default: mock)
    SEEKER_EMBEDDING_BASE_URL  e.g. http://localhost:11434
    SEEKER_EMBEDDING_API_KEY   defaults to "not-required" for local runtimes
    SEEKER_EMBEDDING_DIMENSIONS  default 768
    SEEKER_LLM_BACKEND         mock | openai          (default: mock)
    SEEKER_LLM_MODEL           e.g. qwen3:14b
    SEEKER_LLM_BASE_URL        defaults to embedding base URL if unset
    SEEKER_LLM_API_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineSettings:
    embedding_backend: str = "mock"  # mock | openai
    embedding_model: str = "mock"
    embedding_base_url: str = ""
    embedding_api_key: str = "not-required"
    embedding_dimensions: int = 768

    llm_backend: str = "mock"  # mock | openai
    llm_model: str = "mock-llm"
    llm_base_url: str = ""  # falls back to embedding_base_url when empty
    llm_api_key: str = "not-required"


def load_settings(env: dict[str, str] | None = None) -> EngineSettings:
    """Build settings from `env` (default: os.environ), SEEKER_-prefixed."""
    source = os.environ if env is None else env

    def get(key: str, default: str) -> str:
        return source.get(f"SEEKER_{key}", default)

    def get_int(key: str, default: int) -> int:
        raw = source.get(f"SEEKER_{key}")
        return int(raw) if raw else default

    return EngineSettings(
        embedding_backend=get("EMBEDDING_BACKEND", "mock"),
        embedding_model=get("EMBEDDING_MODEL", "mock"),
        embedding_base_url=get("EMBEDDING_BASE_URL", ""),
        embedding_api_key=get("EMBEDDING_API_KEY", "not-required"),
        embedding_dimensions=get_int("EMBEDDING_DIMENSIONS", 768),
        llm_backend=get("LLM_BACKEND", "mock"),
        llm_model=get("LLM_MODEL", "mock-llm"),
        llm_base_url=get("LLM_BASE_URL", ""),
        llm_api_key=get("LLM_API_KEY", "not-required"),
    )
