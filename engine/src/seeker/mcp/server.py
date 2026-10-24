"""MCP server shim.

Wraps the REST API as MCP tools (docs/build_docs/05-mcp-server.md).  The MCP
layer is a translation shim, NOT a second implementation — each tool calls the
same router function the REST route calls.

Tools (spec section 7):
- search_documents  -> POST /v1/search
- list_sources      -> GET  /v1/sources
- reindex_source    -> POST /v1/sources/{id}/sync
"""

from __future__ import annotations

import json
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server

from seeker.api.routes import list_sources, search, sync_source
from seeker.api.schemas import SearchRequest


def build_mcp_server() -> Server:
    """Create the MCP server exposing Seeker's three tools."""
    app = Server("personal-search")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_documents",
                description="Semantic search across all indexed personal documents",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="list_sources",
                description="List registered document sources and their sync status",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="reindex_source",
                description="Trigger a manual re-sync of a specific source",
                inputSchema={
                    "type": "object",
                    "properties": {"source_id": {"type": "string"}},
                    "required": ["source_id"],
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.Content]:
        if name == "search_documents":
            resp = search(SearchRequest(**arguments))
            body = {"results": [r.model_dump() for r in resp.results]}
        elif name == "list_sources":
            body = {"sources": [s.model_dump() for s in list_sources()]}
        elif name == "reindex_source":
            body = sync_source(arguments["source_id"])
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [types.TextContent(type="text", text=json.dumps(body))]

    return app


def run_mcp() -> None:
    """Run the MCP server over stdio."""
    import anyio
    from mcp.server.stdio import stdio_server

    server = build_mcp_server()

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run)


if __name__ == "__main__":
    run_mcp()
