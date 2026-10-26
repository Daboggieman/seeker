"""Index pipeline: connector → extract → hash gate → chunk → embed → store.

Contract (docs/build_docs/04-core-engine-specs.md, docs/handover_docs/02-engine-conventions.md):
- the index pipeline is one direction: connectors → chunk → embed → store;
  nothing else writes to the vector store;
- `content_hash` (sha256 of fetched bytes) is checked before embedding —
  re-embedding an unchanged file is a bug, not an optimisation. Chunks whose
  stored model differs from the current backend are re-embedded even when the
  hash is unchanged (a model switch makes every vector stale);
- `embedding_model` on every chunk is the backend's `model_name`, so the
  same-model rule is checkable in the store;
- a full sync (since=None) prunes stored documents of the source that the
  walk no longer finds — a full walk is the authoritative snapshot.

Per-item failures never abort a sync: one unreadable file costs one entry in
`SyncStats.failed`, never the rest of the source.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from seeker.chunking.chunker import Chunk, chunk_text
from seeker.connectors.base import RawItem, SourceConnector
from seeker.embeddings.base import EmbeddingBackend
from seeker.pipeline.extract import ExtractedSegment, extract_segments
from seeker.store.records import DocumentRecord, StoredChunk
from seeker.store.store import VectorStore

_DEFAULT_BATCH_SIZE = 32  # chunks per embed request (spec §5.3 suggests 32)


@dataclass(frozen=True)
class SyncStats:
    indexed: int = 0
    skipped_unchanged: int = 0
    unsupported: int = 0
    pruned: int = 0
    failed: list[str] = field(default_factory=list)


class IndexPipeline:
    """Turns connector items into chunked, embedded, stored documents."""

    def __init__(
        self,
        store: VectorStore,
        embedding_backend: EmbeddingBackend,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self.store = store
        self.backend = embedding_backend
        self.batch_size = batch_size

    async def sync(
        self,
        connector: SourceConnector,
        *,
        source_id: str,
        since: str | None = None,
    ) -> SyncStats:
        """Sync one source: index changed items; prune vanished ones on full syncs.

        `since=None` is the initial full walk — its listing is an authoritative
        snapshot, so documents of this source absent from it are deleted.
        Incremental syncs (since set) never prune.
        """
        items = connector.list_changed_items(since)
        indexed = skipped_unchanged = unsupported = 0
        failed: list[str] = []
        for item in items:
            try:
                outcome = await self._index_item(connector, item, source_id)
            except Exception:  # noqa: BLE001 — one bad file must not stop the sync
                failed.append(item.path)
                continue
            if outcome == "indexed":
                indexed += 1
            elif outcome == "unchanged":
                skipped_unchanged += 1
            else:
                unsupported += 1
        pruned = self._prune_missing(items, source_id) if since is None else 0
        return SyncStats(
            indexed=indexed,
            skipped_unchanged=skipped_unchanged,
            unsupported=unsupported,
            pruned=pruned,
            failed=failed,
        )

    async def _index_item(
        self, connector: SourceConnector, item: RawItem, source_id: str
    ) -> str:  # "indexed" | "unchanged" | "unsupported"
        fetched = connector.fetch_content(item)
        content_hash = hashlib.sha256(fetched.content).hexdigest()
        existing = self.store.get_document_by_path(item.path)
        if (
            existing is not None
            and existing.content_hash == content_hash
            and self.store.chunk_models(existing.id) == {self.backend.model_name}
        ):
            return "unchanged"

        segments = extract_segments(fetched.content, fetched.mime_type)
        if segments is None:
            return "unsupported"

        document_id = existing.id if existing else uuid.uuid4().hex
        chunks = self._make_chunks(document_id, segments)
        vectors = await self._embed_chunk_texts([chunk.text for chunk in chunks])
        stored = [
            StoredChunk(
                id=chunk.id,
                document_id=document_id,
                text=chunk.text,
                position=position,
                page=chunk.page,
                embedding_model=self.backend.model_name,
                vector=vector,
            )
            for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        self.store.upsert_document(
            DocumentRecord(
                id=document_id,
                source_id=source_id,
                path=item.path,
                title=Path(item.path).stem,
                mime_type=fetched.mime_type,
                modified_at=item.modified_at,
                indexed_at=_utcnow(),
                content_hash=content_hash,
            )
        )
        self.store.replace_chunks(document_id, stored)
        return "indexed"

    def _make_chunks(
        self, document_id: str, segments: list[ExtractedSegment]
    ) -> list[Chunk]:
        """Chunk every segment, renumbering positions across the document."""
        chunks: list[Chunk] = []
        for segment in segments:
            for chunk in chunk_text(segment.text, document_id, page=segment.page):
                chunks.append(chunk)
        return chunks

    async def _embed_chunk_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(await self.backend.embed_documents(batch))
        return vectors

    def _prune_missing(self, items: list[RawItem], source_id: str) -> int:
        """Delete stored documents of `source_id` not in a full-walk snapshot."""
        listed = {item.path for item in items}
        stored = self.store.document_paths_for_source(source_id)
        pruned = 0
        for path, document_id in stored.items():
            if path not in listed:
                self.store.delete_document(document_id)
                pruned += 1
        return pruned


def _utcnow() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
