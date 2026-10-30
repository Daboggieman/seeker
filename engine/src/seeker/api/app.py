"""REST API surface — the engine's one client-facing surface.

Contract (docs/build_docs/03-api-design.md, docs/handover_docs/02-engine-conventions.md):
- one engine, one surface: every client adapter (MCP shim, mobile, extension)
  hangs off these routes; the MCP layer is a translation shim over the same
  `Engine` implementation, never a second one;
- bearer token on every client-engine call; no anonymous routes except health;
- errors are machine-readable: `{"code": ...}` in the body;
- every response carries `X-Request-Id` (echoed from the client when present);
- the FastAPI-generated OpenAPI document is the contract of record.
"""

from __future__ import annotations

import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from seeker.config import EngineSettings, load_settings
from seeker.factories import build_embedding_backend
from seeker.mcp.server import build_mcp_server
from seeker.pipeline.indexer import IndexPipeline
from seeker.service import Engine, SourceNotFoundError
from seeker.store.records import SourceRecord
from seeker.store.store import VectorStore

# -- request/response schemas -----------------------------------------------


class SearchFilters(BaseModel):
    source_id: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SourceCreateRequest(BaseModel):
    source_id: str = Field(min_length=1)
    root_path: str = Field(min_length=1)


# -- dependencies -----------------------------------------------------------


def engine_dep(request: Request) -> Engine:
    return request.app.state.engine


def auth_dep(request: Request) -> None:
    """Bearer-token check; constant-time compare."""
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {request.app.state.settings.api_token}"
    if not secrets.compare_digest(auth, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "missing or invalid bearer token"},
        )


EngDep = Annotated[Engine, Depends(engine_dep)]


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _source_dict(source: SourceRecord) -> dict[str, Any]:
    return {
        "id": source.id,
        "type": source.type,
        "root_path": source.root_path,
        "last_synced_at": source.last_synced_at,
        "status": source.status,
    }


# -- routes -----------------------------------------------------------------

router = APIRouter(prefix="/v1")


@router.post("/search", dependencies=[Depends(auth_dep)])
async def search(body: SearchRequest, engine: Annotated[Engine, Depends(engine_dep)]):
    try:
        results = await engine.search(
            body.query,
            top_k=body.top_k,
            source_ids=body.filters.source_id or None,
        )
    except ValueError as exc:
        raise _error(422, "VALIDATION_ERROR", str(exc)) from exc
    return {"results": results}


@router.get("/sources", dependencies=[Depends(auth_dep)])
def list_sources(engine: Annotated[Engine, Depends(engine_dep)]) -> list[dict[str, Any]]:
    return [_source_dict(s) for s in engine.list_sources()]


@router.post("/sources", status_code=201, dependencies=[Depends(auth_dep)])
def create_source(
    body: SourceCreateRequest, engine: Annotated[Engine, Depends(engine_dep)]
) -> dict[str, Any]:
    try:
        record = engine.add_source(body.source_id, body.root_path)
    except NotADirectoryError as exc:
        raise _error(
            422, "VALIDATION_ERROR", f"root_path is not a directory: {body.root_path}"
        ) from exc
    return _source_dict(record)


@router.post("/sources/{source_id}/sync", dependencies=[Depends(auth_dep)])
async def sync_source(
    source_id: str, engine: Annotated[Engine, Depends(engine_dep)]
) -> dict[str, Any]:
    try:
        return await engine.sync_source(source_id)
    except SourceNotFoundError as exc:
        raise _error(404, "SOURCE_NOT_FOUND", f"source {source_id!r} not found") from exc


@router.delete("/sources/{source_id}", status_code=204, dependencies=[Depends(auth_dep)])
def delete_source(source_id: str, engine: Annotated[Engine, Depends(engine_dep)]) -> None:
    try:
        engine.delete_source(source_id)
    except SourceNotFoundError as exc:
        raise _error(404, "SOURCE_NOT_FOUND", f"source {source_id!r} not found") from exc


@router.get("/status", dependencies=[Depends(auth_dep)])
def status(engine: Annotated[Engine, Depends(engine_dep)]) -> dict[str, Any]:
    return engine.status()


@router.get("/health")
def health() -> dict[str, str]:
    """Anonymous liveness probe; the only anonymous route."""
    return {"status": "ok"}


# -- app factory -------------------------------------------------------------


def create_app(settings: EngineSettings | None = None) -> FastAPI:
    """Build the engine app; defaults from `SEEKER_*` env vars."""
    settings = settings or load_settings()
    db = Path(settings.db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    store = VectorStore(db, dimensions=settings.embedding_dimensions)
    embedding_backend = build_embedding_backend(settings)
    engine = Engine(store, embedding_backend, IndexPipeline(store, embedding_backend))

    # MCP is a translation shim over the same Engine — mounted on this app,
    # never a second server implementation. The streamable app serves at its
    # own internal "/mcp" path, so it mounts at the root and POST /mcp reaches
    # it directly (mounting it under /mcp would double-prefix to /mcp/mcp).
    mcp_app = build_mcp_server(engine).streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # FastAPI does not run lifespans of mounted sub-apps; without this the
        # MCP session manager never starts and every /mcp call is a 500
        # ("Task group is not initialized").
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(title="Seeker Engine", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.store = store
    app.state.settings = settings

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    app.include_router(router)
    app.mount("/", mcp_app)
    return app
