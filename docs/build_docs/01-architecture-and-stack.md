# Seeker — Architecture and Stack

Source of record: spec §2 (Architecture), §3 (Tech Stack).

## System architecture

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

The engine has zero knowledge of which adapter is calling it.

## Tech stack

| Component | Choice | Why |
|---|---|---|
| Core engine language | Python (FastAPI) | Fits existing Python fluency; FastAPI gives async REST + auto OpenAPI docs |
| Embedding model | `nomic-embed-text` via Ollama | Runs on your existing local Ollama setup, no external API cost |
| Optional query rewriting | Local model via Ollama (qwen3:14b or Mistral Large) | Reuse infra already working rather than adding a new dependency. *2026-10-30: ADR-0002 named `qwen2.5-coder:7b` (what the user runs); live config sets no `SEEKER_LLM_*` values — the knobs are wired through compose but inert. The rewrite step itself is still off — open decision 1* |
| Vector store | `sqlite-vec` to start; Qdrant if you outgrow it | sqlite-vec = zero ops, single file; Qdrant = filtering + scale later |
| Reranker (optional) | Small cross-encoder (e.g. `bge-reranker-base`) | Meaningful relevance boost on top-K before returning results |
| File parsing | PyMuPDF (PDF) + UTF-8 text for `text/*` files; office docs, binaries and images are skipped as `unsupported` | PyMuPDF covers PDFs; `python-docx`/`openpyxl`/`unstructured` were the plan — not built |
| OCR (scanned PDFs) | Tesseract via `pytesseract` | Standard, local, no cloud OCR needed. *Not built — scanned/image-only PDFs currently index to nothing (no OCR yet)* |
| MCP layer | Python MCP SDK | Wraps the REST API as MCP tools for Claude Desktop / VS Code |
| Deployment | Docker Compose + Tailscale | Private reachability from any device without exposing anything publicly |
| Mobile client | Expo | You already have this stack from Kairo |
| Browser extension | Manifest V3 | Covers Google Docs + browser-based PDF viewers |
| Office client | Office Add-ins (Office.js) | One JS codebase across Word/Excel/PowerPoint |

## Key decisions

| # | Decision | Why |
|---|---|---|
| D1 | Python + FastAPI for engine | Existing Python fluency, async REST, auto OpenAPI docs |
| D2 | `nomic-embed-text` via Ollama | Local, no API cost, already installed |
| D3 | `sqlite-vec` at launch | Zero ops, single file, fine for personal-scale corpora |
| D4 | Tailscale-only reachability | Private networking; no port exposed to the internet |
| D5 | MCP first, custom UIs later | Validate retrieval quality before UI investment |
| D6 | Expo for mobile | Reuse Kairo's proven stack |
| D7 | Repository layout: one repo, `engine/` Python package at the root | Matches the spec's `build: ./engine` compose context; client adapters (mobile, extension, office) become sibling directories later without moving the engine. *Live — `engine/`, `mobile/` and `extension/` exist (Phases 1, 3–4); `office/` not yet* |

## Repository layout

The layout follows from decision D7 and the spec's compose file (`build: ./engine`).
Phase 1 creates only `engine/`; later phases add their directories without moving anything.

```
seeker/
  engine/                     # the core engine — Python package
    pyproject.toml            # deps, ruff, pytest config; venv at engine/.venv
    src/seeker/               # connectors/, chunking/, embeddings/, store/, query/, api/, mcp/
    tests/                    # unit + api tests
  docker-compose.yml          # Phase 2: at the repo root (engine + tailscale + backup)
  docs/
    build_docs/               # this planning package
    handover_docs/            # the running record
    adr/                      # decision records (ADR-0001…0003 as of 2026-11-13)
  mobile/                     # Phase 3 (Expo)
  extension/                  # Phase 4 (Manifest V3)
  office/                     # Phase 5 (Office.js)
  semantic-search-build-docs.md   # source spec, stays at repo root
```

The engine ran locally in Phase 1 (`uvicorn` on port 8420, venv-based); since Phase 2 it
runs as the Docker Compose `engine` service (live 2026-11-12), still on port 8420.