"""Pydantic request and response schemas for the REST API.

The API contract lives here; FastAPI generates OpenAPI from these models.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------------------


class SourceRegisterRequest(BaseModel):
    source_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")]
    source_type: Annotated[str, Field(min_length=1)]
    config: dict = Field(default_factory=dict)


class SourceResponse(BaseModel):
    id: str
    type: str
    config: str  # JSON string
    last_synced_at: str | None
    status: str  # idle | syncing | error


# ------------------------------------------------------------------------------
# Search
# ------------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=2000)]
    top_k: int = Field(default=5, ge=1, le=100)
    source_ids: list[str] | None = None


class SearchResult(BaseModel):
    document_id: str
    title: str
    path: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    source_id: str


class SearchResponse(BaseModel):
    results: list[SearchResult]


# ------------------------------------------------------------------------------
# Status
# ------------------------------------------------------------------------------


class StatusResponse(BaseModel):
    status: str = "healthy"
    index_size: int  # number of chunks indexed
    sources: list[str]