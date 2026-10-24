# Seeker — Data Model

Source of record: spec §4 (Data Model).

## Document

```jsonc
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
```

## Chunk

```jsonc
{
  "id": "uuid",
  "document_id": "uuid (FK -> Document)",
  "text": "string",
  "position": 0,                  // order within document
  "page": null,                   // for PDFs
  "embedding_model": "nomic-embed-text",
  "vector": [0.012, -0.041, ...]  // stored in vector index, not inline in prod
}
```

Storing `embedding_model` per chunk lets you re-embed cleanly later if you switch models,
without ambiguity about which vectors are stale.

## Source (connector registration)

```jsonc
{
  "id": "fs-home",
  "type": "filesystem | gdrive | notion | imap",
  "config": { "root_path": "/Users/you/Documents" },
  "last_synced_at": "ISO-8601",
  "status": "idle | syncing | error"
}
```

## Conventions

- Primary keys are UUIDs.
- `content_hash` on every document — re-embedding an unchanged file is a bug, not an
  optimisation. The hash short-circuits unchanged files during sync.
- `position` and `page` on every chunk so a result can point back to an exact location in the
  source document.
- Timestamps are ISO-8601 UTC.