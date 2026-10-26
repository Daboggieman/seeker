"""Unit tests for the sqlite-vec vector store.

Contract (docs/build_docs/04-core-engine-specs.md section 5.4;
docs/handover_docs/02-engine-conventions.md): single-file store, per-chunk
`embedding_model`, `content_hash` gate support, same-model query filtering,
metadata preserved through the pipeline.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from seeker.embeddings.mock import MockEmbeddingBackend
from seeker.store.records import DocumentRecord, StoredChunk
from seeker.store.store import VectorStore

MODEL = "mock"


def run(coro):
    return asyncio.run(coro)


def make_document(path: str = "/docs/a.txt", doc_id: str = "doc-1") -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        source_id="fs-home",
        path=path,
        title="A Document",
        mime_type="text/plain",
        modified_at="2026-10-26T00:00:00Z",
        indexed_at="2026-10-26T00:00:01Z",
        content_hash=f"hash-{path}",
    )


def make_chunk(
    doc_id: str,
    text: str,
    position: int = 0,
    vector: list[float] | None = None,
    model: str = MODEL,
    chunk_id: str | None = None,
) -> StoredChunk:
    if vector is None:
        vector = run(MockEmbeddingBackend(dimensions=8).embed_query(text))
    return StoredChunk(
        id=chunk_id or f"chunk-{doc_id}-{position}",
        document_id=doc_id,
        text=text,
        position=position,
        page=None,
        embedding_model=model,
        vector=vector,
    )


@pytest.fixture
def store(tmp_path):
    return VectorStore(tmp_path / "test.db", dimensions=8)


class TestOpening:
    def test_reopening_same_dimensions_is_fine(self, tmp_path) -> None:
        first = VectorStore(tmp_path / "db.sqlite", dimensions=8)
        first._conn.close()
        reopened = VectorStore(tmp_path / "db.sqlite", dimensions=8)
        assert reopened.dimensions == 8

    def test_reopening_with_other_dimensions_fails(self, tmp_path) -> None:
        first = VectorStore(tmp_path / "db.sqlite", dimensions=8)
        first._conn.close()
        with pytest.raises(ValueError, match="dimensions"):
            VectorStore(tmp_path / "db.sqlite", dimensions=16)

    def test_nonpositive_dimensions_raise(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            VectorStore(tmp_path / "db.sqlite", dimensions=0)


class TestDocuments:
    def test_upsert_then_fetch_by_path(self, store: VectorStore) -> None:
        doc = make_document()
        store.upsert_document(doc)
        assert store.get_document_by_path("/docs/a.txt") == doc

    def test_upsert_same_path_updates_row(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        updated = replace(make_document(), content_hash="hash-v2", indexed_at="T2")
        store.upsert_document(updated)
        assert store.get_document_by_path("/docs/a.txt").content_hash == "hash-v2"
        assert store.get_document_by_path("/docs/a.txt").id == "doc-1"

    def test_unknown_path_returns_none(self, store: VectorStore) -> None:
        assert store.get_document_by_path("/nope") is None

    def test_delete_document_removes_everything(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks("doc-1", [make_chunk("doc-1", "some text")])
        store.delete_document("doc-1")
        assert store.get_document_by_path("/docs/a.txt") is None
        assert store.search(
            run(MockEmbeddingBackend(dimensions=8).embed_query("some text")),
            model_name=MODEL,
            top_k=5,
        ) == []


class TestChunks:
    def test_chunks_replace_atomically(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks("doc-1", [make_chunk("doc-1", "alpha")])
        store.replace_chunks("doc-1", [make_chunk("doc-1", "bravo")])
        hits = store.search(
            run(MockEmbeddingBackend(dimensions=8).embed_query("bravo")),
            model_name=MODEL,
            top_k=5,
        )
        assert [h.text for h in hits] == ["bravo"]

    def test_chunk_with_foreign_document_id_raises(self, store: VectorStore) -> None:
        with pytest.raises(ValueError, match="belongs to"):
            store.replace_chunks("doc-1", [make_chunk("other-doc", "text")])

    def test_stale_vectors_are_gone_after_replace(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks("doc-1", [make_chunk("doc-1", "alpha")])
        store.replace_chunks(
            "doc-1", [make_chunk("doc-1", "alpha", chunk_id="reused-id")]
        )
        # No unique/ghost-vector errors on search after the swap.
        hits = store.search(
            run(MockEmbeddingBackend(dimensions=8).embed_query("alpha")),
            model_name=MODEL,
            top_k=5,
        )
        assert len(hits) == 1


class TestSearch:
    def test_nearest_chunk_ranks_first(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks(
            "doc-1",
            [
                make_chunk("doc-1", "quarterly budget disagreement", position=0),
                make_chunk("doc-1", "sourdough bread recipe", position=1),
            ],
        )
        backend = MockEmbeddingBackend(dimensions=8)
        query = run(backend.embed_query("quarterly budget disagreement"))
        hits = store.search(query, model_name=MODEL, top_k=2)
        assert hits[0].text == "quarterly budget disagreement"
        assert hits[0].path == "/docs/a.txt"
        assert hits[0].source_id == "fs-home"
        assert hits[0].title == "A Document"
        assert hits[0].score == pytest.approx(0.0, abs=1e-5)

    def test_top_k_is_respected_exactly(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks(
            "doc-1",
            # "topic N" pairs can hash-cancel to zero at 8 dims; four topics
            # chosen to stay nonzero (verified 2026-10-26).
            [make_chunk("doc-1", f"topic {i}", position=i) for i in range(4)],
        )
        query = run(MockEmbeddingBackend(dimensions=8).embed_query("topic 0"))
        hits = store.search(query, model_name=MODEL, top_k=2)
        assert len(hits) == 2

    def test_wrong_model_chunks_never_returned(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        store.replace_chunks(
            "doc-1", [make_chunk("doc-1", "budget text", model="nomic-embed-text")]
        )
        hits = store.search(
            run(MockEmbeddingBackend(dimensions=8).embed_query("budget")),
            model_name=MODEL,
            top_k=5,
        )
        assert hits == []

    def test_source_filter_restricts_results(self, store: VectorStore) -> None:
        backend = MockEmbeddingBackend(dimensions=8)
        query = run(backend.embed_query("shared phrase"))
        # Two documents, same wording, different sources.
        store.upsert_document(make_document(path="/docs/a.txt", doc_id="doc-a"))  # fs-home
        store.upsert_document(
            replace(make_document(path="/docs/b.txt", doc_id="doc-b"), source_id="fs-other")
        )
        store.replace_chunks(
            "doc-a", [make_chunk("doc-a", "shared phrase here", position=0)]
        )
        store.replace_chunks(
            "doc-b", [make_chunk("doc-b", "shared phrase there", position=0)]
        )
        hits = store.search(query, model_name=MODEL, top_k=10, source_ids=["fs-home"])
        assert hits, "expected matches before filtering"
        assert {h.source_id for h in hits} == {"fs-home"}

    def test_zero_query_vector_rejected(self, store: VectorStore) -> None:
        with pytest.raises(ValueError, match="zero vector"):
            store.search([0.0] * 8, model_name=MODEL, top_k=3)

    def test_nonpositive_top_k_rejected(self, store: VectorStore) -> None:
        with pytest.raises(ValueError):
            store.search([1.0] * 8, model_name=MODEL, top_k=0)


class TestNormalization:
    def test_inserted_vectors_are_normalized(self, store: VectorStore) -> None:
        store.upsert_document(make_document())
        # An unnormalized (2x) vector must still behave like its unit vector.
        big_vector = [v * 10 for v in run(MockEmbeddingBackend(dimensions=8).embed_query("alpha"))]
        store.replace_chunks("doc-1", [make_chunk("doc-1", "alpha", vector=big_vector)])
        scaled_query = [v * 5 for v in run(MockEmbeddingBackend(dimensions=8).embed_query("alpha"))]
        hits = store.search(scaled_query, model_name=MODEL, top_k=1)
        assert hits[0].score == pytest.approx(0.0, abs=1e-5)
