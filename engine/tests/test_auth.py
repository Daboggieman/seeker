"""Auth behavior tests.

Verifies the bearer-token gate: protected routes reject missing/wrong tokens
and accept the right one, while /health stays open. These tests run with
SEEKER_TOKEN set, so they exercise the enforced path.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from seeker.api import auth as auth_module
from seeker.api.main import create_app


class TmpDir:
    def __init__(self) -> None:
        self.path = Path(tempfile.mkdtemp())

    def __enter__(self) -> TmpDir:
        return self

    def __exit__(self, *args: object) -> None:
        shutil.rmtree(self.path)


class _TokenEnv:
    """Set/unset SEEKER_TOKEN and re-read the module-level flag."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._old: str | None = None

    def __enter__(self) -> _TokenEnv:
        self._old = auth_module._TOKEN
        auth_module._TOKEN = self._token
        auth_module.AUTH_ENABLED = True
        return self

    def __exit__(self, *args: object) -> None:
        auth_module._TOKEN = self._old or ""
        auth_module.AUTH_ENABLED = bool(auth_module._TOKEN)


def _client_with_token(td_path: Path, token: str | None) -> tuple:
    """Build a TestClient; when token is given, send it on every request."""
    app = create_app(td_path / "test.db")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client, headers


class TestAuthEnforced:
    def test_health_open_without_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            assert client.get("/health").status_code == 200

    def test_sources_reject_missing_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            assert client.get("/v1/sources").status_code == 401

    def test_sources_reject_wrong_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.get("/v1/sources", headers={"Authorization": "Bearer wrong"})
            assert resp.status_code == 401

    def test_sources_accept_correct_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.get("/v1/sources", headers={"Authorization": "Bearer secret-token"})
            assert resp.status_code == 200
            assert resp.json() == []

    def test_search_requires_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            resp = client.post("/v1/search", json={"query": "anything"})
            assert resp.status_code == 401
            resp = client.post(
                "/v1/search",
                json={"query": "anything"},
                headers={"Authorization": "Bearer secret-token"},
            )
            assert resp.status_code == 200

    def test_sync_and_delete_require_token(self) -> None:
        with TmpDir() as td, _TokenEnv("secret-token"):
            app = create_app(td.path / "test.db")
            client = TestClient(app)
            assert client.post("/v1/sources/fs/sync").status_code == 401
            assert client.delete("/v1/sources/fs").status_code == 401
            assert client.get("/v1/status").status_code == 401


class TestAuthDisabled:
    def test_no_token_env_means_open(self) -> None:
        with TmpDir() as td:
            # Simulate unset SEEKER_TOKEN.
            with _TokenEnv(""):
                auth_module.AUTH_ENABLED = False
                app = create_app(td.path / "test.db")
                client = TestClient(app)
                resp = client.get("/v1/sources")
                assert resp.status_code == 200
            # Restore.
            auth_module.AUTH_ENABLED = bool(auth_module._TOKEN)
