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
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from seeker.config import EngineSettings, load_settings
from seeker.factories import build_embedding_backend
from seeker.mcp.server import build_mcp_server
from seeker.pipeline.indexer import IndexPipeline
from seeker.service import Engine, SourceNotFoundError
from seeker.store.store import VectorStore

router = APIRouter(prefix="/v1")


# -- schemas ---------------------------------------------------------------


class SearchFilters(BaseModel):
    source_id: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: SearchFilters | None = None


class SourceCreateRequest(BaseModel):
    id: str
    root_path: str


class ErrorResponse(BaseModel):
    code: str
    message: str


# -- dependencies ----------------------------------------------------------


def require_auth(request: Request) -> None:
    """Bearer-token check on every client-engine call except health."""
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {request.app.state.settings.api_token}"
    if not secrets.compare_digest(auth, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "missing or invalid bearer token"},
        )


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


EngineDep = Annotated[Engine, Depends(require_auth_aware_engine)]


def require_auth_aware_engine(request: Request) -> Engine:
    return request.app.state.engine


def auth_dep(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {request.app.state.settings.api_token}"
    if not secrets.compare_digest(auth, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "missing or invalid bearer token"},
        )


def engine_dep(request: Request) -> Engine:
    return request.app.state.engine


EngDep = Annotated[Engine, Depends(engine_dep)]


# -- error mapping ---------------------------------------------------------


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# -- routes ----------------------------------------------------------------

router = APIRouter(prefix="/v1")


@router.post("/search", dependencies=[Depends(auth_dep)])
async def search(body: SearchRequest, engine: EngDep) -> dict[str, list[dict]]:
    try:
        results = await engine.search(
            body.query,
            top_k=body.top_k,
            source_ids=body.filters.source_id or None,
        )
    except ValueError as exc:
        raise _http_error(422, "VALIDATION_ERROR", str(exc)) from exc
    return {"results": results}


@router.get("/sources", dependencies=[Depends(auth_dep)])
def list_sources(engine: Annotated[Engine, Depends(engine_dep)]) -> list[dict]:
    return [_source_dict(s) for s in engine.list_sources()]


@router.post("/sources", status_code=201, dependencies=[Depends(auth_dep)])
def create_source(body: SourceCreateRequest, engine: EngDep) -> dict:
    try:
        record = engine.add_source(body.source_id, body.root_path)
    except NotADirectoryError:
        raise _http_error(
            422, "VALIDATION_ERROR", f"root_path is not a directory: {body.root_path}"
        )
    return _source_dict(record)


@router.post("/sources/{source_id}/sync", dependencies=[Depends(auth_dep)])
async def sync_source(source_id: str, engine: EngDep) -> dict:
    try:
        return await engine.sync_source(source_id)
    except SourceNotFoundError:
        raise _http_error(404, "SOURCE_NOT_FOUND", f"source {source_id!r} not found")


@router.delete("/sources/{source_id}", status_code=204, dependencies=[Depends(auth_dep)])
def delete_source(source_id: str, engine: EngDep) -> None:
    try:
        engine.delete_source(source_id)
    except SourceNotFoundError:
        raise _http_error(404, "SOURCE_NOT_FOUND", f"source {source_id!r} not found")


@router.get("/status", dependencies=[Depends(auth_dep)])
def status(engine: EngDep) -> dict:
    return engine.status()


@router.get("/health")
def health() -> dict[str, str]:
    """Anonymous liveness probe; the only anonymous route."""
    return {"status": "ok"}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchFilters(BaseModel):
    source_id: list[str] = Field(default_factory=list)


class SourceCreateRequest(BaseModel):
    source_id: str = Field(min_length=1)
    root_path: str = Field(min_length=1)


class SearchResponse(BaseModel):
    results: list[dict[str, Any]]


def _source_dict(source) -> dict:
    return {
        "id": source.id,
        "type": source.type,
        "root_path": source.root_path,
        "last_synced_at": source.last_synced_at,
        "status": source.status,
    }
