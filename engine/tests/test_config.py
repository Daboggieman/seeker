"""Unit tests for config loading."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from seeker.config import load_settings


class TestDefaults:
    def test_embedding_defaults_to_mock(self) -> None:
        s = load_settings({})
        assert s.embedding_backend == "mock"
        assert s.embedding_model == "mock"

    def test_llm_defaults_to_mock(self) -> None:
        s = load_settings({})
        assert s.llm_backend == "mock"

    def test_embedding_dimensions_768(self) -> None:
        assert load_settings({}).embedding_dimensions == 768


class TestEnvOverride:
    def test_embedding_backend_from_env(self) -> None:
        s = load_settings({"SEEKER_EMBEDDING_BACKEND": "openai"})
        assert s.embedding_backend == "openai"

    def test_embedding_model_from_env(self) -> None:
        s = load_settings({"SEEKER_EMBEDDING_MODEL": "nomic-embed-text"})
        assert s.embedding_model == "nomic-embed-text"

    def test_embedding_base_url_from_env(self) -> None:
        s = load_settings({"SEEKER_EMBEDDING_BASE_URL": "http://localhost:11434"})
        assert s.embedding_base_url == "http://localhost:11434"

    def test_llm_model_from_env(self) -> None:
        s = load_settings({"SEEKER_LLM_MODEL": "qwen3:14b"})
        assert s.llm_model == "qwen3:14b"

    def test_llm_base_url_defaults_empty(self) -> None:
        # The factory falls back to embedding_base_url when llm_base_url is ""
        s = load_settings({})
        assert s.llm_base_url == ""

    def test_int_parsing(self) -> None:
        s = load_settings({"SEEKER_EMBEDDING_DIMENSIONS": "1536"})
        assert s.embedding_dimensions == 1536


class TestSettingsImmutable:
    def test_engine_settings_is_frozen(self) -> None:
        s = load_settings({})
        with pytest.raises(FrozenInstanceError):
            s.embedding_backend = "openai"  # type: ignore[misc]
