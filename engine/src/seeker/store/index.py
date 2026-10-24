"""Sqlite-vec document and chunk store.

The vector store is backed by sqlite-vec (docs/build_docs/04-core-engine-specs.md section 5.4).
Vectors live in sqlite-vec; metadata (text, path, mime_type) lives in plain SQLite tables.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlite_vec

from seeker.chunking.chunker import Chunk
from seeker.connectors.base import RawItem


def _conn(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path))
    c.execute("PRAGMA foreign_keys = ON")
    return c


class IndexStore:
    """Document + chunk store backed by SQLite + sqlite-vec."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Create all tables if they do not exist.  Idempotent."""
        conn = _conn(self._path)
        sqlite_vec.register(conn)

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id       TEXT PRIMARY KEY,
                type     TEXT NOT NULL,
                config   TEXT NOT NULL DEFAULT '{}',  -- JSON
                last_synced_at  TEXT,
                status   TEXT NOT NULL DEFAULT 'idle'
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

            CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(document_id);
            """
        )

        # sqlite-vec virtual table: 768-dim float vectors, one per chunk.
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors
            USING vec0(chunk_id TEXT PRIMARY KEY, embedding REAL[768])
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
        conn = _conn(self._path)
        conn.execute(
            """
            INSERT INTO sources (id, type, config, status)
            VALUES (?, ?, ?, 'idle')
            ON CONFLICT(id) DO UPDATE
                SET type   = excluded.type,
                    config = excluded.config
            """,
            (source_id, source_type, json.dumps(config)),
        )
        conn.commit()
        conn.close()

    def list_sources(self) -> list[dict[str, Any]]:
        conn = _conn(self._path)
        rows = conn.execute("SELECT id, type, config, last_synced_at, status FROM sources").fetchall()
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
        conn = _conn(self._path)
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.commit()
        conn.close()

    def update_sync_status(self, source_id: str, status: str) -> None:
        conn = _conn(self._path)
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "UPDATE sources SET status = ?, last_synced_at = ? WHERE id = ?",
            (status, now, source_id),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

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
        conn = _conn(self._path)
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            """
            INSERT INTO documents
                (id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                path         = excluded.path,
                title        = excluded.title,
                mime_type    = excluded.mime_type,
                modified_at  = excluded.modified_at,
                indexed_at   = excluded.indexed_at,
                content_hash = excluded.content_hash
            """,
            (doc_id, source_id, path, title, mime_type, modified_at, now, content_hash),
        )
        conn.commit()
        conn.close()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        conn = _conn(self._path)
        row = conn.execute(
            "SELECT id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash "
            "FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(
            zip(
                [
                    "id",
                    "source_id",
                    "path",
                    "title",
                    "mime_type",
                    "modified_at",
                    "indexed_at",
                    "content_hash",
                ],
                row,
            )
        )

    def get_documents_by_source(self, source_id: str) -> list[dict[str, Any]]:
        conn = _conn(self._path)
        rows = conn.execute(
            "SELECT id, source_id, path, title, mime_type, modified_at, indexed_at, content_hash "
            "FROM documents WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        conn.close()
        cols = [
            "id",
            "source_id",
            "path",
            "title",
            "mime_type",
            "modified_at",
            "indexed_at",
            "content_hash",
        ]
        return [dict(zip(cols, r)) for r in rows]

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]] | None = None,
    ) -> None:
        if not chunks:
            return
        conn = _conn(self._path)
        sqlite_vec.register(conn)

        for i, chunk in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO chunks (id, document_id, text, position, page, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text            = excluded.text,
                    position        = excluded.position,
                    page            = excluded.page,
                    embedding_model = excluded.embedding_model
                """,
                (chunk.id, chunk.document_id, chunk.text, chunk.position, chunk.page, "mock"),
            )

        if vectors:
            for chunk, vec in zip(chunks, vectors):
                conn.execute(
                    "INSERT OR REPLACE INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                    (chunk.id, json.dumps(vec)),
                )

        conn.commit()
        conn.close()

    def get_chunk_texts(self, chunk_ids: list[str]) -> dict[str, str]:
        if not chunk_ids:
            return {}
        conn = _conn(self._path)
        placeholders = ",".join("?" * len(chunk_ids))
        rows = conn.execute(
            f"SELECT id, text FROM chunks WHERE id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        conn.close()
        return dict(rows)

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
        """ANN search over chunk vectors, join with document metadata.

        Returns results sorted by cosine similarity descending.
        """
        conn = _conn(self._path)
        sqlite_vec.register(conn)

        # Build filter for source_ids
        doc_filter = ""
        if source_ids:
            placeholders = ",".join("?" * len(source_ids))
            doc_filter = (
                f"AND d.source_id IN ({placeholders}) "
                f"AND d.id IN (SELECT document_id FROM chunks WHERE chunk_id = v.chunk_id)"
            )
            params: list[Any] = source_ids + [top_k]
        else:
            params = [top_k]

        # sqlite-vec top-k by cosine similarity desc
        rows = conn.execute(
            f"""
            SELECT
                v.chunk_id,
                d.id          AS document_id,
                d.source_id,
                d.path,
                d.title,
                d.mime_type,
                c.text,
                c.position,
                c.page,
                v.embedding
            FROM chunk_vectors v
            JOIN chunks       c ON c.id = v.chunk_id
            JOIN documents    d ON d.id = c.document_id
            {doc_filter}
            ORDER BY v.embedding <-> ? DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        results = []
        for row in rows:
            embedding = json.loads(row[8]) if row[8] else []
            score = float(_cosine(query_vector, embedding)) if embedding else 0.0
            # Build snippet: first 300 chars of text
            text = row[6] or ""
            snippet = text[:300] + ("..." if len(text) > 300 else "")
            results.append(
                {
                    "chunk_id": row[0],
                    "document_id": row[1],
                    "source_id": row[2],
                    "path": row[3],
                    "title": row[4],
                    "mime_type": row[5],
                    "text": text,
                    "snippet": snippet,
                    "position": row[7],
                    "page": row[8] if isinstance(row[8], int) else None,
                    "score": round(score, 4),
                }
            )

        conn.close()
        return results


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)