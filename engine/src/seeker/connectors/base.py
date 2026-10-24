"""Connector interface.

Each connector implements the common interface (docs/build_docs/04-core-engine-specs.md
section 5.1):
  list_changed_items(since) -> list[RawItem]
  fetch_content(item) -> bytes, mime_type
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RawItem:
    """A document found by the connector, before content is fetched."""

    path: str  # the source-specific identifier (file path, Drive file ID, etc.)
    modified_at: datetime
    content_hash: str | None = None  # SHA-256; None = fetch to determine


class Connector(ABC):
    """Abstract base for all connectors.  Subclass for each source type."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique id for this source, e.g. 'fs-home' or 'drive-personal'."""
        ...

    @property
    def source_type(self) -> str:
        """Source type string: 'filesystem', 'gdrive', 'notion', 'imap'."""
        return self.__class__.__name__.replace("Connector", "").lower()

    @abstractmethod
    def list_changed_items(self, since: datetime | None) -> list[RawItem]:
        """Return all items modified since `since` (None = full scan)."""
        ...

    @abstractmethod
    def fetch_content(self, item: RawItem) -> tuple[bytes, str]:
        """Fetch the document body and return (bytes, mime_type)."""
        ...
