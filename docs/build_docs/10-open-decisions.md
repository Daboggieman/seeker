# Seeker — Open Decisions

Source of record: spec §13 (Open Questions / Future Considerations). Each row holds the default
that applies if the decision is not made explicitly. When a decision IS made, it moves into an
ADR in `docs/adr/` and this table is updated to say so.

| # | Question | Default if undecided | Status |
| --- | --- | --- | --- |
| 1 | Query rewriting — add the rewrite step or keep raw queries? | Skip initially; add only if raw semantic search underperforms on vague queries (per spec §5.5) | Open |
| 2 | Reranker — include a cross-encoder pass, and which model? | `bge-reranker-base` if recall@5 stalls after tuning chunking | Open |
| 9 | Embedding backend — Ollama is not installed on this machine (verified 2026-10-24) | **Mock embedding backend first** (deterministic vectors behind the same interface, tagged `embedding_model: "mock"`); decide real backend (native Ollama install vs Docker sidecar) before the eval set runs | Open — blocks eval set, not engine work |
| 3 | Vector store migration threshold — when does sqlite-vec stop being enough? | Stay on sqlite-vec until metadata-filtered search at larger scale or per-source collection isolation is needed; then Qdrant | Open |
| 4 | Reindexing debounce strategy for frequently-edited office documents | Debounce (e.g. re-index only if not modified for N minutes after a change event) | Open |
| 5 | Resource budget for the always-on host (RAM for embedding batches, disk for the vector index) | Decide from measured throughput during Phase 1; record the numbers in handover docs | Open |
| 6 | Offline-first (local-embedded engine + sync) | Not worth the complexity unless you regularly need search with zero network access — revisit only then | Open |
| 7 | Email connector scope (IMAP vs Gmail API, which labels/folders) | Gmail API if the account is Google; filter to specific labels, never index everything | Open |
| 8 | Bearer-token rotation story | Shared secret in engine config; rotate manually when a device is lost | Open |
| 10 | First indexed source directory for the eval set (`~/Documents` is empty on this machine) | User will point at a real directory during Phase 1 | Open — user input needed |

## How to close one

Record it as an ADR in `docs/adr/`, then move the row's status to Closed with the ADR number.
Do not edit the spec's §13 list to record the decision — that section is the spec's record of
what was open when the spec was written; this file tracks the current state.