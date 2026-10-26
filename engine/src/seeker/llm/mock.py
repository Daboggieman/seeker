"""Deterministic mock LLM backend for development and tests.

Returns a fixed, deterministic reply so pipeline code that needs an LLM
(query rewriting, once enabled) runs without any network or model. Recall and
rewrite quality measured against this backend mean nothing.
"""

from __future__ import annotations


class MockLLMBackend:
    """Echo-style LLM: deterministic passthrough for tests and dev."""

    def __init__(self, model_name: str = "mock-llm", reply: str = "") -> None:
        self.model_name = model_name
        self._reply = reply

    async def chat(self, messages: list[dict[str, str]]) -> str:
        if self._reply:
            return self._reply
        # Deterministic default: repeat the last user message back.
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""
