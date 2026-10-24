# Engine conventions — follow these for every module

These were decided once in the spec. Re-deciding them per component is how the engine ends up
inconsistent. Everything here binds all modules. Nothing here has been exercised by code yet —
the first build session is expected to confirm or correct these, and any departure is recorded
below.

## Structure rules

- **One engine, one surface.** The engine exposes REST (`/v1/...`); the MCP layer proxies it.
  There is no second implementation of search or indexing anywhere.
- **The index pipeline is one direction:** connectors → chunk → embed → store. Nothing writes
  to the vector store except the pipeline; nothing reads it except the query path.
- **Connectors implement the common interface.** `list_changed_items(since) -> [RawItem]` and
  `fetch_content(item) -> bytes + mime_type`. A connector that cannot express these is the
  wrong connector.
- **The engine is client-agnostic.** No adapter-specific fields, headers, or branches inside
  the engine.

## Data rules

- `content_hash` (sha256) is checked before embedding. Unchanged file → skip. No exceptions.
- `embedding_model` is stored on every chunk. Query embedding uses the same model the target
  chunks were indexed with — mixing models is a bug, not a fallback.
- Chunk metadata (`document_id`, `page`, `position`) is preserved through the pipeline. A
  result that cannot point back to its exact location is a bug.
- Timestamps are ISO-8601 UTC.

## Query rules

- `top_k` is respected exactly; filters restrict by `source_id`; every result carries a score,
  snippet, path, and source_id.
- Query rewriting and reranking are **off by default** — they are opt-in additions validated
  against the eval set, never defaults (open decisions 1–2 in
  [`../build_docs/10-open-decisions.md`](../build_docs/10-open-decisions.md)).

## Security rules

- Bearer token on every client-engine call; no anonymous routes except health.
- Source credentials stay in engine config, encrypted at rest, never sent to clients.
- Tailscale-only reachability; no public binding.

## Departure record

When the code departs from a rule above, record the departure here — what, why, and when —
so the next session does not "fix" it back.

- **2026-10-24 — mock embeddings before a real backend.** Ollama is not installed on this
  machine (verified), so Phase 1 starts with a mock embedding backend: deterministic vectors
  behind the same interface as the future Ollama backend, tagged `embedding_model: "mock"`.
  This is why the same-model rule matters — a query embedded with mock vectors must never be
  ANN-searched against `nomic-embed-text` chunks, and the per-chunk model field is what makes
  that check enforceable. The eval set (recall@5) means nothing until a real backend lands;
  it measures pipeline plumbing only.
