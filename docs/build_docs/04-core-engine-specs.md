# Seeker — Core Engine Specs

Source of record: spec §5 (Core Engine Components). Four components are specified to a level
of detail where implementation must follow the text closely: connectors, chunking, embeddings,
vector store, and the query pipeline.

---

## 5.1 Connectors

Each connector implements a common interface:
`list_changed_items(since) -> [RawItem]` and `fetch_content(item) -> bytes + mime_type`.

| Connector | Mechanism |
|---|---|
| **Filesystem** | `watchdog` for live change events; initial full walk on first run. *Implemented 2026-10-26 as polling (`list_changed_items` by mtime) — watchdog deferred until the pipeline can receive events (open decision 4); also skips dot-dirs, never follows symlinks, and since 2026-10-30 supports `exclude_dirs` + code-extension mime overrides* |
| **Google Drive** | Drive API v3, OAuth2, incremental sync via `changes.list` |
| **Notion** | Notion API, paginated `search` + block children fetch |
| **Email** | IMAP or Gmail API, filtered to specific labels/folders |
| **PDFs** | PyMuPDF for text-layer PDFs; Tesseract OCR fallback when no text layer detected — *OCR is a later phase (not built as of 2026-10-30)* |

Launch scope is the filesystem connector. Drive, Notion, and email are later — each one is
registered as a `source` row and synced independently.

## 5.2 Chunking

- Split by paragraph/section boundaries first, not fixed character counts.
- Target ~300–500 tokens per chunk, ~50-token overlap between adjacent chunks.
- Preserve source metadata per chunk (document id, page, position) so results can point back
  to an exact location.

## 5.3 Embeddings

- `nomic-embed-text` (768-dim) called via local Ollama endpoint, batched (e.g. 32
  chunks/request) for throughput.
- Store `embedding_model` per chunk — re-embedding after a model switch must never be ambiguous
  about which vectors are stale.

## 5.4 Vector store

- Start with `sqlite-vec`: single file, no server process, good enough for personal-scale
  corpora (tens of thousands of chunks).
- Migrate to Qdrant only if you need metadata-filtered search at larger scale or
  multi-collection isolation per source.

## 5.5 Query pipeline

1. **(Optional) Query rewrite** — pass the raw query through your local model route to
   generate 1–2 alternate phrasings ("budget disagreement doc from march" → "Q1 marketing
   budget dispute email"). **Skip this step initially**; add it only if raw semantic search
   underperforms on vague queries.
2. **Embed** the query (or each rewritten variant) with the same embedding model used for
   indexing.
3. **ANN search** — top-K (e.g. K=20) nearest chunks from the vector store.
4. **(Optional) Rerank** — cross-encoder pass on the top-K to reorder by finer-grained
   relevance.
5. **Return top-N** (e.g. 5) with snippet, source path, score, and document metadata.