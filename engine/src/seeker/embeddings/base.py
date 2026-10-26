"""Embedding backend interface.

Contract (docs/build_docs/04-core-engine-specs.md section 5.3, docs/build_docs/02-data-model.md):
- one interface, multiple backends — the mock today, an Ollama backend later;
- `model_name` is the value stored in each chunk's `embedding_model` field at
  embed time, so a model switch never leaves stale vectors ambiguous;
- queries are embedded with the same model that indexed the target chunks —
  mixing models is a bug, not a fallback (docs/handover_docs/02-engine-conventions.md).

The interface is async because the real backend will call a local HTTP
endpoint; the mock implements it with plain computation.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingBackend(Protocol):
    """Interface every embedding backend implements.

    `embed_query` and `embed_documents` are separate methods so backends that
    treat queries and passages differently (instruction prefixes, model
    routes) can do so without callers caring.
    """

    model_name: str
    dimensions: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passage texts for indexing; results match the input order."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        ...
