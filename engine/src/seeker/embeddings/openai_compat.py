"""Universal OpenAI-compatible embedding backend.

Handles Ollama, LM Studio, OpenRouter, Groq, vLLM, Cerebras, Together —
any server that exposes `/v1/embeddings` with the standard request/response
shape. Point `base_url` and `api_key` at any of them; the rest is identical.
"""

from __future__ import annotations

import httpx

from seeker.embeddings.base import EmbeddingBackend


class OpenAICompatibleEmbeddingBackend(EmbeddingBackend):
    """OpenAI-compatible `/v1/embeddings` endpoint.

    The `model_name` is stored verbatim in each chunk so a model switch is
    always detectable in the vector store (docs/handover_docs/02-engine-conventions.md).
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key: str = "not-required",
        dimensions: int = 768,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not model_name:
            raise ValueError("model_name is required")
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.dimensions = dimensions
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model_name

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=60.0,
            transport=self._transport,
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        async with self._client() as client:
            resp = await client.post(
                "/v1/embeddings",
                json={
                    "model": self._model_name,
                    "input": texts,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]

    async def embed_query(self, text: str) -> list[float]:
        async with self._client() as client:
            resp = await client.post(
                "/v1/embeddings",
                json={
                    "model": self._model_name,
                    "input": text,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
