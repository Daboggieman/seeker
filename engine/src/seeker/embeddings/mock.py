"""Deterministic mock embedding backend.

Decision of 2026-10-24 (docs/handover_docs/02-engine-conventions.md departure
record; open decision 9): Ollama is not installed, so Phase 1 builds against a
mock backend — deterministic vectors behind the same interface as the future
Ollama backend, tagged `embedding_model: "mock"`.

Vectors are bag-of-words via the hashing trick: each token hashes to a
coordinate and a sign, hits are accumulated, and the result is L2-normalized.
Same text always yields the same vector (hashlib digests, never Python's
randomized `hash()`), and texts sharing vocabulary land near each other —
enough for the query pipeline to behave sensibly in tests. Recall measured on
these vectors means nothing about retrieval quality; it measures pipeline
plumbing only.
"""

from __future__ import annotations

import hashlib
import re

_TOKEN = re.compile(r"\w+")

# nomic-embed-text's dimensionality (docs/build_docs/04-core-engine-specs.md
# section 5.3), so the vector store is exercised at the real size from day one.
_DEFAULT_DIMENSIONS = 768


class MockEmbeddingBackend:
    """Deterministic hash-based embedder implementing `EmbeddingBackend`."""

    def __init__(self, dimensions: int = _DEFAULT_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.model_name = "mock"

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            vector[value % self.dimensions] += 1.0 if value >> 63 else -1.0
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
