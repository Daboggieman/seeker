"""sqlite-vec vector store.

Contract (docs/build_docs/04-core-engine-specs.md section 5.4,
docs/handover_docs/02-engine-conventions.md):
- sqlite-vec: single file, no server process, personal-scale corpora;
- nothing writes to the store except the index pipeline, nothing reads it
  except the query path — this module is that low-level boundary;
- `embedding_model` on every chunk row; the query path filters on it so a
  query embedded with one model can never rank chunks of another;
- `content_hash` on every document, checked by the pipeline via
  `get_document_by_path` before re-embedding.

Invariants enforced here:
- one dimensions value per store file, fixed at creation (a `meta` row) and
  checked on every open;
- vectors are L2-normalized before insert, so the L2 distances sqlite-vec
  returns order identically to cosine similarity (sqlite-vec 0.1.9 has no
  vec0 cosine distance option — verified 2026-10-26);
- chunks are always written together with their vectors in one transaction,
  and a document's old chunks+ vectors are deleted before its new ones land.

Sync by design: personal-scale sqlite calls are millisecond-fast; the API
layer wraps this in a threadpool, not this module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from seeker.store.records import DocumentRecord, SearchHit, SourceRecord, StoredChunk

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  root_path TEXT NOT NULL,
  last_synced_at TEXT,
  status TEXT NOT NULL DEFAULT 'idle'
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  modified_at TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  position INTEGER NOT NULL,
  page INTEGER,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
"""


def _normalize(vector: list[float]) -> list[float]:
    """Unit-normalize; zero vectors pass through unchanged."""
    norm = sum(v * v for v in vector) ** 0.5
    if norm == 0.0:
        return list(vector)
    return [v / norm for v in vector]


