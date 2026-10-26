"""MCP shim tests: each tool proxies to the same Engine methods the REST routes
call and returns the REST response shape (docs/build_docs/05-mcp-server.md,
docs/build_docs/08-testing-and-validation.md). Tools run through
MCPServer.call_tool directly — no HTTP — because the shim has no logic of its
own to test beyond the proxy contract."""

from __future__ import annotations

import asyncio
import json

import pytest

from seeker.embeddings.mock import MockEmbeddingBackend
from seeker.mcp.server import build_mcp_server
from seeker.pipeline.indexer import IndexPipeline
from seeker.service import Engine, SourceNotFoundError
from seeker.store.store import VectorStore


def run(coro):
    return asyncio.run(coro)


def call(server, name: str, arguments: dict | None = None) -> dict:
    result = run(server.call_tool(name, arguments or {}))
    assert not result.is_error
    return json.loads(result.content[0].text)


def root_cause(exc: BaseException) -> BaseException:
    while exc.__cause__ is not None:
        exc = exc.__cause__
    return exc


def make_source_dir(tmp_path, name: str = "docs") -> str:
    docs = tmp_path / name
    docs.mkdir(exist_ok=True)
    (docs / "budget.txt").write_text("quarterly budget disagreement memo")
    (docs / "recipes.txt").write_text("sourdough needs flour and time")
    return str(docs)


@pytest.fixture
def engine(tmp_path) -> Engine:
    store = VectorStore(tmp_path / "mcp.db", dimensions=8)
    backend = MockEmbeddingBackend(dimensions=8)
    return Engine(store, backend, IndexPipeline(store, backend))


@pytest.fixture
def server(engine):
    return build_mcp_server(engine)


class TestToolRegistry:
    def test_exactly_the_three_translation_tools(self, server) -> None:
        assert {tool.name for tool in run(server.list_tools())} == {
            "search_documents",
            "list_sources",
            "reindex_source",
        }


class TestListSources:
    def test_empty_registry(self, server) -> None:
        assert call(server, "list_sources") == {"sources": []}

    def test_returns_rest_source_shape(self, engine, server, tmp_path) -> None:
        root = make_source_dir(tmp_path)
        engine.add_source("docs", root)
        body = call(server, "list_sources")
        assert body["sources"] == [
            {
                "id": "docs",
                "type": "filesystem",
                "root_path": root,
                "last_synced_at": None,
                "status": "idle",
            }
        ]


class TestSearchDocuments:
    def test_proxies_to_engine_and_returns_rest_shape(self, engine, server, tmp_path) -> None:
        engine.add_source("docs", make_source_dir(tmp_path))
        run(engine.sync_source("docs"))
        body = call(server, "search_documents", {"query": "quarterly budget disagreement memo"})
        assert body["results"], "indexed documents must be findable through the shim"
        top = body["results"][0]
        assert top["path"].endswith("budget.txt")
        assert set(top) == {
            "chunk_id",
            "document_id",
            "title",
            "path",
            "snippet",
            "score",
            "source_id",
            "page",
            "position",
        }

    def test_source_filter_and_top_k_pass_through(self, engine, server, tmp_path) -> None:
        for name in ("work", "home"):
            docs = tmp_path / name
            docs.mkdir(exist_ok=True)
            (docs / "note.txt").write_text(f"shared vocabulary marker {name}")
        engine.add_source("work", str(tmp_path / "work"))
        engine.add_source("home", str(tmp_path / "home"))
        for name in ("work", "home"):
            run(engine.sync_source(name))
        body = call(
            server,
            "search_documents",
            {"query": "shared vocabulary marker", "top_k": 2, "source_ids": ["home"]},
        )
        assert body["results"]
        assert {r["source_id"] for r in body["results"]} == {"home"}

    def test_empty_query_surfaces_engine_error(self, server) -> None:
        with pytest.raises(Exception) as excinfo:
            call(server, "search_documents", {"query": "  "})
        assert isinstance(root_cause(excinfo.value), ValueError)

    def test_reindex_unknown_source_surfaces_source_not_found(self, server) -> None:
        with pytest.raises(Exception) as excinfo:
            call(server, "reindex_source", {"source_id": "nope"})
        assert isinstance(root_cause(excinfo.value), SourceNotFoundError)
