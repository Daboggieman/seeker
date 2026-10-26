"""Unit tests for the index pipeline.

Runs connector → extract → hash gate → chunk → embed → store end to end
against a scripted connector and the real sqlite-vec store (tmp file), with
the mock embedding backend. No network.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from seeker.connectors.base import FetchedContent, RawItem
from seeker.embeddings.mock import MockEmbeddingBackend
from seeker.pipeline.indexer import IndexPipeline
from seeker.store.store import VectorStore

MODEL = "mock"


def run(coro):
    return asyncio.run(coro)


@dataclass
class FakeConnector:
    """Scripted in-memory connector: path -> (bytes, mime)."""

    files: dict[str, tuple[bytes, str]]
    fail_on: set[str] = field(default_factory=set)

    def list_changed_items(self, since: str | None) -> list[RawItem]:
        return [
            RawItem(path=path, modified_at="2026-10-26T00:00:00Z", size=len(data))
            for path, (data, _mime) in sorted(self.files.items())
        ]

    def fetch_content(self, item: RawItem) -> FetchedContent:
        if item.path in self.fail_on:
            raise OSError("simulated read failure")
        data, mime = self.files[item.path]
        return FetchedContent(content=data, mime_type=mime)


@pytest.fixture
def store(tmp_path):
    return VectorStore(tmp_path / "pipe.db", dimensions=8)


def make_pipeline(store: VectorStore) -> IndexPipeline:
    return IndexPipeline(store, MockEmbeddingBackend(dimensions=8))


def search(store: VectorStore, query: str, top_k: int = 5):
    return store.search(
        run(MockEmbeddingBackend(dimensions=8).embed_query(query)),
        model_name=MODEL,
        top_k=top_k,
    )


class TestFirstSync:
    def test_indexes_text_files(self, store: VectorStore) -> None:
        connector = FakeConnector(
            {
                "/docs/budget.txt": (b"Q1 budget was disputed", "text/plain"),
                "/docs/recipes.txt": (b"sourdough needs flour and time", "text/plain"),
            }
        )
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.indexed == 2
        assert stats.failed == []
        hits = search(store, "Q1 budget")
        assert hits
        assert all(hit.source_id == "fs-home" for hit in hits)

    def test_stores_document_metadata(self, store: VectorStore) -> None:
        connector = FakeConnector({"/docs/notes.md": (b"# heading\nbody", "text/markdown")})
        run(make_pipeline(store).sync(connector, source_id="fs-home"))
        doc = store.get_document_by_path("/docs/notes.md")
        assert doc is not None
        assert doc.title == "notes"
        assert doc.mime_type == "text/markdown"
        assert doc.source_id == "fs-home"
        assert len(doc.content_hash) == 64

    def test_unsupported_mime_is_skipped(self, store: VectorStore) -> None:
        connector = FakeConnector(
            {"/docs/blob.xyzzy": (b"\x00\x01binary", "application/octet-stream")}
        )
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.unsupported == 1
        assert store.get_document_by_path("/docs/blob.xyzzy") is None

    def test_empty_text_file_indexes_zero_chunks(self, store: VectorStore) -> None:
        connector = FakeConnector({"/docs/empty.txt": (b"", "text/plain")})
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.indexed == 1
        assert list(store.document_paths_for_source("fs-home")) == ["/docs/empty.txt"]
        doc_id = store.document_paths_for_source("fs-home")["/docs/empty.txt"]
        assert store.chunk_models(doc_id) == set()  # zero chunks

    def test_failed_file_does_not_abort_sync(self, store: VectorStore) -> None:
        connector = FakeConnector(
            {
                "/docs/good.txt": (b"fine content here", "text/plain"),
                "/docs/broken.txt": (b"never read", "text/plain"),
            },
            fail_on={"/docs/broken.txt"},
        )
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.indexed == 1
        assert stats.failed == ["/docs/broken.txt"]


class TestHashGate:
    def test_second_sync_skips_unchanged(self, store: VectorStore) -> None:
        connector = FakeConnector({"/docs/a.txt": (b"same bytes", "text/plain")})
        pipeline = make_pipeline(store)
        run(pipeline.sync(connector, source_id="fs-home"))
        stats = run(pipeline.sync(connector, source_id="fs-home"))
        assert stats.indexed == 0
        assert stats.skipped_unchanged == 1

    def test_modified_file_is_reindexed(self, store: VectorStore) -> None:
        connector = FakeConnector({"/docs/f.txt": (b"version one", "text/plain")})
        pipeline = make_pipeline(store)
        run(pipeline.sync(connector, source_id="fs-home"))
        connector.files["/docs/f.txt"] = (b"version two", "text/plain")
        stats = run(pipeline.sync(connector, source_id="fs-home"))
        assert stats.indexed == 1
        hits = search(store, "version two")
        assert any("version two" in hit.text for hit in hits)

    def test_same_hash_but_other_model_is_reembedded(self, store: VectorStore) -> None:
        # Same content, but the stored chunks carry another model's name:
        # the model switch makes every vector stale regardless of the hash.
        connector = FakeConnector({"/docs/f.txt": (b"stable content", "text/plain")})
        run(make_pipeline(store).sync(connector, source_id="fs-home"))
        doc = store.get_document_by_path("/docs/f.txt")
        assert doc is not None
        store._conn.execute(
            "UPDATE chunks SET embedding_model = 'nomic-embed-text' WHERE document_id = ?",
            (doc.id,),
        )
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.indexed == 1
        assert store.chunk_models(doc.id) == {MODEL}


class TestPruning:
    def test_full_sync_prunes_vanished_documents(self, store: VectorStore) -> None:
        connector = FakeConnector(
            {
                "/docs/stay.txt": (b"stays put", "text/plain"),
                "/docs/gone.txt": (b"disappears", "text/plain"),
            }
        )
        pipeline = make_pipeline(store)
        run(pipeline.sync(connector, source_id="fs-home"))
        connector.files.pop("/docs/gone.txt")
        stats = run(pipeline.sync(connector, source_id="fs-home"))
        assert stats.pruned == 1
        assert store.get_document_by_path("/docs/gone.txt") is None
        assert store.get_document_by_path("/docs/stay.txt") is not None

    def test_incremental_sync_never_prunes(self, store: VectorStore) -> None:
        connector = FakeConnector({"/docs/a.txt": (b"one", "text/plain")})
        pipeline = make_pipeline(store)
        run(pipeline.sync(connector, source_id="fs-home"))
        stats = run(
            pipeline.sync(connector, source_id="fs-home", since="2026-10-25T00:00:00Z")
        )
        assert stats.pruned == 0


class TestPdfPages:
    def test_page_numbers_survive_the_pipeline(self, store: VectorStore) -> None:
        pdf_bytes = make_two_page_pdf("first page content", "second page content")
        connector = FakeConnector({"/docs/book.pdf": (pdf_bytes, "application/pdf")})
        stats = run(make_pipeline(store).sync(connector, source_id="fs-home"))
        assert stats.indexed == 1
        rows = store._conn.execute(
            "SELECT page, position FROM chunks ORDER BY position"
        ).fetchall()
        assert [row["page"] for row in rows] == [1, 2]


def make_two_page_pdf(page1: str, page2: str) -> bytes:
    """Build a minimal two-page text PDF with PyMuPDF."""
    import pymupdf

    doc = pymupdf.open()
    for text in (page1, page2):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data
