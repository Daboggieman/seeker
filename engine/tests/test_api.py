"""API tests: the REST surface against a fully wired app (mock embeddings,
tmp store), through Starlette's TestClient (ASGI, no network). Every route is
covered with valid, invalid, and unauthenticated calls (docs/build_docs/
08-testing-and-validation.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from seeker.api.app import create_app
from seeker.config import EngineSettings

DEV_TOKEN = "dev-insecure-token"
AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}


def make_client(
    tmp_path, token: str = DEV_TOKEN, base_url: str = "http://testserver"
) -> TestClient:
    app = create_app(
        EngineSettings(
            db_path=str(tmp_path / "api.db"),
            embedding_dimensions=8,
            api_token=token,
        )
    )
    return TestClient(app, raise_server_exceptions=False, base_url=base_url)


@pytest.fixture
def client(tmp_path) -> TestClient:
    return make_client(tmp_path)


def make_source_dir(tmp_path, name: str = "docs", text: str | None = None) -> str:
    docs = tmp_path / name
    docs.mkdir(exist_ok=True)
    (docs / "budget.txt").write_text(text or "quarterly budget disagreement memo")
    (docs / "recipes.txt").write_text("sourdough needs flour and time")
    return str(docs)


def add_and_sync(client: TestClient, source_id: str, root_path: str) -> dict:
    resp = client.post(
        "/v1/sources", json={"source_id": source_id, "root_path": root_path}, headers=AUTH
    )
    assert resp.status_code == 201, resp.text
    resp = client.post(f"/v1/sources/{source_id}/sync", headers=AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMcpOverHttp:
    """The MCP shim is mounted on the same app; its transport must actually work."""

    def test_initialize_handshake_succeeds(self, tmp_path) -> None:
        # base_url with an explicit port so the Host header carries one and
        # passes the SDK's DNS-rebinding wildcard ("127.0.0.1:*" requires the
        # colon — a bare "127.0.0.1" host is rejected 421); TestClient's
        # default host "testserver" would be rejected as well.
        with make_client(tmp_path, base_url="http://127.0.0.1:8420") as client:
            resp = client.post(  # `with` runs the app lifespan, which starts
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                },
                headers={  # /mcp is token-gated like every REST route
                    "Accept": "application/json, text/event-stream",
                    **AUTH,
                },
            )
        assert resp.status_code == 200
        assert "seeker" in resp.text  # serverInfo.name from the initialize result

    def test_unauthenticated_mcp_rejected(self, tmp_path) -> None:
        # The MCP mount has no route-level auth of its own; the middleware
        # must supply the bearer-token gate (same shape as the REST 401s).
        with make_client(tmp_path, base_url="http://127.0.0.1:8420") as client:
            resp = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                headers={"Accept": "application/json, text/event-stream"},
            )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "UNAUTHORIZED"


class TestAuth:
    def test_missing_token_is_401(self, tmp_path) -> None:
        client = make_client(tmp_path)
        resp = client.post("/v1/search", json={"query": "anything"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_wrong_token_is_401(self, tmp_path) -> None:
        client = make_client(tmp_path)
        resp = client.post(
            "/v1/search", json={"query": "anything"}, headers={"Authorization": "Bearer wrong"}
        )
        assert resp.status_code == 401

    def test_custom_token_replaces_default(self, tmp_path) -> None:
        client = make_client(tmp_path, token="custom-secret")
        resp = client.post("/v1/search", json={"query": "x"}, headers=AUTH)
        assert resp.status_code == 401
        resp = client.post(
            "/v1/search", json={"query": "x"}, headers={"Authorization": "Bearer custom-secret"}
        )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/v1/search"),
            ("get", "/v1/sources"),
            ("post", "/v1/sources"),
            ("post", "/v1/sources/docs/sync"),
            ("delete", "/v1/sources/docs"),
            ("get", "/v1/status"),
        ],
    )
    def test_every_route_rejects_anonymous(
        self, client: TestClient, method: str, path: str
    ) -> None:
        resp = client.request(method, path, json={"query": "x", "root_path": "/tmp"})
        assert resp.status_code == 401

    def test_health_is_anonymous(self, client: TestClient) -> None:
        resp = client.get("/v1/health")
        assert resp.status_code == 200


class TestRequestId:
    def test_response_carries_request_id(self, client: TestClient) -> None:
        resp = client.get("/v1/health")
        assert resp.headers["X-Request-Id"]

    def test_client_request_id_is_echoed(self, client: TestClient) -> None:
        resp = client.get("/v1/health", headers={**AUTH, "X-Request-Id": "my-id-42"})
        assert resp.headers["X-Request-Id"] == "my-id-42"


class TestSearch:
    def test_empty_index_returns_empty_results(self, client: TestClient) -> None:
        resp = client.post("/v1/search", json={"query": "budget"}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"results": []}

    def test_search_after_sync_ranks_matching_document_first(self, tmp_path) -> None:
        client = make_client(tmp_path)
        add_and_sync(client, "docs", make_source_dir(tmp_path))
        resp = client.post(
            "/v1/search",
            json={"query": "quarterly budget disagreement memo"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results, "index has two documents; a query must return hits"
        assert results[0]["path"].endswith("budget.txt")

    def test_result_shape_matches_data_model(self, tmp_path) -> None:
        client = make_client(tmp_path)
        add_and_sync(client, "docs", make_source_dir(tmp_path))
        resp = client.post("/v1/search", json={"query": "sourdough"}, headers=AUTH)
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert set(result) == {
            "chunk_id",
            "document_id",
            "title",
            "path",
            "snippet",
            "score",
            "source_id",
            "page",
            "position",
        }
        assert -1.0 <= result["score"] <= 1.0
        assert result["source_id"] == "docs"

    def test_top_k_is_respected(self, tmp_path) -> None:
        client = make_client(tmp_path)
        add_and_sync(client, "docs", make_source_dir(tmp_path))
        resp = client.post(
            "/v1/search", json={"query": "memo", "top_k": 1}, headers=AUTH
        )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

    def test_filter_restricts_to_one_source(self, tmp_path) -> None:
        client = make_client(tmp_path)
        add_and_sync(client, "work", make_source_dir(tmp_path, "work"))
        add_and_sync(client, "home", make_source_dir(tmp_path, "home"))

        resp = client.post(
            "/v1/search",
            json={"query": "budget", "filters": {"source_id": ["home"]}},
            headers=AUTH,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results
        assert {r["source_id"] for r in results} == {"home"}

    def test_empty_query_is_422(self, client: TestClient) -> None:
        resp = client.post("/v1/search", json={"query": ""}, headers=AUTH)
        assert resp.status_code == 422

    def test_whitespace_query_is_422_validation_error(self, client: TestClient) -> None:
        resp = client.post("/v1/search", json={"query": "   "}, headers=AUTH)
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


class TestSources:
    def test_create_source_returns_record(self, tmp_path, client: TestClient) -> None:
        root = make_source_dir(tmp_path)
        resp = client.post(
            "/v1/sources", json={"source_id": "docs", "root_path": root}, headers=AUTH
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "docs"
        assert body["type"] == "filesystem"
        assert body["root_path"] == root
        assert body["last_synced_at"] is None
        assert body["status"] == "idle"

    def test_create_source_with_missing_dir_is_422(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/sources",
            json={"source_id": "x", "root_path": "/nonexistent/root"},
            headers=AUTH,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"

    def test_list_sources_includes_created(self, tmp_path, client: TestClient) -> None:
        root = make_source_dir(tmp_path)
        client.post("/v1/sources", json={"source_id": "docs", "root_path": root}, headers=AUTH)
        resp = client.get("/v1/sources", headers=AUTH)
        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == ["docs"]

    def test_sync_returns_stats_and_updates_source(self, tmp_path, client: TestClient) -> None:
        root = make_source_dir(tmp_path)
        client.post("/v1/sources", json={"source_id": "docs", "root_path": root}, headers=AUTH)
        resp = client.post("/v1/sources/docs/sync", headers=AUTH)
        assert resp.status_code == 200
        stats = resp.json()
        assert set(stats) == {"indexed", "skipped_unchanged", "unsupported", "pruned", "failed"}
        assert stats["indexed"] == 2
        assert stats["failed"] == []

        listed = client.get("/v1/sources", headers=AUTH).json()[0]
        assert listed["last_synced_at"] is not None
        assert listed["status"] == "idle"

    def test_sync_unknown_source_is_404(self, client: TestClient) -> None:
        resp = client.post("/v1/sources/nope/sync", headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "SOURCE_NOT_FOUND"

    def test_sync_failure_carries_diagnosis(self, tmp_path, client: TestClient) -> None:
        """A failing file surfaces path/error/reason/suggestion, not a bare path."""
        import httpx

        from seeker.pipeline.indexer import IndexPipeline

        root = make_source_dir(tmp_path)
        client.post(
            "/v1/sources", json={"source_id": "docs", "root_path": root}, headers=AUTH
        )

        class UnreachableBackend:
            model_name = "mock"
            dimensions = 8

            async def embed_documents(self, texts):
                raise httpx.ConnectError("All connection attempts failed")

            async def embed_query(self, text):
                raise httpx.ConnectError("All connection attempts failed")

        engine = client.app.state.engine
        engine.pipeline = IndexPipeline(engine.store, UnreachableBackend())

        resp = client.post("/v1/sources/docs/sync", headers=AUTH)
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["indexed"] == 0
        failure = stats["failed"][0]
        assert failure["path"].endswith(".txt")
        assert "ConnectError" in failure["error"]
        assert failure["reason"] == "embedding endpoint unreachable"
        assert "ollama serve" in failure["suggestion"]

    def test_delete_source_removes_index(self, tmp_path, client: TestClient) -> None:
        add_and_sync(client, "docs", make_source_dir(tmp_path))
        resp = client.delete("/v1/sources/docs", headers=AUTH)
        assert resp.status_code == 204
        assert client.get("/v1/sources", headers=AUTH).json() == []
        search = client.post("/v1/search", json={"query": "budget"}, headers=AUTH)
        assert search.json()["results"] == []

    def test_delete_unknown_source_is_404(self, client: TestClient) -> None:
        resp = client.delete("/v1/sources/nope", headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "SOURCE_NOT_FOUND"


class TestStatus:
    def test_status_counts_and_sources(self, tmp_path, client: TestClient) -> None:
        add_and_sync(client, "docs", make_source_dir(tmp_path))
        resp = client.get("/v1/status", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["embedding_model"] == "mock"
        assert body["documents"] == 2
        assert body["chunks"] >= 2
        assert body["sources"][0]["id"] == "docs"
