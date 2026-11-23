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

*Serving live on that URL since 2026-10-30 — since 2026-11-04 via the docker compose stack
(engine on 127.0.0.1:8420; the native systemd user service was disabled after the reboot
race). `/mcp` is bearer-gated (`Authorization: Bearer $SEEKER_API_TOKEN`). The MCP-over-HTTP
transport bugs — double-prefixed mount path, session-manager lifespan — were fixed 2026-10-29, see
handover `01`.* After deployment (Phase 2), repoint `url` from `localhost` to the Tailscale
address and add the bearer header. *Phase 2 caveat (2026-10-30) superseded 2026-11-12:
`SEEKER_MCP_ALLOWED_HOSTS` (config.py, wired through docker-compose.yml) adds Host patterns
beyond loopback, and the sidecar enables `tailscale serve` 443→8420 — e.g.
`SEEKER_MCP_ALLOWED_HOSTS=search-engine-2.taile24e8b.ts.net:*`.*