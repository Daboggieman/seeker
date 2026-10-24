"""Embedding backend — interface and mock implementation.

The contract (docs/build_docs/04-core-engine-specs.md section 5.3):
- `nomic-embed-text` (768-dim) via Ollama at launch, batched (32 chunks/request).
- Store `embedding_model` per chunk — the same model indexes and queries.

The mock backend is deterministic and tagged `embedding_model: "mock"` so it is
never confused with a real model's vectors.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import numpy as np


class EmbeddingBackend(Protocol):
    """The embedding backend contract.  Swap implementations without touching callers."""

    @property
    def model_name(self) -> str:
        """The model name stored on every chunk, e.g. 'nomic-embed-text' or 'mock'."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one normalized vector per input text."""
        ...


def _make_deterministic_vector(text: str, dim: int) -> list[float]:
    """A deterministic pseudo-embedding built from the text hash.

    Not useful for retrieval — exists only to unblock the pipeline while a real
    backend is not installed.  Vectors tagged `embedding_model: "mock"` cannot be
    ANN-searched against real vectors and the per-chunk model field enforces this.
    """
    seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)  # fits uint32
    rng = np.random.RandomState(seed)
    raw = rng.randn(dim).astype(np.float64)
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


class MockEmbeddingBackend:
    """Deterministic, deterministic vector backend for pre-Ollama development."""

    DIM = 768  # matches nomic-embed-text

    @property
    def model_name(self) -> str:
        return "mock"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_make_deterministic_vector(t, self.DIM) for t in texts]
