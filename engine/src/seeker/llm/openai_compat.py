"""Universal OpenAI-compatible chat backend.

Same contract as the embedding side: one class covers Ollama, LM Studio,
OpenRouter, Groq, vLLM, Cerebras, Together, or any server speaking
`/v1/chat/completions`. Only `base_url`, `api_key`, and `model_name` change.
"""

from __future__ import annotations

import httpx


class OpenAICompatibleLLMBackend:
    """OpenAI-compatible `/v1/chat/completions` endpoint."""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key: str = "not-required",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not model_name:
            raise ValueError("model_name is required")
        self.model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=120.0,
            transport=self._transport,
        )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        async with self._client() as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
