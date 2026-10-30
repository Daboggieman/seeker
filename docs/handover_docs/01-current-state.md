# Current state — 2026-10-29

> Phase 1 in progress. Built so far: chunker (+ overlap fix, 2026-10-26), mock
> embedding backend, universal OpenAI-compatible backends, config + factories
> (ADR-0001), sqlite-vec vector store, filesystem connector, index pipeline,
> REST query API, MCP shim, **real backend via native Ollama (ADR-0002,
> 2026-10-29)**. Next: eval set — needs the user's source directory (OD 10) —
> then Phase 1 exit validation in Claude Desktop. See the phase board below.

The status board. Everything here is dated; if a claim is older than the work, distrust it and
re-measure.

## What is being worked on right now

**2026-10-29 — MCP over HTTP fixed; engine + Ollama are systemd user services.**

- **MCP-over-HTTP transport fixed** (`engine/src/seeker/api/app.py`) — it had
  never actually worked over HTTP (the MCP tests bypassed HTTP via
  `call_tool`). Two bugs: (1) the mcp SDK's streamable app serves at its own
  internal `/mcp` path, so mounting it at `/mcp` double-prefixed the endpoint
  to `/mcp/mcp` — fixed by mounting at the root so `POST /mcp` reaches it
  directly; (2) FastAPI does not run lifespans of mounted sub-apps, so the
  session manager never started and every MCP call was a 500 ("Task group is
  not initialized") — fixed by composing the sub-app's lifespan into the
  parent app's. New API test performs a real MCP `initialize` handshake over
  HTTP (TestClient needs `with` for lifespans; its Host header must carry a
  port and be localhost to pass the SDK's DNS-rebinding protection — bare
  `127.0.0.1` or `testserver` are rejected 421).
- **Phase 2 note:** the SDK auto-enables rebinding protection allowing only
  `127.0.0.1:*/localhost:*/[::1]:*` as Host. Access via a Tailscale hostname
  or IP will be rejected 421 until `transport_security` is widened
  (`streamable_http_app(transport_security=...)`).
- **Engine + Ollama run as systemd user services** (user-approved
  2026-10-30): `~/.config/systemd/user/{ollama,seeker-engine}.service`,
  config in `~/.config/seeker/engine.env` (edit + `systemctl --user restart
  seeker-engine`), engine on **:8420** (the port the MCP shim docs already
  promised), linger enabled (runs at boot, survives session teardowns — the
  ad-hoc `setsid` launches died at every session boundary, 3× today).
  Swap any OpenAI-compatible provider by editing the env file (ADR-0001).
- **Suite: 145 tests green, ruff clean (measured 2026-10-30).**

**2026-10-29 — real backend wired: native Ollama; end-to-end verified with real embeddings.**

- **Decision recorded as ADR-0002**
  ([`../adr/0002-native-ollama-real-backend.md`](../adr/0002-native-ollama-real-backend.md)):
  native Ollama at `http://localhost:11434` (server v0.40.13); embeddings =
  `nomic-embed-text` (pulled 2026-10-29, **768 dims measured** — matches the
  default `SEEKER_EMBEDDING_DIMENSIONS`); LLM `qwen2.5-coder:7b` configured but
  unused until query rewriting is enabled (OD 1). Open decision 9 closed in
  [`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md).
  "Custom AIs" needed no new code — any OpenAI-compatible provider is a
  `SEEKER_*` env-var change (ADR-0001), now verified against a real local
  runtime.
- **End-to-end verified** (measured 2026-10-29): engine on :8777 with the real
  config, temp corpus of 3 files → sync returned `indexed: 3, failed: []`;
  query "how do I keep my bread culture alive" ranked bread.txt top-1 (0.513)
  over unrelated chunks (0.364 / 0.336) — keyword-free semantic match.
- **Suite re-verified**: 138 tests green, ruff clean, on a freshly recreated
  `engine/.venv` — now **Python 3.14** (the venv had vanished again; note the
  handover previously recorded Python 3.12.3).
- **Sync failures are no longer silent (fixed later the same day, 2026-10-29):**
  `SyncStats.failed` now carries structured `SyncFailure` records — `path`,
  `error` (type + message), best-effort `reason`, `suggestion` — and the sync
  API/MCP responses return them (`{"path", "error", "reason", "suggestion"}`),
  while the full traceback is logged per file. Recognized classes: endpoint
  unreachable/timeout, HTTP 404 (model missing) / 401-403 (credentials),
  undecodable text mime, corrupt/image-only PDF, unreadable file; anything else
  → "unexpected error" + log. Verified live: sync against a dead embedding port
  returns "embedding endpoint unreachable" + the `ollama serve` suggestion per
  file. Suite now 144 tests, ruff clean. Note: `httpx` is imported by
  `pipeline/indexer.py` at runtime but is only declared under `[project.optional-
  dependencies].dev` in `engine/pyproject.toml` (same is already true of
  `embeddings/openai_compat.py`) — a packaging gap to close before any
  non-venv install; not fixed (user's call).
- **Remaining gotchas (user's call):**
  - Background processes launched from an assistant session (ollama serve,
    uvicorn) die when the session ends — superseded 2026-10-30 by the systemd
    user services above; `setsid nohup` remains the fallback for one-off runs.
  - `data/` is **not** in `.gitignore`; the default `SEEKER_DB_PATH` is the
    relative `data/seeker.db`. The user will handle `.gitignore` themselves
    (2026-10-29: declined the assistant adding it).
  - `/tmp` is cleaned between sessions on this machine — smoke-test corpora
    and DBs there do not persist.

**2026-10-26 — query API + MCP shim built and tested; store thread-affinity bug found and fixed.**

- **REST query API** (`engine/src/seeker/api/app.py`, `service.py`): `/v1/search`,
  `/v1/sources` CRUD + sync, `/v1/status`, anonymous `/v1/health`. Bearer-token auth on every
  client-engine route (constant-time compare), machine-readable `{"code": ...}` errors,
  `X-Request-Id` middleware echoing a client-supplied id. The FastAPI-generated OpenAPI doc is
  the contract of record.
- **MCP shim** (`engine/src/seeker/mcp/server.py`): `MCPServer` (mcp 2.3.0) mounted at `/mcp`
  on the same app; tools (`search_documents`, `list_sources`, `reindex_source`) call the same
  `Engine` methods the REST routes call — no second implementation.
- **Store bug fixed** (`engine/src/seeker/store/store.py`): the sqlite connection was opened
  without `check_same_thread=False`, so any store call from a FastAPI threadpool worker, the
  TestClient portal thread, or an MCP tool thread raised `sqlite3.ProgrammingError` — every
  authenticated route except health was a 500 in any real use. The cross-thread design intent
  ("the API layer wraps it in a threadpool") predates the store; the store now matches it.
  Writes remain serialized by `with self._conn` transactions. Found by the new API tests;
  every store-touching route is covered by one.
- **API + MCP tests** (`engine/tests/test_api.py`, `engine/tests/test_mcp.py`): 34 tests —
  every route with valid/invalid/anonymous calls, validation errors, request-id echo, source
  filter, top_k, and the MCP tools called via `MCPServer.call_tool` (no HTTP). Ruff B904
  re-raise chain fixes in `app.py` en route.
- Suite: **138 tests green, ruff clean (measured 2026-10-26)**. Known flake (pre-existing,
  unrelated to this work): `test_filesystem_connector.py::
  TestIncrementalSync::test_since_exact_boundary_excludes_modified_at_same_moment` fails ~1
  run in 3 — the test's `time.time()` float boundary vs the file's µs-rounded mtime can
  roundtrip a sub-microsecond delta that flips the comparison. Suggested fix (not applied,
  user's call): µs-align the boundary (`t = round(time.time(), 6)`) or compare with an
  epsilon in the connector.
- Known behavior to decide later (not a bug, matches the code as written): FastAPI's own
  422 validation errors (e.g. empty `query` string) return FastAPI's default body shape, not
  the engine's `{"code": ...}` shape — only route-mapped errors do.

**2026-10-26 — chunker bug fixed; universal model backends; sqlite-vec store; filesystem connector; index pipeline.**

- **Index pipeline** (`engine/src/seeker/pipeline/`): `extract.py` (text/*
  decode + PyMuPDF page-tagged PDF extraction; unsupported mimes → None;
  scanned-PDF OCR is a later phase) and `indexer.py` (`IndexPipeline.sync`):
  fetch → sha256 `content_hash` gate → chunk (page tags preserved, positions
  renumbered per document) → batched embed (32/request) → store. Model-switch
  rule: same hash but chunks carrying another `embedding_model` are
  re-embedded. Full syncs (`since=None`) prune vanished documents; incremental
  syncs never prune. One failed file never aborts a sync (`SyncStats.failed`).
  104 tests green, ruff clean (measured 2026-10-26).
- **Filesystem connector** (`engine/src/seeker/connectors/`): the common
  interface (`list_changed_items(since) -> [RawItem]`,
  `fetch_content(item) -> FetchedContent`) as `base.py`; `FilesystemConnector`
  walks the source root recursively, incremental by mtime (`since` as
  ISO-8601 UTC "Z" string, None = full walk). Judgment calls (reversible):
  dot-files/dirs skipped by default (`include_hidden=True` disables), symlinks
  never followed, fetch verifies resolved path stays under the source root.
  Watchdog live events deferred until the pipeline exists to receive them
  (open decision 4 = its debounce strategy); the pipeline polls for now.
- **Vector store** (`engine/src/seeker/store/`): sqlite-vec 0.1.9 single-file
  store — documents + chunks tables, `chunk_vectors` vec0 virtual table
  (chunk_id PK, `float[N]`). Enforced in the module: one dimensions value per
  file (checked on open), vectors L2-normalized at insert (vec0 0.1.9 has no
  cosine distance option — verified — but for unit vectors L2 ordering equals
  cosine ordering), chunks+vectors written atomically, old vectors deleted on
  replace, per-chunk `embedding_model` filter on every search (same-model
  rule), source filter, `content_hash` gate support via
  `get_document_by_path`. Sync by design; the API layer wraps it in a
  threadpool. 76 tests green, ruff clean (measured 2026-10-26).
  Known quirk: the 8-dim mock can hash-cancel short two-token texts ("new
  text") to the zero vector — harmless for real corpora, noted where tests
  pick phrases.
- Chunker overlap bug fixed: `_carry_units` returned empty whenever every unit
  exceeded the overlap budget (the common case — ~300-token paragraphs, 50-token
  overlap), so adjacent chunks shared no overlap at all. Now falls back to the
  previous chunk's trailing words sized `min(overlap_tokens, room)`; dead
  `_word_carry` deleted. The previously failing
  `TestOverlap::test_adjacent_chunks_overlap` passes; suite green (59 tests,
  measured 2026-10-26).
- Embeddings module: `EmbeddingBackend` protocol, `MockEmbeddingBackend`
  (deterministic hashing-trick vectors, 768-dim, `embedding_model: "mock"`),
  `OpenAICompatibleEmbeddingBackend` (`/v1/embeddings`).
- LLM module: `LLMBackend` protocol, `MockLLMBackend`,
  `OpenAICompatibleLLMBackend` (`/v1/chat/completions`) — for the optional
  query-rewrite step, still off by default (open decisions 1–2).
- Config (`engine/src/seeker/config.py`, `SEEKER_*` env vars) and factories
  (`engine/src/seeker/factories.py`): backends selected by config, defaults are
  mock, engine runs with zero setup. Decision recorded as ADR-0001
  ([`../adr/0001-universal-openai-compatible-backends.md`](../adr/0001-universal-openai-compatible-backends.md)).
- Dev venv recreated at `engine/.venv` (it had vanished; pytest/ruff reinstalled
  from the `dev` extras).

**Pre-flight for Phase 1, 2026-10-24.** Environment verified: Python 3.12.3, Docker 29.9 +
Compose v5.6, Expo stack present. **Ollama is not installed on this machine** (no binary, no
service, nothing on `:11434`) — decided 2026-10-24 to build the engine against a **mock
embedding backend** and defer the real-backend decision (native install vs Docker sidecar) to
open decision 9 in
[`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md). The eval-set
source directory is also deferred — the user will point at one during Phase 1 (open decision
10). Repository layout was decided (D6 in
[`../build_docs/01-architecture-and-stack.md`](../build_docs/01-architecture-and-stack.md)):
`engine/` Python package at repo root, engine runs locally via uvicorn in Phase 1, Docker
enters only at Phase 2.

## Phase board

| Phase | Status | Verified | Notes |
|---|---|---|---|
| 1 — Core engine + MCP server | in progress | chunker, embeddings/LLM backends, vector store, filesystem connector, index pipeline, REST query API + MCP shim; ruff clean; 2026-10-26. Real backend via native Ollama, e2e verified 2026-10-29 (ADR-0002). MCP-over-HTTP transport fixed + systemd services 2026-10-30 | Code complete. Blocked on: eval set (source chosen: ~/gsmhub), Phase 1 exit validation in Claude Desktop |
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
