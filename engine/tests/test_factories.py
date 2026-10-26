"""Unit tests for backend factories."""

from __future__ import annotations

import pytest

from seeker.config import load_settings
from seeker.embeddings.mock import MockEmbeddingBackend
from seeker.embeddings.openai_compat import OpenAICompatibleEmbeddingBackend
from seeker.factories import build_embedding_backend, build_llm_backend
from seeker.llm.mock import MockLLMBackend
from seeker.llm.openai_compat import OpenAICompatibleLLMBackend


class TestEmbeddingFactory:
    def test_mock_kind_builds_mock(self) -> None:
        backend = build_embedding_backend(load_settings({}))
        assert isinstance(backend, MockEmbeddingBackend)
        assert backend.model_name == "mock"

    def test_openai_kind_builds_universal(self) -> None:
        s = load_settings(
            {
                "SEEKER_EMBEDDING_BACKEND": "openai",
                "SEEKER_EMBEDDING_MODEL": "nomic-embed-text",
                "SEEKER_EMBEDDING_BASE_URL": "http://localhost:11434",
            }
        )
        backend = build_embedding_backend(s)
        assert isinstance(backend, OpenAICompatibleEmbeddingBackend)
        assert backend.model_name == "nomic-embed-text"

    def test_unknown_kind_raises(self) -> None:
        s = load_settings({"SEEKER_EMBEDDING_BACKEND": "brainfuck"})
        with pytest.raises(ValueError):
            build_embedding_backend(s)


class TestLLMFactory:
    def test_mock_kind_builds_mock(self) -> None:
        backend = build_llm_backend(load_settings({}))
        assert isinstance(backend, MockLLMBackend)

    def test_openai_kind_builds_universal(self) -> None:
        s = load_settings(
            {
                "SEEKER_LLM_BACKEND": "openai",
                "SEEKER_LLM_MODEL": "qwen3:14b",
                "SEEKER_LLM_BASE_URL": "http://localhost:11434",
            }
        )
        backend = build_llm_backend(s)
        assert isinstance(backend, OpenAICompatibleLLMBackend)
        assert backend.model_name == "qwen3:14b"

    def test_llm_base_url_falls_back_to_embedding_url(self) -> None:
        # One base URL serves both when only the embedding side is configured.
        s = load_settings(
            {
                "SEEKER_LLM_BACKEND": "openai",
                "SEEKER_EMBEDDING_BASE_URL": "http://localhost:11434",
            }
        )
        backend = build_llm_backend(s)
        assert isinstance(backend, OpenAICompatibleLLMBackend)
        assert backend._base_url == "http://localhost:11434"

    def test_unknown_kind_raises(self) -> None:
        s = load_settings({"SEEKER_LLM_BACKEND": "hal9000"})
        with pytest.raises(ValueError):
            build_llm_backend(s)
