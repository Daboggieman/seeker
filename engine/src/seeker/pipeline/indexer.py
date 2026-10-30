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

Per-item failures never abort a sync: one unreadable file costs one structured
entry in `SyncStats.failed` (path, error, best-effort reason, suggested check),
never the rest of the source — and the full traceback lands in the engine log.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from seeker.chunking.chunker import Chunk, chunk_text
from seeker.connectors.base import RawItem, SourceConnector
from seeker.embeddings.base import EmbeddingBackend
from seeker.pipeline.extract import ExtractedSegment, extract_segments
from seeker.store.records import DocumentRecord, StoredChunk
from seeker.store.store import VectorStore

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 32  # chunks per embed request (spec §5.3 suggests 32)


@dataclass(frozen=True)
class SyncFailure:
    """One file that failed during sync, with its diagnosis.

    `reason` is best-effort — derived from the exception where it is
    recognizable, honest "unexpected error" where it is not. `suggestion` is
    the first thing to check. The traceback itself lives in the engine log.
    """

    path: str
    error: str
    reason: str
    suggestion: str


@dataclass(frozen=True)
class SyncStats:
    indexed: int = 0
    skipped_unchanged: int = 0
    unsupported: int = 0
    pruned: int = 0
    failed: list[SyncFailure] = field(default_factory=list)


def _classify_failure(exc: BaseException) -> tuple[str, str]:
    """Best-effort (reason, suggestion) for a failed file — never a diagnosis.

    Recognizes only what can be recognized honestly (endpoint down, model
    missing, auth rejected, undecodable text, unreadable file); anything else
    falls back to generic guidance with the traceback in the engine log.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return (
                "embedding endpoint rejected the credentials",
                "check SEEKER_EMBEDDING_API_KEY against the endpoint",
            )
        if status == 404:
            return (
                "embedding model not found on the endpoint",
                "pull or correct SEEKER_EMBEDDING_MODEL (e.g. `ollama pull nomic-embed-text`)",
            )
        return (f"embedding endpoint returned HTTP {status}", "check the endpoint's logs")
    if isinstance(exc, httpx.TimeoutException):
        return ("embedding request timed out", "check runtime load; smaller batches may help")
    if isinstance(exc, (httpx.TransportError, ConnectionError)):
        return (
            "embedding endpoint unreachable",
            "confirm the runtime is up (e.g. `ollama serve`) and "
            "SEEKER_EMBEDDING_BASE_URL points at it",
        )
    if isinstance(exc, UnicodeDecodeError):
        return (
            "file is not decodable as its declared text mime type",
            "exclude it from the source or teach extraction its real encoding",
        )
    if type(exc).__name__ == "FileDataError" and "pymupdf" in type(exc).__module__:
        return (
            "PDF could not be parsed (corrupt or image-only)",
            "OCR for scanned PDFs is a later phase; otherwise check the file",
        )
    if isinstance(exc, OSError):
        return ("file could not be read", "check that it still exists and is readable")
    return ("unexpected error", "see the engine log for the full traceback")


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
        failed: list[SyncFailure] = []
        for item in items:
            try:
                outcome = await self._index_item(connector, item, source_id)
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the sync
                reason, suggestion = _classify_failure(exc)
                logger.exception("index failed for %s (%s)", item.path, reason)
                failed.append(
                    SyncFailure(
                        path=item.path,
                        error=f"{type(exc).__name__}: {exc}",
                        reason=reason,
                        suggestion=suggestion,
                    )
                )
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
