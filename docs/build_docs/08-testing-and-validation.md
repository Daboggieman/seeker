# Seeker — Testing and Validation

Source of record: spec §11 (Testing & Validation).

## The eval set

Build a small eval set early: **~20 queries with a known "correct" document each**, drawn from
your real files. This is the engine's quality bar — not vibes.

**Built 2026-10-30** (`engine/eval/`): `queries.json` (20 query→document pairs over the
user's gsmhub corpus) and `run_eval.py` (indexes incrementally, runs the queries through the
real backend, prints per-query hits + recall@5). The recall@5 record itself lives in the
handover's dated entries ([`../handover_docs/01-current-state.md`](../handover_docs/01-current-state.md))
— baseline **recall@5 = 0.50, measured 2026-10-30**.

- Track **recall@5** as you tune chunking, embedding batch size, and reranking.
- Every change to chunking, embedding, or the query pipeline re-runs the eval set.
- A change that lowers recall@5 on the eval set does not ship, regardless of how it feels.

## What each layer must cover

| Layer | Must cover |
|---|---|
| Chunking unit tests | Paragraph splitting, overlap, token targets, page/position metadata preserved |
| Embedding integration | Batch calls to Ollama; `embedding_model` recorded per chunk; failure surfaces as an error, never a silent skip |
| Connector tests | `list_changed_items(since)` returns only changes; `fetch_content` returns bytes + mime; content_hash skips unchanged files |
| Query pipeline | top_k respected; filters restrict by source_id; score present on every result |
| API tests | Every route: valid, invalid, auth missing; validation errors |
| MCP shim | Each tool proxies to the right endpoint and returns the REST response shape |

## Standing test rules

- Never weaken a test to obtain a passing result.
- Never claim a test passed without running it.
- Add a test for every bug fix.

## Throughput sanity check

Sanity-check indexing throughput on your actual document volume **before committing to a
vector store choice** — sqlite-vec's limits are fine for thousands of documents, less so for
hundreds of thousands. If a full initial index takes hours, that is a finding, not a footnote —
record it in the handover docs.