"""Tests for the sqlite-vec store.

Contract (docs/build_docs/04-core-engine-specs.md section 5.4):
- sqlite-vec at launch: single file, no server, good for personal scale.
- Schema: documents, chunks, sources; vectors stored in sqlite-vec.
- content_hash gates re-embedding; embedding_model stored per chunk.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from seeker.chunking.chunker import Chunk
from seeker.embeddings.backends import MockEmbeddingBackend
from seeker.store.index import IndexStore


class TmpDB:
    """Create a temporary sqlite-vec database, clean up after the test."""

    def __init__(self) -> None:
        self.path = Path(tempfile.mktemp(suffix=".db"))

    def __enter__(self) -> TmpDB:
        return self

    def __exit__(self, *args: object) -> None:
        self.path.unlink(missing_ok=True)

    def conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))


def make_chunk(
    doc_id: str = "doc-1",
    position: int = 0,
    text: str = "the quick brown fox",
    page: int | None = None,
) -> Chunk:
    return Chunk(
        id=f"chunk-{doc_id}-{position}",
        document_id=doc_id,
        text=text,
        position=position,
        page=page,
    )


class TestIndexStoreInit:
    def test_creates_tables(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            conn = td.conn()
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            assert "documents" in tables
            assert "chunks" in tables
            assert "sources" in tables

    def test_init_is_idempotent(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.init()  # must not raise
            conn = td.conn()
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM documents"
                ).fetchone()[0]
                == 0
            )


class TestIndexStoreSources:
    def test_register_and_list_sources(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-home", "filesystem", {"root_path": "/home"})
            sources = store.list_sources()
            assert len(sources) == 1
            assert sources[0]["id"] == "fs-home"
            assert sources[0]["type"] == "filesystem"

    def test_register_twice_updates_config(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-home", "filesystem", {"root_path": "/home"})
            store.register_source("fs-home", "filesystem", {"root_path": "/docs"})
            sources = store.list_sources()
            assert len(sources) == 1
            assert '"root_path": "/docs"' in sources[0]["config"]

    def test_delete_source_removes_documents_and_chunks(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {"root": "/tmp"})
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/test.txt",
                title="test",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="abc123",
            )
            store.upsert_chunks([make_chunk("doc-1", 0, "hello world")])
            store.delete_source("fs-test")
            assert store.list_sources() == []
            conn = td.conn()
            assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0

    def test_update_sync_status(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            store.update_sync_status("fs-test", "idle")
            sources = store.list_sources()
            assert sources[0]["status"] == "idle"


class TestIndexStoreDocuments:
    def test_upsert_and_get_document(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/notes.txt",
                title="Meeting Notes",
                mime_type="text/plain",
                modified_at="2026-01-01T12:00:00Z",
                content_hash="abc",
            )
            doc = store.get_document("doc-1")
            assert doc is not None
            assert doc["title"] == "Meeting Notes"
            assert doc["content_hash"] == "abc"

    def test_upsert_document_updates_existing(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/a.txt",
                title="v1",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="v1",
            )
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/a.txt",
                title="v2",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:01Z",
                content_hash="v2",
            )
            doc = store.get_document("doc-1")
            assert doc is not None
            assert doc["title"] == "v2"
            assert doc["content_hash"] == "v2"

    def test_get_document_returns_none_for_unknown(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            assert store.get_document("does-not-exist") is None


class TestIndexStoreChunks:
    def test_upsert_chunks_stores_text_and_metadata(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/test.txt",
                title="test",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="abc",
            )
            store.upsert_chunks([make_chunk("doc-1", 0, "hello world", page=1)])
            conn = td.conn()
            row = conn.execute(
                "SELECT document_id, text, position, page FROM chunks WHERE id='chunk-doc-1-0'"
            ).fetchone()
            assert row == ("doc-1", "hello world", 0, 1)

    def test_chunks_are_associated_with_document(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/a.txt",
                title="a",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="x",
            )
            store.upsert_chunks([make_chunk("doc-1", 0, "alpha"), make_chunk("doc-1", 1, "beta")])
            conn = td.conn()
            count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id='doc-1'"
            ).fetchone()[0]
            assert count == 2


class TestIndexStoreSearch:
    def test_search_returns_results_with_scores(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            backend = MockEmbeddingBackend()
            # Index a known chunk
            chunk = make_chunk("doc-1", 0, "the quick brown fox jumps over the lazy dog")
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/test.txt",
                title="test",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="x",
            )
            vectors = backend.embed([chunk.text])
            store.upsert_chunks([chunk], vectors=vectors)
            # Query with a near-identical sentence
            query_vec = backend.embed(["the quick brown canine leaps over the sleepy cat"])[0]
            results = store.search(query_vec, top_k=3, source_ids=["fs-test"])
            assert len(results) >= 1
            assert results[0]["document_id"] == "doc-1"
            assert "score" in results[0]
            assert 0.0 <= results[0]["score"] <= 1.0

    def test_search_respects_source_filter(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            backend = MockEmbeddingBackend()
            store.register_source("fs-a", "filesystem", {})
            store.register_source("fs-b", "filesystem", {})
            store.upsert_document(
                doc_id="d-a",
                source_id="fs-a",
                path="/tmp/a.txt",
                title="a",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="x",
            )
            store.upsert_document(
                doc_id="d-b",
                source_id="fs-b",
                path="/tmp/b.txt",
                title="b",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="y",
            )
            chunk_a = make_chunk("d-a", 0, "finance quarterly report")
            chunk_b = make_chunk("d-b", 0, "lunch menu options")
            va = backend.embed([chunk_a.text])
            vb = backend.embed([chunk_b.text])
            store.upsert_chunks([chunk_a], vectors=va)
            store.upsert_chunks([chunk_b], vectors=vb)
            # Filter to fs-a only — should not return d-b
            results = store.search(va[0], top_k=5, source_ids=["fs-a"])
            doc_ids = {r["document_id"] for r in results}
            assert "d-a" in doc_ids
            assert "d-b" not in doc_ids

    def test_search_returns_snippet(self) -> None:
        with TmpDB() as td:
            store = IndexStore(td.path)
            store.init()
            store.register_source("fs-test", "filesystem", {})
            backend = MockEmbeddingBackend()
            long_text = " ".join(f"word{i}" for i in range(200))
            chunk = make_chunk("doc-1", 0, long_text)
            store.upsert_document(
                doc_id="doc-1",
                source_id="fs-test",
                path="/tmp/long.txt",
                title="long",
                mime_type="text/plain",
                modified_at="2026-01-01T00:00:00Z",
                content_hash="x",
            )
            store.upsert_chunks([chunk], vectors=backend.embed([chunk.text]))
            results = store.search(backend.embed(["query"])[0], top_k=1)
            assert len(results) == 1
            assert "snippet" in results[0]
            assert isinstance(results[0]["snippet"], str)