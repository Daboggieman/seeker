"""Filesystem source connector.

Mechanism (docs/build_docs/04-core-engine-specs.md section 5.1): initial full
walk on first run, incremental listing by modification time afterwards. The
watchdog live-event watcher joins when the index pipeline exists to receive
its events (open decision 4 covers its debounce strategy); until then the
pipeline polls `list_changed_items`.

Judgment calls, made 2026-10-26 and open to reversal:
- dot-prefixed files and directories are skipped by default (`.git`, editor
  droppings, cache dirs) — personal source roots are full of them and indexing
  them is noise; pass `include_hidden=True` to disable;
- symlinks are never followed and symlinked files are skipped — a source
  mount must never cause reads outside its root.

`since` is an ISO-8601 UTC timestamp string (None = everything); items are
compared by filesystem mtime converted to UTC.
"""

from __future__ import annotations

import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

from seeker.connectors.base import FetchedContent, RawItem

_UNKNOWN_MIME = "application/octet-stream"


def _since_to_epoch(since: str | None) -> float | None:
    if since is None:
        return None
    return datetime.fromisoformat(since).timestamp()


def _to_iso_utc(epoch_seconds: float) -> str:
    # Canonical "Z" form; fromisoformat reads it back fine on 3.11+.
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


class FilesystemConnector:
    """Filesystem source: recursive walk, mtime-incremental, read-only."""

    def __init__(self, root_path: str | Path, *, include_hidden: bool = False) -> None:
        root = Path(root_path)
        if not root.is_dir():
            raise NotADirectoryError(f"source root is not a directory: {root}")
        self.root = root.resolve()
        self.include_hidden = include_hidden

    # -- listing -------------------------------------------------------------

    def list_changed_items(self, since: str | None) -> list[RawItem]:
        since_epoch = _since_to_epoch(since)
        items: list[RawItem] = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            # Mutating dirnames in place prunes hidden dirs from the walk.
            if not self.include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            base = Path(dirpath)
            for name in filenames:
                if not self.include_hidden and name.startswith("."):
                    continue
                path = base / name
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                if since_epoch is not None and stat.st_mtime <= since_epoch:
                    continue
                items.append(
                    RawItem(
                        path=str(path),
                        modified_at=_to_iso_utc(stat.st_mtime),
                        size=stat.st_size,
                    )
                )
        return sorted(items, key=lambda item: item.path)

    # -- fetching ------------------------------------------------------------

    def fetch_content(self, item: RawItem) -> FetchedContent:
        resolved = Path(item.path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"item path escapes source root: {item.path}")
        mime_type = mimetypes.guess_type(resolved.name)[0] or _UNKNOWN_MIME
        return FetchedContent(content=resolved.read_bytes(), mime_type=mime_type)
