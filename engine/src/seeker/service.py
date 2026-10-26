"""The engine service: one implementation behind both surfaces.

Conventions (docs/handover_docs/02-engine-conventions.md): the engine exposes
REST (`/v1/...`) and the MCP layer proxies it — there is no second
implementation of search or indexing anywhere. This module is that single
implementation; the REST routes and the MCP tools are both thin wrappers over
`Engine` methods, each returning its own protocol's shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

from seeker.connectors.filesystem import FilesystemConnector
from seeker.pipeline.indexer import SyncStats
from seeker.store.records import SourceRecord
from seeker.store.store import VectorStore


class SourceNotFoundError(Exception):
    pass


def sync_stats_to_dict(stats: SyncStats) -> dict:
    return {
        "indexed": stats.indexed,
        "skipped_unchanged": stats.skipped_unchanged,
        "unsupported": stats.unsupported,
        "pruned": stats.pruned,
        "failed": stats.failed,
    }


class Engine:
    """Search, source management, and sync — the one engine implementation."""

    def __init__(self, store: VectorStore, embedding_backend, pipeline) -> None:
        self.store = store
        self.backend = embedding_backend
        self.pipeline = pipeline

    # -- search --------------------------------------------------------------

    async def search(
        self, query: str, *, top_k: int, source_ids: list[str] | None = None
    ) -> list[dict]:
        """Embed the query with the indexing model and run KNN.

        Results carry cosine similarity as the score (higher is better — the
        REST contract's shape) plus the metadata the data model requires:
        chunk location, path, and source. Snippets are the chunk text's head.
        """
        if not query.strip():
            raise ValueError("query must not be empty")
        query_vector = await self.backend.embed_query(query)
        hits = self.store.search(
            query_vector,
            model_name=self.backend.model_name,
            top_k=top_k,
            source_ids=source_ids,
        )
        return [
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "title": hit.title,
                "path": hit.path,
                "snippet": _snippet(hit.text),
                "score": _similarity(hit.score),
                "source_id": hit.source_id,
                "page": hit.page,
                "position": hit.position,
            }
            for hit in hits
        ]

    # -- sources -------------------------------------------------------------

    def add_source(self, source_id: str, root_path: str) -> SourceRecord:
        """Register a filesystem source; validates the root exists."""
        connector = FilesystemConnector(root_path)  # raises NotADirectoryError
        record = SourceRecord(
            id=source_id,
            type="filesystem",
            root_path=str(connector.root),
            last_synced_at=None,
            status="idle",
        )
        self.store.upsert_source(record)
        return record

    def list_sources(self) -> list[SourceRecord]:
        return self.store.list_sources()

    def get_source(self, source_id: str) -> SourceRecord:
        source = self.store.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    def delete_source(self, source_id: str) -> None:
        if self.store.get_source(source_id) is None:
            raise SourceNotFoundError(source_id)
        self.store.delete_source(source_id)

    def connector_for(self, source: SourceRecord) -> FilesystemConnector:
        if source.type != "filesystem":
            raise ValueError(f"unsupported source type: {source.type!r}")
        return FilesystemConnector(source.root_path)

    async def sync_source(self, source_id: str) -> dict:
        """Run a full sync for one registered source; updates its status row."""
        source = self.get_source(source_id)
        self.store.upsert_source(
            SourceRecord(
                id=source.id,
                type=source.type,
                root_path=source.root_path,
                last_synced_at=source.last_synced_at,
                status="syncing",
            )
        )
        connector = self.connector_for(source)
        try:
            stats = await self.pipeline.sync(connector, source_id=source.id)
        except Exception:
            self.store.upsert_source(
                SourceRecord(
                    id=source.id,
                    type=source.type,
                    root_path=source.root_path,
                    last_synced_at=source.last_synced_at,
                    status="error",
                )
            )
            raise
        self.store.upsert_source(
            SourceRecord(
                id=source.id,
                type=source.type,
                root_path=source.root_path,
                last_synced_at=_utcnow(),
                status="idle",
            )
        )
        return sync_stats_to_dict(stats)

    def status(self) -> dict:
        return {
            "status": "ok",
            "embedding_model": self.backend.model_name,
            "dimensions": self.backend.dimensions,
            **self.store.counts(),
            "sources": [
                {
                    "id": s.id,
                    "type": s.type,
                    "root_path": s.root_path,
                    "last_synced_at": s.last_synced_at,
                    "status": s.status,
                }
                for s in self.store.list_sources()
            ],
        }


def _snippet(text: str, limit: int = 240) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _similarity(distance: float) -> float:
    """sqlite-vec L2 distance → cosine similarity (unit vectors), clamped."""
    return round(max(-1.0, min(1.0, 1.0 - distance * distance / 2.0)), 4)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
