# Current state — 2026-10-26

> Phase 1 in progress. Built so far: chunker (+ overlap fix, 2026-10-26), mock
> embedding backend, universal OpenAI-compatible backends, config + factories
> (ADR-0001), sqlite-vec vector store, filesystem connector. Next: text
> extraction + index pipeline, then query API, MCP shim. See the phase board
> below.

The status board. Everything here is dated; if a claim is older than the work, distrust it and
re-measure.

## What is being worked on right now

**2026-10-26 — chunker bug fixed; universal model backends; sqlite-vec store; filesystem connector.**

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
| Phase | Status | Verified | Notes |
|---|---|---|---|
| 1 — Core engine + MCP server | in progress | chunker, embeddings/LLM backends, vector store, filesystem connector tested 2026-10-26 | Mock embeddings + universal OpenAI-compatible backends (ADR-0001); next: index pipeline |
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
