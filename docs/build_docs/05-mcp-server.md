# Seeker — MCP Server

Source of record: spec §7 (MCP Server Spec).

Wrap the REST API as MCP tools so Claude Desktop and VS Code become working clients
immediately, with no custom UI. This is Phase 1's validation surface — retrieval quality gets
proved here before any client UI is built.

## Tool definitions

```json
{
  "tools": [
    {
      "name": "search_documents",
      "description": "Semantic search across all indexed personal documents",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" },
          "top_k": { "type": "integer", "default": 5 },
          "source_ids": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["query"]
      }
    },
    {
      "name": "list_sources",
      "description": "List registered document sources and their sync status",
      "inputSchema": { "type": "object", "properties": {} }
    },
    {
      "name": "reindex_source",
      "description": "Trigger a manual re-sync of a specific source",
      "inputSchema": {
        "type": "object",
        "properties": { "source_id": { "type": "string" } },
        "required": ["source_id"]
      }
    }
  ]
}
```

## Wrapping strategy

Each tool call internally proxies to the matching REST endpoint — the MCP layer is a
translation shim, **not** a second implementation.

*Implemented 2026-10-26: the tools call the same `Engine` methods the REST routes call,
rather than proxying over HTTP — the invariant ("no second implementation") is what binds;
see the departure record in handover `02`. Tool shapes are unchanged from the table below.*

| MCP tool | Engine method (same one the REST route calls) |
|---|---|
| `search_documents` | `Engine.search` (`POST /v1/search`) |
| `list_sources` | `Engine.list_sources` (`GET /v1/sources`) |
| `reindex_source` | `Engine.sync_source` (`POST /v1/sources/{id}/sync`) |

## Client registration

Register the server in each app's MCP config, pointing at the local (pre-deployment) instance:

```json
{
  "mcpServers": {
    "personal-search": {
      "url": "http://localhost:8420/mcp"
    }
  }
}
```

*Serving live on that URL since 2026-10-30 (systemd user service; the MCP-over-HTTP transport
bugs — double-prefixed mount path, session-manager lifespan — were fixed 2026-10-29, see
handover `01`).* After deployment (Phase 2), repoint `url` from `localhost` to the Tailscale
address — no other change needed. *Phase 2 caveat: the SDK's Host-header protection allows
only localhost hosts; see the Phase 2 note in handover `01` (2026-10-30 entry).*