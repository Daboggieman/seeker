"""Row types crossing the store boundary.

Mirrors docs/build_docs/02-data-model.md. Vectors live in the sqlite-vec
virtual table, never inline; `embedding_model` lives on every chunk row.
Timestamps are ISO-8601 UTC strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    source_id: str
    path: str
    title: str
    mime_type: str
    modified_at: str
    indexed_at: str
    content_hash: str


@dataclass(frozen=True)
class StoredChunk:
    """A chunk with its embedding, as written by the index pipeline."""

    id: str
    document_id: str
    text: str
    position: int
    page: int | None
    embedding_model: str
    vector: list[float]


@dataclass(frozen=True)
class SearchHit:
    """One KNN result; score is L2 distance (lower is better).

    Vectors are L2-normalized at insert and the query vector must be
    normalized too, so distance ordering is cosine ordering
    (d² = 2 − 2·cos θ for unit vectors).
    """

    chunk_id: str
    document_id: str
    text: str
    position: int
    page: int | None
    embedding_model: str
    score: float
    path: str
    source_id: str
    title: str
