"""MCP translation shim.

Contract (docs/build_docs/05-mcp-server.md, docs/handover_docs/02-engine-conventions.md):
the MCP layer is a translation shim, NOT a second implementation. These tools
call the same `Engine` methods the REST routes call — one implementation, two
protocol shapes. Client registration points Claude Desktop / VS Code at
`http://localhost:8420/mcp` (Tailscale address after Phase 2).
"""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer


def build_mcp_server(engine) -> MCPServer:
    server = MCPServer(
        "seeker",
        instructions="Semantic search over your personal documents.",
    )

    @server.tool()
    async def search_documents(
        query: str, top_k: int = 5, source_ids: list[str] | None = None
    ) -> str:
        """Semantic search across all indexed personal documents."""
        results = await engine.search(query, top_k=top_k, source_ids=source_ids)
        return json.dumps({"results": results})

    @server.tool()
    def list_sources() -> str:
        """List registered document sources and their sync status."""
        return json.dumps(
            {
                "sources": [
                    {
                        "id": s.id,
                        "type": s.type,
                        "root_path": s.root_path,
                        "last_synced_at": s.last_synced_at,
                        "status": s.status,
                    }
                    for s in engine.list_sources()
                ]
            }
        )

    @server.tool()
    async def reindex_source(source_id: str) -> str:
        """Trigger a manual re-sync of a specific source."""
        stats = await engine.sync_source(source_id)
        return json.dumps(stats)

    return server
