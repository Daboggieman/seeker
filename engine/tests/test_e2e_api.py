"""End-to-end API integration test.

Tests the full path: register source -> sync -> search, against synthetic fixtures.
No real files, no eval set — this is the plumbing proof for Phase 1.
The real eval set (recall@5) requires real files and a real directory (open decision 10).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from seeker.api.main import create_app


class TmpDir:
    def __init__(self) -> None:
        self.path = Path(tempfile.mkdtemp())

    def __enter__(self) -> TmpDir:
        return self

    def __exit__(self, *args: object) -> None:
        shutil.rmtree(self.path)

    def write(self, name: str, content: str) -> Path:
        p = self.path / name
        p.write_text(content, encoding="utf-8")
        return p


class TestE2EAPI:
    """Smoke test for the full engine stack, synthetic data."""

    def test_health_endpoint(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_register_source(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.post(
                "/v1/sources",
                json={
                    "source_id": "fs-test",
                    "source_type": "filesystem",
                    "config": {"root_path": str(td.path)},
                },
            )
            assert resp.status_code == 201
            assert resp.json()["id"] == "fs-test"

    def test_list_sources(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            client.post(
                "/v1/sources",
                json={
                    "source_id": "fs-test",
                    "source_type": "filesystem",
                    "config": {"root_path": str(td.path)},
                },
            )
            resp = client.get("/v1/sources")
            assert resp.status_code == 200
            sources = resp.json()
            assert len(sources) == 1
            assert sources[0]["id"] == "fs-test"

    def test_sync_then_search(self) -> None:
        with TmpDir() as td:
            # Write a document in the source directory.
            td.write(
                "budget_notes.txt",
                "The Q1 marketing budget disagreement was resolved on March 15.",
            )
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            # Register the source pointing at the temp dir.
            client.post(
                "/v1/sources",
                json={
                    "source_id": "fs-test",
                    "source_type": "filesystem",
                    "config": {"root_path": str(td.path)},
                },
            )
            # Sync — index the file.
            sync_resp = client.post("/v1/sources/fs-test/sync")
            assert sync_resp.status_code == 200
            assert sync_resp.json()["chunks_indexed"] == 1
            # Search with a vague query.
            search_resp = client.post(
                "/v1/search",
                json={"query": "Q1 marketing budget disagreement from march"},
            )
            assert search_resp.status_code == 200
            results = search_resp.json()["results"]
            assert len(results) >= 1
            # The match should point at the budget_notes.txt file.
            assert any("budget" in r["title"] or "budget" in r["path"] for r in results)
            # Score is present and in range.
            for r in results:
                assert 0.0 <= r["score"] <= 1.0

    def test_search_respects_source_filter(self) -> None:
        with TmpDir() as td:
            td.write("finance.txt", "Q1 marketing budget report")
            td.write("cooking.txt", "lasagna recipe")
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            client.post(
                "/v1/sources",
                json={
                    "source_id": "fs-test",
                    "source_type": "filesystem",
                    "config": {"root_path": str(td.path)},
                },
            )
            client.post("/v1/sources/fs-test/sync")
            # Filter to a source that does not exist.
            resp = client.post(
                "/v1/search",
                json={
                    "query": "Q1 marketing budget report",
                    "source_ids": ["nonexistent"],
                },
            )
            assert resp.status_code == 200
            assert resp.json()["results"] == []

    def test_delete_source(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            client.post(
                "/v1/sources",
                json={
                    "source_id": "fs-test",
                    "source_type": "filesystem",
                    "config": {"root_path": str(td.path)},
                },
            )
            del_resp = client.delete("/v1/sources/fs-test")
            assert del_resp.status_code == 200
            list_resp = client.get("/v1/sources")
            assert list_resp.json() == []

    def test_status_endpoint(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.get("/v1/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "healthy"
            assert "sources" in body

    def test_unknown_source_returns_404(self) -> None:
        with TmpDir() as td:
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.delete("/v1/sources/does-not-exist")
            assert resp.status_code == 404