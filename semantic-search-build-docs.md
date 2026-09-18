# Universal Semantic Search — Technical Build Docs

**Status:** Planning / pre-build
**Scope:** A self-hosted semantic search engine over personal files (filesystem, cloud docs, email, PDFs) with adapters for VS Code, mobile, browser, and Office — reachable from anywhere over a private network.

---

## 1. Overview & Goals

**Problem:** Keyword search across scattered personal files (local disk, Drive, PDFs, docs) fails when you don't remember exact filenames or terms. Retrieval should work off *meaning*, not string matching.

**Goals:**
- One engine, indexed once, queryable from any surface (desktop, mobile, VS Code, browser, Office, coding assistant, coding agents, IDEs).
- Fast to validate before investing in polished client UIs.

**Recommended build order:** core engine → MCP wrapper (validate quality) → self-hosted deployment → mobile → browser extension → Office add-in → (optional) OS-native search hooks.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CORE ENGINE                           │
│  (self-hosted, always-on — Docker container + Tailscale)     │
│                                                                │
│   ┌────────────┐    ┌───────────────┐    ┌────────────────┐  │
│   │ Connectors │───▶│ Index pipeline│───▶│  Query API      │  │
│   │ (crawl/    │    │ (chunk, embed,│    │ (embed query,   │  │
│   │  watch)    │    │  store)       │    │  ANN + rerank)  │  │
│   └────────────┘    └───────────────┘    └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                    REST API + MCP server
                              │
        ┌──────────┬──────────┬──────────┬──────────┐
        │ VS Code  │  Mobile  │ Browser  │  Office   │
        │ (MCP or  │  (Expo,  │ext (Docs,│  add-in   │
        │  ext.)   │  REST)   │ PDFs)    │           │
        └──────────┴──────────┴──────────┴──────────┘
```

The engine has zero knowledge of which adapter is calling it. Every client is a thin shell around the same REST/MCP surface.

---

## 3. Tech Stack

| Component | Choice | Why |
|---|---|---|
| Core engine language | Python (FastAPI) | Fits existing Python fluency; FastAPI gives async REST + auto OpenAPI docs |
| Embedding model | `nomic-embed-text` via Ollama | Runs on your existing local Ollama setup, no external API cost |
| Optional query rewriting | Local model already routed through Claude Code (qwen3:14b via Ollama, or Mistral Large backend) | Reuse infra you've already got working rather than adding a new dependency |
| Vector store | `sqlite-vec` to start; Qdrant if you outgrow it | sqlite-vec = zero ops, single file; Qdrant = filtering + scale later |
| Reranker (optional) | Small cross-encoder (e.g. `bge-reranker-base`) | Meaningful relevance boost on top-K before returning results |
| File parsing | PyMuPDF (PDF), `python-docx`/`openpyxl` (Office), `unstructured` (general) | Broad format coverage without hand-rolled parsers |
| OCR (scanned PDFs) | Tesseract via `pytesseract` | Standard, local, no cloud OCR needed |
| MCP layer | Python MCP SDK | Wraps the REST API as MCP tools for Claude Desktop / VS Code |
| Deployment | Docker Compose + Tailscale | Private reachability from any device without exposing anything publicly |
| Mobile client | Expo | You already have this stack fully set up from Kairo |
| Browser extension | Manifest V3 | Covers Google Docs + browser-based PDF viewers |
| Office client | Office Add-ins (Office.js) | One JS codebase across Word/Excel/PowerPoint |

---

## 4. Data Model

```jsonc
// Document
{
  "id": "uuid",
  "source_id": "fs-home | drive-personal | notion-workspace | ...",
  "path": "/original/path/or/url",
  "title": "string",
  "mime_type": "application/pdf | text/plain | ...",
  "modified_at": "ISO-8601",
  "indexed_at": "ISO-8601",
  "content_hash": "sha256, used to skip re-embedding unchanged files"
}

// Chunk
{
  "id": "uuid",
  "document_id": "uuid (FK -> Document)",
  "text": "string",
  "position": 0,                  // order within document
  "page": null,                   // for PDFs
  "embedding_model": "nomic-embed-text",
  "vector": [0.012, -0.041, ...]  // stored in vector index, not inline in prod
}

// Source (connector registration)
{
  "id": "fs-home",
  "type": "filesystem | gdrive | notion | imap",
  "config": { "root_path": "/Users/you/Documents" },
  "last_synced_at": "ISO-8601",
  "status": "idle | syncing | error"
}
```

---

## 5. Core Engine Components

### 5.1 Connectors
Each connector implements a common interface: `list_changed_items(since) -> [RawItem]` and `fetch_content(item) -> bytes + mime_type`.

- **Filesystem** — `watchdog` for live change events; initial full walk on first run.
- **Google Drive** — Drive API v3, OAuth2, incremental sync via `changes.list`.
- **Notion** — Notion API, paginated `search` + block children fetch.
- **Email** — IMAP or Gmail API, filtered to specific labels/folders to avoid indexing everything.
- **PDFs** — PyMuPDF for text-layer PDFs; fall back to Tesseract OCR when no text layer is detected.

### 5.2 Chunking
- Split by paragraph/section boundaries first, not fixed character counts.
- Target ~300–500 tokens per chunk, ~50-token overlap between adjacent chunks.
- Preserve source metadata per chunk (document id, page, position) so results can point back to an exact location.

### 5.3 Embeddings
- `nomic-embed-text` (768-dim) called via local Ollama endpoint, batched (e.g. 32 chunks/request) for throughput.
- Store `embedding_model` per chunk — this lets you re-embed cleanly later if you switch models without ambiguity about which vectors are stale.

### 5.4 Vector Store
- Start with `sqlite-vec`: single file, no server process, good enough for personal-scale corpora (tens of thousands of chunks).
- Migrate to Qdrant only if you need metadata-filtered search at larger scale or multi-collection isolation per source.

### 5.5 Query Pipeline
1. **(Optional) Query rewrite** — pass the raw query through your local qwen3:14b route to generate 1–2 alternate phrasings ("budget disagreement doc from march" → "Q1 marketing budget dispute email"). Skip this step initially; add it if raw semantic search underperforms on vague queries.
2. **Embed** the query (or each rewritten variant) with the same embedding model used for indexing.
3. **ANN search** — top-K (e.g. K=20) nearest chunks from the vector store.
4. **(Optional) Rerank** — cross-encoder pass on the top-K to reorder by finer-grained relevance.
5. **Return top-N** (e.g. 5) with snippet, source path, score, and document metadata.

---

## 6. Core Engine REST API

```
POST   /v1/sources                 register a new connector
GET    /v1/sources                 list registered sources + sync status
POST   /v1/sources/{id}/sync       trigger a manual re-sync
DELETE /v1/sources/{id}            remove a source and its indexed content

