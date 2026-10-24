# Seeker — Client Adapters

Source of record: spec §9 (Client Adapters by build phase). Every client is a thin shell
around the same REST/MCP surface — the engine never knows which adapter is calling.

## Phase 1 — MCP clients (Claude Desktop, VS Code)

Register the server in each app's MCP config, pointing at the local instance
([`05-mcp-server.md`](05-mcp-server.md)). Use this phase to **validate retrieval quality on
real queries** before building anything else. No client code is written in this phase — only
config.

## Phase 2 — Self-hosted deployment

Move the container to always-on infrastructure ([`06-deployment.md`](06-deployment.md)). No
client code changes — repoint the URL from `localhost` to the Tailscale address.

## Phase 3 — Expo mobile app

Screens: search bar, results list (title, snippet, source), source filter toggle. Calls
`POST /v1/search` directly over the Tailnet — no MCP on mobile.

## Phase 4 — Browser extension (Manifest V3)

Content script injects a search overlay (triggered by a keyboard shortcut); background service
worker calls the REST API. Covers Google Docs and any browser-based PDF viewer without
per-site integration.

## Phase 5 — Office add-in

Office.js task pane, one codebase shared across Word/Excel/PowerPoint, calling the same REST
API.

## Phase 6 (optional, later) — OS-native search hooks

macOS Spotlight importer / Windows Search indexer plugin, only if a dedicated search surface
still feels necessary once the above are in daily use.