class VectorStore:
    """Documents + chunks + vectors in one sqlite file."""

    def __init__(self, path: str | Path, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        stored = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'dimensions'"
        ).fetchone()
        if stored is None:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('dimensions', ?)",
                    (str(self.dimensions),),
                )
        elif int(stored["value"]) != self.dimensions:
            raise ValueError(
                f"store was created with {stored['value']} dimensions, "
                f"got {self.dimensions}"
            )
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding float[{self.dimensions}]
            )"""
        )

    # -- index path (called by the pipeline only) ---------------------------

    def upsert_document(self, doc: DocumentRecord) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO documents
                   (id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(path) DO UPDATE SET
                     source_id=excluded.source_id,
                     title=excluded.title,
                     mime_type=excluded.mime_type,
                     modified_at=excluded.modified_at,
                     indexed_at=excluded.indexed_at,
                     content_hash=excluded.content_hash""",
                (
                    doc.id,
                    doc.source_id,
                    doc.path,
                    doc.title,
                    doc.mime_type,
                    doc.modified_at,
                    doc.indexed_at,
                    doc.content_hash,
                ),
            )

    def replace_chunks(
        self, document_id: str, chunks: list[StoredChunk]
    ) -> None:
        """Atomically replace a document's chunks and their vectors."""
        for chunk in chunks:
            if chunk.document_id != document_id:
                raise ValueError(
                    f"chunk {chunk.id} belongs to {chunk.document_id}, not {document_id}"
                )
        with self._conn:
            old_ids = [
                row["id"]
                for row in self._conn.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
                ).fetchall()
            ]
            if old_ids:
                marks = ",".join("?" * len(old_ids))
                self._conn.execute(
                    f"DELETE FROM chunk_vectors WHERE chunk_id IN ({marks})", old_ids
                )
                self._conn.execute(
                    f"DELETE FROM chunks WHERE id IN ({marks})", old_ids
                )
            for chunk in chunks:
                self._conn.execute(
                    "INSERT INTO chunks (id, document_id, text, position, page, embedding_model)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.text,
                        chunk.position,
                        chunk.page,
                        chunk.embedding_model,
                    ),
                )
                self._conn.execute(
                    "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                    (chunk.id, _serialize(_normalize(chunk.vector))),
                )

    def delete_document(self, document_id: str) -> None:
        """Remove a document and all of its chunks and vectors."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM chunk_vectors WHERE chunk_id IN"
                " (SELECT id FROM chunks WHERE document_id = ?)",
                (document_id,),
            )
            self._conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            self._conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    # -- index path: content_hash gate -------------------------------------

    def get_document_by_path(self, path: str) -> DocumentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE path = ?", (path,)
        ).fetchone()
        return _row_to_document(row) if row else None

    def document_paths_for_source(self, source_id: str) -> dict[str, str]:
        """path -> document_id for every stored document of one source."""
        return {
            row["path"]: row["id"]
            for row in self._conn.execute(
                "SELECT path, id FROM documents WHERE source_id = ?", (source_id,)
            ).fetchall()
        }

    def chunk_models(self, document_id: str) -> set[str]:
        """Distinct embedding models across a document's chunks."""
        return {
            row["embedding_model"]
            for row in self._conn.execute(
                "SELECT DISTINCT embedding_model FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        }

    def counts(self) -> dict[str, int]:
        """Index sizes for the status endpoint."""
        documents = self._conn.execute("SELECT count(*) AS n FROM documents").fetchone()[0]
        chunks = self._conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        return {"documents": documents, "chunks": chunks}

    # -- sources -------------------------------------------------------------

    def upsert_source(self, source: SourceRecord) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO sources (id, type, root_path, last_synced_at, status)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     type=excluded.type,
                     root_path=excluded.root_path,
                     last_synced_at=excluded.last_synced_at,
                     status=excluded.status""",
                (
                    source.id,
                    source.type,
                    source.root_path,
                    source.last_synced_at,
                    source.status,
                ),
            )

    def get_source(self, source_id: str) -> SourceRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return _row_to_source(row) if row else None

    def list_sources(self) -> list[SourceRecord]:
        rows = self._conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [_row_to_source(row) for row in rows]

    def delete_source(self, source_id: str) -> bool:
        """Remove a source and every document indexed from it."""
        document_ids = [
            row["id"]
            for row in self._conn.execute(
                "SELECT id FROM documents WHERE source_id = ?", (source_id,)
            ).fetchall()
        ]
        had_documents = bool(document_ids)
        for document_id in document_ids:
            self.delete_document(document_id)
        with self._conn:
            self._conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return had_documents

    def close(self) -> None:
        self._conn.close()

    # -- query path ---------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        *,
        model_name: str,
        top_k: int,
        source_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        """KNN search restricted to chunks of exactly `model_name`.

        The kNN pass runs first (vec0), then the outer query filters by
        embedding model and optional sources — wrong-model chunks can consume
        KNN slots but can never be returned, which upholds the same-model rule
        at the cost of recall when stale-model chunks exist. Re-embedding
        stale chunks is the pipeline's job, not the store's.
        """
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not query_vector:
            raise ValueError("query_vector must not be empty")
        norm = sum(v * v for v in query_vector) ** 0.5
        if norm == 0.0:
            raise ValueError("query_vector must not be a zero vector")
        sql = """
            SELECT c.id, c.document_id, c.text, c.position, c.page,
                   c.embedding_model, v.distance,
                   d.path, d.source_id, d.title
            FROM chunk_vectors v
            JOIN chunks c ON c.id = v.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE v.embedding MATCH ? AND v.k = ?
              AND c.embedding_model = ?
        """
        params: list[object] = [_serialize(_normalize(query_vector)), top_k, model_name]
        if source_ids:
            marks = ",".join("?" * len(source_ids))
            sql += f" AND d.source_id IN ({marks})"
            params.extend(source_ids)
        sql += " ORDER BY v.distance LIMIT ?"
        params.append(top_k)
        rows = self._conn.execute(sql, params).fetchall()
        return [
            SearchHit(
                chunk_id=row["id"],
                document_id=row["document_id"],
                text=row["text"],
                position=row["position"],
                page=row["page"],
                embedding_model=row["embedding_model"],
                score=row["distance"],
                path=row["path"],
                source_id=row["source_id"],
                title=row["title"],
            )
            for row in rows
        ]


def _serialize(vector: list[float]) -> str:
    return "[" + ",".join(repr(v) for v in vector) + "]"


def _row_to_document(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        source_id=row["source_id"],
        path=row["path"],
        title=row["title"],
        mime_type=row["mime_type"],
        modified_at=row["modified_at"],
        indexed_at=row["indexed_at"],
        content_hash=row["content_hash"],
    )


def _row_to_source(row: sqlite3.Row) -> SourceRecord:
    return SourceRecord(
        id=row["id"],
        type=row["type"],
        root_path=row["root_path"],
        last_synced_at=row["last_synced_at"],
        status=row["status"],
    )
