"""Seeker eval set runner — recall@5 over the queries in queries.json.

The quality bar (docs/build_docs/08-testing-and-validation.md): ~20 queries
with a known correct document each; every change to chunking, embedding, or
the query pipeline re-runs this, and a lower recall@5 does not ship.

Usage (from engine/, venv active):
    SEEKER_EMBEDDING_BACKEND=openai \
    SEEKER_EMBEDDING_MODEL=nomic-embed-text \
    SEEKER_EMBEDDING_BASE_URL=http://localhost:11434 \
    .venv/bin/python eval/run_eval.py

The corpus is the source tree at EVAL_ROOT, indexed into a dedicated eval DB
(SEEKER_EVAL_DB, default data/eval.db — never the main index) with dependency
and build trees excluded. Incremental syncs make re-runs cheap.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from seeker.config import load_settings
from seeker.connectors.filesystem import FilesystemConnector
from seeker.factories import build_embedding_backend
from seeker.pipeline.indexer import IndexPipeline
from seeker.service import Engine
from seeker.store.store import VectorStore

EVAL_DIR = Path(__file__).parent
QUERIES_FILE = EVAL_DIR / "queries.json"
EVAL_ROOT = "/home/recoding/gsmhub"
EVAL_EXCLUDES = {"node_modules", "dist", "playwright-report", "test-results"}
TOP_K = 5


async def main() -> int:
    settings = load_settings()
    db_path = Path(os.environ.get("SEEKER_EVAL_DB", "data/eval.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = VectorStore(str(db_path), dimensions=settings.embedding_dimensions)
    backend = build_embedding_backend(settings)
    engine = Engine(store, backend, IndexPipeline(store, backend))

    # -- index (incremental after the first run) -----------------------------
    connector = FilesystemConnector(EVAL_ROOT, exclude_dirs=EVAL_EXCLUDES)
    started = time.monotonic()
    stats = await engine.pipeline.sync(connector, source_id="eval-gsmhub")
    elapsed = time.monotonic() - started
    failed = {f.path: f.reason for f in stats.failed}
    print(
        f"index: {stats.indexed} indexed, {stats.skipped_unchanged} unchanged, "
        f"{stats.unsupported} unsupported, {len(failed)} failed "
        f"({elapsed:.1f}s, model={backend.model_name}, db={db_path})"
    )
    for path, reason in failed.items():
        print(f"  FAILED {path}: {reason}")

    # -- run the queries ------------------------------------------------------
    if not QUERIES_FILE.exists():
        print("queries.json missing — indexed only, no queries run")
        return 0
    queries = json.loads(QUERIES_FILE.read_text())
    hits = 0
    misses: list[tuple[str, str, list[str]]] = []
    per_query: list[tuple[str, bool, float]] = []
    for entry in queries:
        expected = str(Path(EVAL_ROOT) / entry["path"])
        results = await engine.search(entry["query"], top_k=TOP_K)
        paths = [r["path"] for r in results]
        found = expected in paths
        best_score = max((r["score"] for r in results), default=0.0)
        per_query.append((entry["query"], found, best_score))
        if found:
            hits += 1
        else:
            misses.append((entry["query"], entry["path"], paths))

    print(f"\nrecall@{TOP_K}: {hits}/{len(queries)} = {hits / len(queries):.2f}\n")
    for query, found, score in per_query:
        mark = "HIT " if found else "MISS"
        print(f"  [{mark}] {score:.3f}  {query}")
    if misses:
        print("\nmisses (query → expected, got):")
        for query, expected, paths in misses:
            got = ", ".join(Path(p).name for p in paths) or "(no results)"
            print(f"  {query!r}\n    expected {Path(expected).name}\n    got      {got}")
    return 0  # the run itself succeeded; recall@5 is the output, not an exit code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