POST   /v1/search                  semantic search
GET    /v1/status                  engine health, index size, last sync times
```

**`POST /v1/search`** — request:
```json
{
  "query": "budget disagreement doc from march",
  "top_k": 5,
  "filters": { "source_id": ["fs-home", "gdrive-personal"] }
}
```

response:
```json
{
  "results": [
    {
      "document_id": "uuid",
      "title": "Q1 Marketing Spend.xlsx",
      "path": "/Users/you/Documents/finance/Q1 Marketing Spend.xlsx",
      "snippet": "...disagreement over the ad spend line item raised by finance...",
      "score": 0.83,
      "source_id": "fs-home"
    }
  ]
}
```

---

## 7. MCP Server Spec

Wrap the REST API as MCP tools so Claude Desktop and VS Code become working clients immediately, with no custom UI.

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

Each tool call internally proxies to the matching REST endpoint above — the MCP layer is a translation shim, not a second implementation.

---

## 8. Deployment

**`docker-compose.yml` skeleton:**
```yaml
services:
  engine:
    build: ./engine
    ports:
      - "8420:8420"
    volumes:
      - ./data:/data          # sqlite-vec file + config
      - ~/Documents:/sources/home:ro
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
    restart: unless-stopped

  tailscale:
    image: tailscale/tailscale
    hostname: search-engine
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
    network_mode: service:engine
    volumes:
      - ./ts-state:/var/lib/tailscale
```

Running this on a home server, NAS, or a small VPS puts the engine on your Tailnet — every device you own can reach it at a stable private address (e.g. `search-engine.your-tailnet.ts.net:8420`) without exposing anything to the public internet.

---

## 9. Client Adapters (by build phase)

### Phase 1 — MCP clients (Claude Desktop, VS Code)
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
Use this phase to validate retrieval quality on real queries before building anything else.

### Phase 2 — Self-hosted deployment
Move the container to always-on infrastructure (§8). No client code changes needed — just repoint the URL from `localhost` to the Tailscale address.

### Phase 3 — Expo mobile app
Screens: search bar, results list (title, snippet, source), source filter toggle. Calls `POST /v1/search` directly over the Tailnet — no MCP needed on mobile.

### Phase 4 — Browser extension (Manifest V3)
Content script injects a search overlay (e.g. triggered by a keyboard shortcut); background service worker calls the REST API. Covers Google Docs and any browser-based PDF viewer without per-site integration.

### Phase 5 — Office add-in
Office.js task pane, one codebase shared across Word/Excel/PowerPoint, calling the same REST API.

### Phase 6 (optional, later) — OS-native search hooks
macOS Spotlight importer / Windows Search indexer plugin, only if a dedicated search surface still feels necessary once the above are in daily use.

---

## 10. Security & Privacy

- No public internet exposure — Tailscale-only reachability.
- Simple bearer-token auth between clients and the engine (a shared secret is sufficient at personal scale; rotate it if a device is lost).
- Source credentials (Drive/Notion OAuth tokens) stored encrypted at rest in the engine's config, never sent to clients.

---

## 11. Testing & Validation

- Build a small eval set: ~20 queries with a known "correct" document each, drawn from your real files. Track recall@5 as you tune chunking/reranking.
- Sanity-check indexing throughput on your actual document volume before committing to a vector store choice — sqlite-vec's limits are fine for thousands of documents, less so for hundreds of thousands.

---

## 12. Milestones

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Core engine + MCP server | You can ask Claude Desktop a vague question and get the right file back |
| 2 | Self-hosted deployment | Same query works from a second device on your Tailnet |
| 3 | Mobile client | Search works from your phone off wifi (via Tailscale) |
| 4 | Browser extension | Search overlay works inside Google Docs |
| 5 | Office add-in | Search task pane works inside Word |
| 6 | (Optional) OS-native hooks | Spotlight/Windows Search returns your indexed content |

---

## 13. Open Questions / Future Considerations

- Whether offline-first (local-embedded engine + sync) is ever worth the added complexity — revisit only if you regularly need search with zero network access.
- Reindexing debounce strategy for frequently-edited office documents (avoid re-embedding on every keystroke-triggered autosave).
- Resource budget for the always-on host (RAM for embedding batches, disk for the vector index).
