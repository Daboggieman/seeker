"""Sqlite-vec document and chunk store.

The vector store is backed by sqlite-vec (docs/build_docs/04-core-engine-specs.md
section 5.4).  Vectors live in a sqlite-vec virtual table; metadata (text, path,
mime_type) lives in plain SQLite tables joined by chunk id.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlite_vec

from seeker.chunking.chunker import Chunk


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class IndexStore:
    """Document + chunk store backed by SQLite + sqlite-vec."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Create all tables if they do not exist.  Idempotent."""
        conn = _connect(self._path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id             TEXT PRIMARY KEY,
                type           TEXT NOT NULL,
                config         TEXT NOT NULL DEFAULT '{}',
                last_synced_at TEXT,
                status         TEXT NOT NULL DEFAULT 'idle'
            );

            CREATE TABLE IF NOT EXISTS documents (
                id           TEXT PRIMARY KEY,
                source_id    TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                path         TEXT NOT NULL,
                title        TEXT NOT NULL DEFAULT '',
                mime_type    TEXT NOT NULL DEFAULT 'application/octet-stream',
                modified_at  TEXT NOT NULL,
                indexed_at   TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id              TEXT PRIMARY KEY,
                document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                text            TEXT NOT NULL,
                position        INTEGER NOT NULL,
                page            INTEGER,
                embedding_model TEXT NOT NULL DEFAULT 'mock'
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
            """
        )
        # sqlite-vec virtual table: 768-dim float vectors, one per chunk.
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors
            USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[768])
            """
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def register_source(
        self, source_id: str, source_type: str, config: dict[str, Any]
    ) -> None:
        conn = _connect(self._path)
        conn.execute(
            """
            INSERT INTO sources (id, type, config, status)
            VALUES (?, ?, ?, 'idle')
            ON CONFLICT(id) DO UPDATE
                SET type = excluded.type, config = excluded.config
            """,
            (source_id, source_type, json.dumps(config)),
        )
        conn.commit()
        conn.close()

    def list_sources(self) -> list[dict[str, Any]]:
        conn = _connect(self._path)
        rows = conn.execute(
            "SELECT id, type, config, last_synced_at, status FROM sources"
        ).fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "type": r[1],
                "config": r[2],
                "last_synced_at": r[3],
                "status": r[4],
            }
            for r in rows
        ]

    def delete_source(self, source_id: str) -> None:
        """Remove a source; its documents and chunks cascade."""
        conn = _connect(self._path)
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.commit()
        conn.close()

    def update_sync_status(self, source_id: str, status: str) -> None:
        conn = _connect(self._path)
        conn.execute(
            "UPDATE sources SET status = ?, last_synced_at = ? WHERE id = ?",
            (status, _now_iso(), source_id),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    _DOC_COLS = "id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash"
    _DOC_KEYS = [
        "id",
        "source_id",
        "path",
        "title",
        "mime_type",
        "modified_at",
        "indexed_at",
        "content_hash",
    ]

    def upsert_document(
        self,
        *,
        doc_id: str,
        source_id: str,
        path: str,
        title: str,
        mime_type: str,
        modified_at: str,
        content_hash: str,
    ) -> None:
        conn = _connect(self._path)
        conn.execute(
            """
            INSERT INTO documents
                (id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                path = excluded.path,
                title = excluded.title,
                mime_type = excluded.mime_type,
                modified_at = excluded.modified_at,
                indexed_at = excluded.indexed_at,
                content_hash = excluded.content_hash
            """,
            (doc_id, source_id, path, title, mime_type, modified_at, _now_iso(), content_hash),
        )
        conn.commit()
        conn.close()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        conn = _connect(self._path)
        row = conn.execute(
            f"SELECT {self._DOC_COLS} FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(zip(self._DOC_KEYS, row, strict=True))

    def get_documents_by_source(self, source_id: str) -> list[dict[str, Any]]:
        conn = _connect(self._path)
        rows = conn.execute(
            f"SELECT {self._DOC_COLS} FROM documents WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        conn.close()
        return [dict(zip(self._DOC_KEYS, row, strict=False)) for row in rows]

    def find_document_by_hash(self, source_id: str, content_hash: str) -> str | None:
        """The document id whose content_hash matches, within one source.

        The hash gate (docs/build_docs/11-coding-agent-rules.md rule 4): an
        unchanged file must never be re-embedded.  Lookup is scoped by source so
        identical files in different sources are indexed independently.
        """
        conn = _connect(self._path)
        row = conn.execute(
            "SELECT id FROM documents WHERE source_id = ? AND content_hash = ? LIMIT 1",
            (source_id, content_hash),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def delete_document(self, doc_id: str) -> None:
        conn = _connect(self._path)
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]] | None = None,
        *,
        embedding_model: str = "mock",
    ) -> None:
        if not chunks:
            return
        conn = _connect(self._path)
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO chunks (id, document_id, text, position, page, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text,
                    position = excluded.position,
                    page = excluded.page,
                    embedding_model = excluded.embedding_model
                """,
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.text,
                    chunk.position,
                    chunk.page,
                    embedding_model,
                ),
            )
        if vectors:
            for chunk, vec in zip(chunks, vectors, strict=True):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO chunk_vectors (chunk_id, embedding)
                    VALUES (?, ?)
                    """,
                    (chunk.id, sqlite_vec.serialize_float32(vec)),
                )
        conn.commit()
        conn.close()

    def delete_chunks_for_document(self, doc_id: str) -> None:
        conn = _connect(self._path)
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
        source_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """KNN search over chunk vectors, joined with document metadata.

        Returns up to top_k results whose document's source_id is in
        `source_ids` (None = all sources), best match first, each carrying a
        snippet, path, score, and source id per the API contract.
        """
        conn = _connect(self._path)
        # Over-fetch so a source filter applied after the KNN pass still leaves
        # top_k results in most cases.
        fetch_k = top_k * 4 if source_ids else top_k
        try:
            rows = conn.execute(
                """
                SELECT v.chunk_id, v.distance
                FROM chunk_vectors v
                WHERE embedding MATCH ? AND k = ?
                ORDER BY distance
                """,
                (sqlite_vec.serialize_float32(query_vector), fetch_k),
            ).fetchall()
        finally:
            conn.close()

        results: list[dict[str, Any]] = []
        for chunk_id, distance in rows:
            doc = self._chunk_with_document(chunk_id=chunk_id)
            if doc is None:
                continue
            if source_ids and doc["source_id"] not in source_ids:
                continue
            # sqlite-vec distance is cosine distance: similarity = 1 - distance,
            # clamped to [0, 1] for the API contract ("score" is relevance).
            similarity = max(0.0, 1.0 - distance)
            text = doc["text"]
            results.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": doc["document_id"],
                    "title": doc["title"],
                    "path": doc["path"],
                    "snippet": (text[:200] + "...") if len(text) > 200 else text,
                    "score": round(similarity, 4),
                    "source_id": doc["source_id"],
                }
            )
            if len(results) >= top_k:
                break
        return results

    def _chunk_with_document(self, *, chunk_id: str) -> dict[str, Any] | None:
        conn = _connect(self._path)
        row = conn.execute(
            """
            SELECT c.id, c.document_id, c.text,
                   d.title, d.path, d.source_id
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ?
            """,
            (chunk_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return {
            "chunk_id": row[0],
            "document_id": row[1],
            "text": row[2],
            "title": row[3],
            "path": row[4],
            "source_id": row[5],
        }
