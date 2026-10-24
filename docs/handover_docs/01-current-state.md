# Current state — 2026-10-24

> **Phase 1 code complete.** The core engine (chunker, filesystem connector, mock embedding
> backend, sqlite-vec store, FastAPI API, MCP shim) is built and all 61 tests pass. Phase 1's
> exit criterion — recall@5 on real personal files via MCP — is still open: it needs the real
> embedding backend (open decision 9) and a real source directory (open decision 10).

The status board. Everything here is dated; if a claim is older than the work, distrust it and
re-measure.

## What is being worked on right now

**Phase 1 core engine, 2026-10-24.** Built and verified on branch `phase_1_core_engine`:

- **Chunker** (`engine/src/seeker/chunking/`): paragraph → sentence → hard word split,
  ~500-token chunks, 50-token word-level overlap. 18 tests.
- **Filesystem connector** (`engine/src/seeker/connectors/`): `os.walk` (sees dotfiles),
  extensionless files handled, lazy SHA-256 content hash, mtime gating for incremental sync.
  17 tests.
- **Embedding backends** (`engine/src/seeker/embeddings/`): `EmbeddingBackend` protocol,
  `MockEmbeddingBackend` (SHA-256-seeded deterministic 768-dim vectors), `OllamaBackend`
  stub awaiting open decision 9. 4 tests.
- **IndexStore** (`engine/src/seeker/store/`): sqlite-vec virtual table, `serialize_float32`,
  KNN via `MATCH`/`k`, cosine-distance → similarity `max(0, 1 − distance)`, content-hash
  upsert gating, sync-status tracking. 14 tests.
- **FastAPI app** (`engine/src/seeker/api/`): `/health`, `POST/GET /v1/sources`,
  `POST /v1/sources/{id}/sync`, `DELETE /v1/sources/{id}`, `POST /v1/search`,
  `GET /v1/status`. 8 end-to-end tests against synthetic fixtures (register → sync → search).
- **MCP shim** (`engine/src/seeker/mcp/`): `search_documents`, `list_sources`,
  `reindex_source` — each proxies the same internal function the REST route calls.

Full suite: **61 passed** (`pytest`, engine venv, 2026-10-24).

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 1 — Core engine + MCP server | code complete | 61 tests green | Exit criterion (recall@5 on real files) pending open decisions 9 + 10; branch `phase_1_core_engine` |
| 2 — Self-hosted deployment | not started | — | Docker Compose + Tailscale sidecar; see Linux `host-gateway` note in build docs 06 |
| 3 — Mobile client | not started | — | Expo, direct REST over Tailnet |
| 4 — Browser extension | not started | — | Manifest V3 |
| 5 — Office add-in | not started | — | Office.js task pane |
| 6 — OS-native hooks (optional) | not started | — | Only if still needed after Phase 5 |

Status is written here as the record of what happened, after it happened — never in advance.

## Open items

- **Real embedding backend decision** (open decision 9): native Ollama install vs Docker
  sidecar. The eval set cannot run on mock vectors — recall@5 on mock embeddings measures the
  pipeline, not retrieval quality.
- **Eval-set source directory** (open decision 10): user to supply; `~/Documents` is empty.
- The open decisions in [`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md)
  — query rewriting, reranker, vector-store migration threshold, debounce strategy, resource
  budget, email connector scope — default if not decided, but several are cheaper to decide
  during Phase 1 than after it.
- The user commits and pushes outside these sessions (standing constraint, see
  [`README.md`](README.md)).
