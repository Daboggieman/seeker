"""Unit tests for the filesystem connector.

Contract: `list_changed_items(since) -> [RawItem]`, `fetch_content(item) ->
FetchedContent`. No network; all against tmpfs via pytest's tmp_path fixture.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import pytest

from seeker.connectors.base import RawItem
from seeker.connectors.filesystem import FilesystemConnector


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def touch(path: str, mtime: float) -> None:
    """Create a file and set its modification time."""
    with open(path, "w") as fh:
        fh.write("x")
    os.utime(path, (mtime, mtime))


class TestConstruction:
    def test_missing_root_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        with pytest.raises(NotADirectoryError):
            FilesystemConnector("/not/a/dir")

    def test_file_root_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        f = tmp_path / "file.txt"
        f.write_text("")
        with pytest.raises(NotADirectoryError):
            FilesystemConnector(f)


class TestListAll:
    def test_returns_all_items_on_first_run(self, tmp_path: pytest.TempPathFactory) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        touch(str(tmp_path / "a.txt"), time.time())
        touch(str(sub / "b.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        items = connector.list_changed_items(None)
        paths = {i.path for i in items}
        assert str(tmp_path / "a.txt") in paths
        assert str(sub / "b.txt") in paths

    def test_sorted_by_path(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / "z.txt"), time.time())
        touch(str(tmp_path / "a.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        items = connector.list_changed_items(None)
        assert [os.path.basename(i.path) for i in items] == ["a.txt", "z.txt"]

    def test_includes_modified_at_and_size(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / "f.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        [item] = connector.list_changed_items(None)
        assert item.modified_at.endswith("Z")
        assert item.size == 1

    def test_hidden_files_excluded_by_default(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / ".hidden"), time.time())
        touch(str(tmp_path / "visible.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        paths = {os.path.basename(i.path) for i in connector.list_changed_items(None)}
        assert ".hidden" not in paths
        assert "visible.txt" in paths

    def test_hidden_dirs_excluded_by_default(self, tmp_path: pytest.TempPathFactory) -> None:
        hidden = tmp_path / ".hidden_dir"
        hidden.mkdir()
        touch(str(hidden / "f.txt"), time.time())
        visible = tmp_path / "visible"
        visible.mkdir()
        touch(str(visible / "f.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        paths = {i.path for i in connector.list_changed_items(None)}
        assert str(hidden / "f.txt") not in paths
        assert str(visible / "f.txt") in paths

    def test_include_hidden_returns_dot_files(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / ".secret"), time.time())
        connector = FilesystemConnector(tmp_path, include_hidden=True)
        names = {os.path.basename(i.path) for i in connector.list_changed_items(None)}
        assert ".secret" in names

    def test_symlinked_file_excluded(self, tmp_path: pytest.TempPathFactory) -> None:
        real = tmp_path / "real.txt"
        touch(str(real), time.time())
        os.symlink(str(real), str(tmp_path / "link.txt"))
        connector = FilesystemConnector(tmp_path)
        names = {os.path.basename(i.path) for i in connector.list_changed_items(None)}
        assert "real.txt" in names
        assert "link.txt" not in names


class TestIncrementalSync:
    def test_since_filters_older_files(self, tmp_path: pytest.TempPathFactory) -> None:
        old = time.time() - 100
        touch(str(tmp_path / "old.txt"), old)
        touch(str(tmp_path / "new.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        since = _iso(old + 1)
        items = connector.list_changed_items(since)
        names = {os.path.basename(i.path) for i in items}
        assert "new.txt" in names
        assert "old.txt" not in names

    def test_since_exact_boundary_excludes_modified_at_same_moment(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        t = time.time()
        touch(str(tmp_path / "f.txt"), t)
        connector = FilesystemConnector(tmp_path)
        items = connector.list_changed_items(_iso(t))
        assert items == []  # modified_at exactly at since is already indexed

    def test_since_none_returns_everything(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / "old.txt"), time.time() - 86400)
        touch(str(tmp_path / "new.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        assert len(connector.list_changed_items(None)) == 2


class TestFetchContent:
    def test_fetch_returns_bytes_and_mime(self, tmp_path: pytest.TempPathFactory) -> None:
        f = tmp_path / "doc.txt"
        f.write_bytes(b"hello world")
        connector = FilesystemConnector(tmp_path)
        [item] = connector.list_changed_items(None)
        fc = connector.fetch_content(item)
        assert fc.content == b"hello world"
        assert fc.mime_type == "text/plain"

    def test_fetch_mime_for_markdown(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "readme.md").write_bytes(b"# Hi")
        connector = FilesystemConnector(tmp_path)
        [item] = connector.list_changed_items(None)
        # Python 3.12 includes text/markdown; fall back to text/plain if not.
        assert "text" in connector.fetch_content(item).mime_type

    def test_fetch_unknown_extension_falls_back_to_octet_stream(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        (tmp_path / "artifact.xyzzy").write_bytes(b"data")
        connector = FilesystemConnector(tmp_path)
        [item] = connector.list_changed_items(None)
        assert connector.fetch_content(item).mime_type == "application/octet-stream"

    def test_fetch_path_outside_root_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        connector = FilesystemConnector(tmp_path)
        fake = RawItem(path="/etc/passwd", modified_at=iso_now(), size=1)
        with pytest.raises(ValueError, match="escapes source root"):
            connector.fetch_content(fake)

    def test_fetch_missing_file_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        touch(str(tmp_path / "f.txt"), time.time())
        connector = FilesystemConnector(tmp_path)
        [item] = connector.list_changed_items(None)
        item.path  # consumed
        os.unlink(item.path)
        with pytest.raises(FileNotFoundError):
            connector.fetch_content(item)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
