"""Backend factories.

The single place that turns `EngineSettings` into live backend objects.
Everything downstream depends on the interfaces
(`EmbeddingBackend`, `LLMBackend`), never on a concrete class, so swapping
mock → Ollama → a hosted router is a config change, not a code change.
"""

from __future__ import annotations

from seeker.config import EngineSettings
from seeker.embeddings.base import EmbeddingBackend
from seeker.embeddings.mock import MockEmbeddingBackend
from seeker.embeddings.openai_compat import OpenAICompatibleEmbeddingBackend
from seeker.llm.base import LLMBackend
from seeker.llm.mock import MockLLMBackend
from seeker.llm.openai_compat import OpenAICompatibleLLMBackend


def build_embedding_backend(settings: EngineSettings) -> EmbeddingBackend:
    if settings.embedding_backend == "mock":
        return MockEmbeddingBackend(dimensions=settings.embedding_dimensions)
    if settings.embedding_backend == "openai":
        return OpenAICompatibleEmbeddingBackend(
            model_name=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"unknown embedding backend: {settings.embedding_backend!r}")


def build_llm_backend(settings: EngineSettings) -> LLMBackend:
    if settings.llm_backend == "mock":
        return MockLLMBackend(model_name=settings.llm_model)
    if settings.llm_backend == "openai":
        return OpenAICompatibleLLMBackend(
            model_name=settings.llm_model,
            base_url=settings.llm_base_url or settings.embedding_base_url,
            api_key=settings.llm_api_key,
        )
    raise ValueError(f"unknown llm backend: {settings.llm_backend!r}")
