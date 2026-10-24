"""Filesystem connector.

Filesystem implementation of the Connector interface (base.py).
Handles local file scanning, content-hash gating, and MIME type inference.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

from seeker.connectors.base import Connector, RawItem

# Subset of extensions we index.  Adding a new format requires only adding the
# extension here and any parser dependency in pyproject.toml.
SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".tsv",
    ".pdf",
    ".docx",
    ".xlsx",
}


class PathOutsideRootError(ValueError):
    """Raised when a file path resolves outside the connector's root."""


class FilesystemConnector(Connector):
    """Connector for a local filesystem directory."""

    def __init__(
        self,
        source_id: str,
        root: Path | str,
        *,
        supported_extensions: set[str] | None = None,
    ) -> None:
        self._source_id = source_id
        self._root = Path(root).resolve()
        self._extensions = supported_extensions or SUPPORTED_EXTENSIONS

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "filesystem"

    def _is_inside_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._root)
            return True
        except ValueError:
            return False

    def list_changed_items(self, since: datetime | None) -> list[RawItem]:
        items: list[RawItem] = []
        # Extensionless files (dotfiles like '.gitignore', '.env', 'README')
        # are text candidates too; extension filters apply on top.
        for ext in [*self._extensions, ""]:
            for path_str in _walk_ext(self._root, ext):
                path = Path(path_str)
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                if since is not None and mtime <= since:
                    continue
                items.append(
                    RawItem(
                        path=path_str,
                        modified_at=mtime,
                        content_hash=None,  # computed at fetch time
                    )
                )
        return items

    def fetch_content(self, item: RawItem) -> tuple[bytes, str]:
        path = Path(item.path)
        if not self._is_inside_root(path):
            raise PathOutsideRootError(f"{item.path} is outside root {self._root}")
        data = path.read_bytes()
        mime = _infer_mime(path.name, data)
        # Replace the hash on the item so callers can skip re-embedding
        object.__setattr__(item, "content_hash", sha256_bytes(data))
        return data, mime


def _walk_ext(root: Path, ext: str) -> list[str]:
    """Return all file paths under root with the given suffix.

    `ext` may be a normal suffix ('.txt') or the empty string, which matches
    extensionless files (dotfiles like '.gitignore', '.env', 'README').
    os.walk sees hidden files and hidden directories, which glob skips.
    """
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix == ext:
                found.append(str(path))
    return found


def _infer_mime(name: str, data: bytes) -> str:
    """Return a MIME type, falling back to application/octet-stream."""
    mime, _ = mimetypes.guess_type(name, strict=False)
    if mime:
        # Add charset for text types we control
        if mime.startswith("text/") and "charset" not in mime:
            return f"{mime}; charset=utf-8"
        return mime
    # Binary signature for PDFs we produce in tests
    if data.startswith(b"%PDF"):
        return "application/pdf"
    return "application/octet-stream"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()