"""API tests: the REST surface against a fully wired app (mock embeddings,
tmp store), via httpx's ASGI transport. No network."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from seeker.api.app import create_app
from seeker.config import EngineSettings

DEV_TOKEN = "dev-insecure-token"
AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}


def make_client(tmp_path, token: str | None = DEV_TOKEN) -> TestClient:
    app = create_app(
        EngineSettings(db_path=str(tmp_path / "api.db"), embedding_dimensions=8)
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(tmp_path):
    app = create_app(
        EngineSettings(db_path=str(tmp_path / "api.db"), embedding_dimensions=8)
    )
    return httpx.Client(
        transport=httpx.ASGITransport(app=app), base_url="http://engine", headers=AUTH
    )


def make_source_dir(tmp_path) -> str:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "budget.txt").write_text("quarterly budget disagreement memo")
    (docs / "recipes.txt").write_text("sourdough needs flour and time")
    return str(docs)


class TestAuth:
    def test_missing_token_is_401(self, tmp_path) -> None:
        client = make_client(tmp_path, token=None)
        resp = client.post("/v1/search", json={"query": "anything"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_wrong_token_is_401(self, tmp_path) -> None:
        client = make_client(tmp_path, token="wrong")
        resp = client.post("/v1/search", json={"query": "anything"})
        assert resp.status_code == 401

    def test_health_is_anonymous(self, client: httpx.Client) -> None:
        resp = client.get("/v1/health")
        assert resp.status_code == 200


class TestRequestId:
    def test_response_carries_request_id(self, client: httpx.Client) -> None:
        resp = client.get("/v1/health")
        assert resp.headers["X-Request-Id"]

    def test_client_request_id_is_echoed(self, client: httpx.Client) -> None:
        resp = client.get("/v1/health", headers={**AUTH, "X-Request-Id": "my-id-42"})
        assert resp.headers["X-Request-Id"] == "my-id-42"
