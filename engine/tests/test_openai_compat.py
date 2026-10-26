"""Unit tests for the universal OpenAI-compatible backends.

Runs against `httpx.MockTransport` — no network, no live server. The contract
under test is the wire shape: `/v1/embeddings` and `/v1/chat/completions`
requests as the OpenAI API defines them, since that is what makes the class
universal across Ollama, LM Studio, OpenRouter, Groq, vLLM, etc.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from seeker.embeddings.openai_compat import OpenAICompatibleEmbeddingBackend
from seeker.llm.openai_compat import OpenAICompatibleLLMBackend


def run(coro):
    return asyncio.run(coro)


class RecordingTransport(httpx.AsyncBaseTransport):
    """Mock transport that records requests and replays a canned response."""

    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._status_code = status_code
        self._payload = payload or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            self._status_code,
            json=self._payload,
            request=request,
        )


def embedding_payload(dims: int = 4) -> dict:
    return {"data": [{"embedding": [0.1] * dims, "index": 0}]}


class TestEmbeddingBackend:
    def test_embed_query_hits_embeddings_endpoint(self) -> None:
        transport = RecordingTransport(payload=embedding_payload())
        backend = OpenAICompatibleEmbeddingBackend(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434",
            transport=transport,
        )
        vector = run(backend.embed_query("hello"))
        assert len(vector) == 4
        request = transport.requests[0]
        assert request.url.path == "/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer not-required"

    def test_embed_query_sends_model_and_input(self) -> None:
        transport = RecordingTransport(payload=embedding_payload())
        backend = OpenAICompatibleEmbeddingBackend(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434",
            transport=transport,
        )
        run(backend.embed_query("hello world"))
        body = json.loads(transport.requests[0].content)
        assert body["model"] == "nomic-embed-text"
        assert body["input"] == "hello world"

    def test_embed_documents_preserves_order(self) -> None:
        payload = {
            "data": [
                {"embedding": [1.0, 0.0], "index": 0},
                {"embedding": [0.0, 1.0], "index": 1},
            ]
        }
        transport = RecordingTransport(payload=payload)
        backend = OpenAICompatibleEmbeddingBackend(
            model_name="m", base_url="http://x", transport=transport
        )
        vectors = run(backend.embed_documents(["a", "b"]))
        assert vectors == [[1.0, 0.0], [0.0, 1.0]]
        body = json.loads(transport.requests[0].content)
        assert body["input"] == ["a", "b"]

    def test_trailing_slash_on_base_url_is_normalized(self) -> None:
        transport = RecordingTransport(payload=embedding_payload())
        backend = OpenAICompatibleEmbeddingBackend(
            model_name="m", base_url="http://x/", transport=transport
        )
        run(backend.embed_query("q"))
        assert transport.requests[0].url.path == "/v1/embeddings"

    def test_http_error_propagates(self) -> None:
        transport = RecordingTransport(status_code=500, payload={"error": "boom"})
        backend = OpenAICompatibleEmbeddingBackend(
            model_name="m", base_url="http://x", transport=transport
        )

        with pytest.raises(httpx.HTTPStatusError):
            run(backend.embed_query("q"))

    def test_empty_base_url_or_model_raise(self) -> None:

        with pytest.raises(ValueError):
            OpenAICompatibleEmbeddingBackend(model_name="m", base_url="")
        with pytest.raises(ValueError):
            OpenAICompatibleEmbeddingBackend(model_name="", base_url="http://x")


class TestLLMBackend:
    def test_chat_hits_chat_completions(self) -> None:
        payload = {
            "choices": [{"message": {"role": "assistant", "content": "rewritten query"}}]
        }
        transport = RecordingTransport(payload=payload)
        backend = OpenAICompatibleLLMBackend(
            model_name="qwen3:14b",
            base_url="http://localhost:11434",
            transport=transport,
        )
        messages = [{"role": "user", "content": "raw query"}]
        reply = run(backend.chat(messages))
        assert reply == "rewritten query"
        request = transport.requests[0]
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "qwen3:14b"
        assert body["messages"] == messages

    def test_http_error_propagates(self) -> None:
        transport = RecordingTransport(status_code=503, payload={"error": "down"})
        backend = OpenAICompatibleLLMBackend(
            model_name="m", base_url="http://x", transport=transport
        )

        with pytest.raises(httpx.HTTPStatusError):
            run(backend.chat([{"role": "user", "content": "hi"}]))


class TestMockLLM:
    def test_default_reply_echoes_last_user_message(self) -> None:
        from seeker.llm.mock import MockLLMBackend

        backend = MockLLMBackend()
        messages = [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "budget disagreement doc"},
        ]
        assert run(backend.chat(messages)) == "budget disagreement doc"

    def test_configured_reply_is_fixed(self) -> None:
        from seeker.llm.mock import MockLLMBackend

        backend = MockLLMBackend(reply="fixed reply")
        assert run(backend.chat([{"role": "user", "content": "anything"}])) == "fixed reply"
