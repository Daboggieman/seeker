"""FastAPI router for the /v1/ endpoints.

The chain is always router -> service (here) -> store.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status

from seeker.api.auth import require_auth
from seeker.api.schemas import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceRegisterRequest,
    SourceResponse,
    StatusResponse,
)
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceRegisterRequest,
    SourceResponse,
    StatusResponse,
)
from seeker.connectors.base import Connector
from seeker.connectors.filesystem import FilesystemConnector
from seeker.embeddings.backends import EmbeddingBackend, MockEmbeddingBackend
from seeker.query.pipeline import IndexPipeline
from seeker.store.index import IndexStore

router = APIRouter(prefix="/v1", tags=["v1"])

# Shared global instances (set on app startup).
_store: IndexStore | None = None
_backend: EmbeddingBackend | None = None
_CONNECTORS: dict[str, Connector] = {}


def init_api(store: IndexStore, backend: EmbeddingBackend | None = None) -> None:
    global _store, _backend
    _store = store
    _backend = backend or MockEmbeddingBackend()
    # Re-hydrate connectors from stored source configs.
    for src in _store.list_sources():
        _CONNECTORS[src["id"]] = _connector_from_config(src)


def _connector_from_config(src: dict) -> Connector:
    cfg = json.loads(src["config"]) if src["config"] != "{}" else {}
    if src["type"] == "filesystem":
        root = cfg.get("root_path", "/home")
        return FilesystemConnector(source_id=src["id"], root=root)
    raise ValueError(f"Unknown source type: {src['type']}")


def _store_or_404() -> IndexStore:
    if _store is None:
        raise RuntimeError("API not initialised")
    return _store


# ------------------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------------------


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def register_source(req: SourceRegisterRequest) -> SourceResponse:
    store = _store_or_404()
    store.register_source(req.source_id, req.source_type, req.config)
    # Instantiate and register the connector immediately so sync works.
    cfg = req.config or {}
    if req.source_type == "filesystem":
        root = cfg.get("root_path", "/home")
        _CONNECTORS[req.source_id] = FilesystemConnector(
            source_id=req.source_id, root=root
        )
    row = next(s for s in store.list_sources() if s["id"] == req.source_id)
    return SourceResponse(
        id=row["id"],
        type=row["type"],
        config=row["config"],
        last_synced_at=row["last_synced_at"],
        status=row["status"],
    )


@router.get("/sources")
def list_sources() -> list[SourceResponse]:
    store = _store_or_404()
    return [
        SourceResponse(
            id=s["id"], type=s["type"], config=s["config"],
            last_synced_at=s["last_synced_at"], status=s["status"],
        )
        for s in store.list_sources()
    ]


@router.post("/sources/{source_id}/sync")
def sync_source(source_id: str) -> dict:
    store = _store_or_404()
    sources = store.list_sources()
    if source_id not in {s["id"] for s in sources}:
        raise HTTPException(status_code=404, detail="SOURCE_NOT_FOUND")
    connector = _CONNECTORS.get(source_id)
    if connector is None:
        src = next(s for s in sources if s["id"] == source_id)
        connector = _connector_from_config(src)
        _CONNECTORS[source_id] = connector
    pipeline = IndexPipeline(connector, store, _backend)
    count = pipeline.run()
    return {"source_id": source_id, "chunks_indexed": count}


@router.delete("/sources/{source_id}")
def delete_source(source_id: str) -> dict:
    store = _store_or_404()
    sources = store.list_sources()
    if source_id not in {s["id"] for s in sources}:
        raise HTTPException(status_code=404, detail="SOURCE_NOT_FOUND")
    store.delete_source(source_id)
    _CONNECTORS.pop(source_id, None)
    return {"deleted": source_id}


# ------------------------------------------------------------------------------
# Search
# ------------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    store = _store_or_404()
    backend = _backend or MockEmbeddingBackend()
    query_vec = backend.embed([req.query])[0]
    raw_results = store.search(
        query_vec, top_k=req.top_k, source_ids=req.source_ids
    )
    return SearchResponse(
        results=[
            SearchResult(
                document_id=r["document_id"],
                title=r.get("title", ""),
                path=r.get("path", ""),
                snippet=r.get("snippet", ""),
                score=r["score"],
                source_id=r["source_id"],
            )
            for r in raw_results
        ]
    )


# ------------------------------------------------------------------------------
# Status
# ------------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    store = _store_or_404()
    return StatusResponse(
        status="healthy",
        index_size=0,  # TODO: store.chunk_count()
        sources=[s["id"] for s in store.list_sources()],
    )