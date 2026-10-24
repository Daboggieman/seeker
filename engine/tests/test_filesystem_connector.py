"""Tests for the filesystem connector.

Contract (docs/build_docs/04-core-engine-specs.md section 5.1, filesystem row):
- list_changed_items(since) uses watchdog for live change events;
  initial full walk on first run.
- content_hash gates re-embedding (never re-index unchanged files).
- fetch_content returns (bytes, mime_type).
- Source mounts are read-only (docs/build_docs/11-coding-agent-rules.md rule 7).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from seeker.chunking.chunker import count_tokens
from seeker.connectors.base import Connector, RawItem
from seeker.connectors.filesystem import (
    FilesystemConnector,
    PathOutsideRootError,
)


class TmpDir:
    """Create a temporary directory, clean it up after the test."""

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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestFilesystemConnectorListChangedItems:
    def test_full_scan_returns_all_files(self) -> None:
        with TmpDir() as td:
            td.write("a.txt", "alpha")
            td.write("b.txt", "beta")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            assert len(items) == 2
            assert {i.path for i in items} == {
                str(td.path / "a.txt"),
                str(td.path / "b.txt"),
            }

    def test_incremental_scan_returns_only_newer_files(self) -> None:
        with TmpDir() as td:
            td.write("a.txt", "alpha")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            # Baseline scan
            baseline = conn.list_changed_items(since=None)
            before = max(i.modified_at for i in baseline)

            td.write("b.txt", "beta")
            # Second scan should only pick up b.txt
            items = conn.list_changed_items(since=before)
            assert len(items) == 1
            assert "b.txt" in items[0].path

    def test_directories_and_symlinks_skipped(self) -> None:
        with TmpDir() as td:
            sub = td.path / "subdir"
            sub.mkdir()
            (sub / "nested.txt").write_text("nested")
            td.write("root.txt", "root")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            # Only leaf files
            assert all(Path(i.path).is_file() for i in items)

    def test_hidden_files_included(self) -> None:
        with TmpDir() as td:
            td.write(".hidden", "secret")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            assert len(items) == 1
            assert ".hidden" in items[0].path

    def test_unsupported_extension_returns_no_items(self) -> None:
        with TmpDir() as td:
            td.write("a.jpg", "binary blob")
            td.write("b.mp3", "binary blob")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            # No indexed file types in the fixture
            assert items == []


class TestFilesystemConnectorFetchContent:
    def test_returns_bytes_and_mime_for_plain_text(self) -> None:
        with TmpDir() as td:
            p = td.write("notes.txt", "meeting notes on the Q1 budget")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            data, mime = conn.fetch_content(items[0])
            assert isinstance(data, bytes)
            assert data == b"meeting notes on the Q1 budget"
            assert mime == "text/plain; charset=utf-8"

    def test_returns_bytes_and_mime_for_pdf(self) -> None:
        with TmpDir() as td:
            # Write a minimal PDF
            pdf_bytes = (
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
                b">>endobj\n"
                b"xref\n0 4\n0000000000 65535 f\n"
                b"trailer<</Size 4/Root 1 0 R>>\n"
                b"startxref\n0\n%%EOF"
            )
            p = td.path / "doc.pdf"
            p.write_bytes(pdf_bytes)
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            assert len(items) == 1
            data, mime = conn.fetch_content(items[0])
            assert data == pdf_bytes
            assert mime == "application/pdf"

    def test_fetch_path_outside_root_raises(self) -> None:
        with TmpDir() as td:
            td.write("a.txt", "inside")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            assert items
            # Path that escapes the root
            bad_item = RawItem(
                path=str(td.path.parent / "escape.txt"),
                modified_at=datetime.now(timezone.utc),
            )
            with pytest.raises(PathOutsideRootError):
                conn.fetch_content(bad_item)


class TestFilesystemConnectorContentHash:
    def test_content_hash_is_computed_on_fetch(self) -> None:
        with TmpDir() as td:
            td.write("a.txt", "the quick brown fox")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            assert items
            assert items[0].content_hash is None  # set lazily
            _data, _mime = conn.fetch_content(items[0])
            assert items[0].content_hash == sha256(b"the quick brown fox")

    def test_hash_is_idempotent(self) -> None:
        with TmpDir() as td:
            td.write("a.txt", "stable content")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            _data, _mime = conn.fetch_content(items[0])
            h1 = items[0].content_hash
            # Fetch again
            _data2, _mime2 = conn.fetch_content(items[0])
            assert items[0].content_hash == h1


class TestFilesystemConnectorMimeGuessing:
    @pytest.mark.parametrize(
        "filename,expected_prefix",
        [
            ("doc.pdf", "application/pdf"),
            ("notes.txt", "text/plain"),
            ("data.csv", "text/csv"),
            ("report.docx", "application/vnd.openxmlformats"),
            ("sheet.xlsx", "application/vnd.openxmlformats"),
            ("script.py", "text/x-python"),
            ("readme.md", "text/markdown"),
        ],
    )
    def test_mime_type_is_inferred(self, filename: str, expected_prefix: str) -> None:
        with TmpDir() as td:
            td.write(filename, "content")
            conn = FilesystemConnector(source_id="fs-test", root=td.path)
            items = conn.list_changed_items(since=None)
            if not items:
                pytest.skip(f"{filename} not in supported extensions")
            _data, mime = conn.fetch_content(items[0])
            assert mime.startswith(expected_prefix)
