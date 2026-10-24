"""The indexing pipeline: connector → chunker → embedder → store.

Wires together the components built in isolation so far.  The pipeline is
called by the sync route and can also run as a background task (watchdog-driven
live sync is a Phase 1 stretch goal; initial sync is an explicit call).
"""

from __future__ import annotations

from pathlib import Path

from seeker.chunking.chunker import chunk_text
from seeker.connectors.base import Connector, RawItem
from seeker.embeddings.backends import EmbeddingBackend, MockEmbeddingBackend
from seeker.store.index import IndexStore


class IndexPipeline:
    """One-shot index pipeline for a single source."""

    def __init__(
        self,
        connector: Connector,
        store: IndexStore,
        backend: EmbeddingBackend | None = None,
    ) -> None:
        self._connector = connector
        self._store = store
        self._backend = backend or MockEmbeddingBackend()

    def run(self) -> int:
        """Index all changed items from the connector.

        Returns the number of chunks added.
        """
        source_id = self._connector.source_id
        self._store.update_sync_status(source_id, "syncing")
        try:
            items = self._connector.list_changed_items(since=None)
            chunk_count = 0
            for raw in items:
                doc_id, created = self._upsert_document(raw)
                if not created:
                    # Unchanged — content_hash matches; nothing to do.
                    continue
                self._index_document(doc_id, raw)
                chunk_count += 1
            self._store.update_sync_status(source_id, "idle")
            return chunk_count
        except Exception:
            self._store.update_sync_status(source_id, "error")
            raise

    def _upsert_document(
        self, raw: RawItem
    ) -> tuple[str, bool]:
        """Upsert the document row.  Returns (doc_id, was_created)."""
        data, mime = self._connector.fetch_content(raw)
        doc_id = raw.path or f"doc-{raw.modified_at.timestamp()}"
        # Fast-stable doc id from path + source
        doc_id = f"{self._connector.source_id}:{raw.path}"
        existing = self._store.find_document_by_hash(
            self._connector.source_id, raw.content_hash or ""
        )
        if existing:
            return existing, False
        self._store.upsert_document(
            doc_id=doc_id,
            source_id=self._connector.source_id,
            path=raw.path,
            title=Path(raw.path).name,
            mime_type=mime,
            modified_at=raw.modified_at.isoformat(),
            content_hash=raw.content_hash or "",
        )
        return doc_id, True

    def _index_document(self, doc_id: str, raw: RawItem) -> None:
        """Chunk the document body and write to the store."""
        data, _mime = self._connector.fetch_content(raw)
        text = data.decode("utf-8", errors="replace")
        chunks = chunk_text(
            text,
            document_id=doc_id,
            page=None,  # filesystem connector doesn't track pages
        )
        if not chunks:
            return
        vectors = self._backend.embed([c.text for c in chunks])
        self._store.upsert_chunks(
            chunks,
            vectors=vectors,
            embedding_model=self._backend.model_name,
        )