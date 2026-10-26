"""LLM backend interface.

Used for the optional query-rewrite step (build_docs/04-core-engine-specs.md
section 5.5, step 1) and any future LLM-shaped feature (reranker prompts,
answer generation). Off by default per open decisions 1–2 — this interface
exists so adding them later is a backend swap, not a redesign.
"""

from __future__ import annotations

from typing import Protocol


class LLMBackend(Protocol):
    """Interface every LLM backend implements.

    `model_name` identifies the model in logs; `chat` sends an OpenAI-shaped
    message list and returns the assistant reply as a string.
    """

    model_name: str

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion and return the assistant text."""
        ...
