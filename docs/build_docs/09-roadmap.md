# Seeker — Build Roadmap

Source of record: spec §12 (Milestones). Recommended build order: core engine → MCP wrapper →
self-hosted deployment → mobile → browser extension → Office add-in → OS-native hooks.

**Start of every phase: verification step.** Confirm what is already done and only implement
what is missing. Never assume a prior phase is complete because it was planned.

> **2026-10-24:** Phase 1 code is complete (61 tests green). See
> [`../handover_docs/01-current-state.md`](../handover_docs/01-current-state.md) for the
> full component inventory. The exit criterion (recall@5 on real files via MCP) is still
> pending — it requires the real embedding backend (open decision 9) and a real indexed
> directory (open decision 10).

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Core engine + MCP server | You can ask Claude Desktop a vague question and get the right file back |
| 2 | Self-hosted deployment | Same query works from a second device on your Tailnet |
| 3 | Mobile client | Search works from your phone off wifi (via Tailscale) |
| 4 | Browser extension | Search overlay works inside Google Docs |
| 5 | Office add-in | Search task pane works inside Word |
| 6 | (Optional) OS-native hooks | Spotlight/Windows Search returns your indexed content |

## Phase detail

### Phase 1 — Core engine + MCP server

Deliver: FastAPI engine (connectors → index pipeline → query API), sqlite-vec store, Ollama
embedding, filesystem connector, MCP server shim. Validate over MCP before building anything
else.

**Exit:** a vague natural-language query against real personal files returns the right document
in Claude Desktop, on the eval set, with recall@5 recorded.

### Phase 2 — Self-hosted deployment

Deliver: Docker Compose, Tailscale sidecar, bearer-token auth, backup story for `./data/`.

**Exit:** the same query works from a second device on the Tailnet.

### Phase 3 — Mobile client

Deliver: Expo app — search bar, results list, source filter. Direct `POST /v1/search` over the
Tailnet.

**Exit:** search works from your phone off wifi.

### Phase 4 — Browser extension

Deliver: Manifest V3 extension — content-script overlay (keyboard shortcut), service worker
calling the REST API.

**Exit:** the search overlay works inside Google Docs.

### Phase 5 — Office add-in

Deliver: Office.js task pane, one codebase across Word/Excel/PowerPoint.

**Exit:** search task pane works inside Word.

### Phase 6 (optional) — OS-native hooks

Deliver: Spotlight importer / Windows Search indexer plugin. Only if a dedicated search surface
still feels necessary once the above are in daily use.

## Current status

Planning phase. Phase 1 not started. The running record of where the build actually is lives in
[`../handover_docs/01-current-state.md`](../handover_docs/01-current-state.md) — this roadmap
holds the plan, never the status.