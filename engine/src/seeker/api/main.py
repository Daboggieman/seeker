"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from seeker.api.routes import init_api, router
from seeker.embeddings.backends import MockEmbeddingBackend
from seeker.store.index import IndexStore


def create_app(db_path: Path, host: str = "0.0.0.0", port: int = 8420) -> FastAPI:
    store = IndexStore(db_path)
    store.init()
    backend = MockEmbeddingBackend()

    app = FastAPI(title="Seeker", description="Self-hosted semantic search engine")
    app.include_router(router)

    init_api(store, backend)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app(Path("seeker.db"))
    uvicorn.run(app, host="0.0.0.0", port=8420)