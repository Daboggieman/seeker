"""Source connector interface.

Contract (docs/build_docs/04-core-engine-specs.md section 5.1,
docs/handover_docs/02-engine-conventions.md):
- every connector implements `list_changed_items(since) -> [RawItem]` and
  `fetch_content(item) -> bytes + mime_type`; a connector that cannot express
  these is the wrong connector;
- connectors enumerate and fetch bytes — text extraction, hashing, chunking
  all happen downstream in the index pipeline;
- source mounts are read-only (docs/handover_docs/02-engine-conventions.md
  security rules): no connector ever writes to a source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawItem:
    """One changed source item, as a connector reports it."""

    path: str
    modified_at: str  # ISO-8601 UTC
    size: int


@dataclass(frozen=True)
class FetchedContent:
    """The bytes and mime type behind a RawItem."""

    content: bytes
    mime_type: str


class SourceConnector(Protocol):
    """Interface every source connector implements."""

    def list_changed_items(self, since: str | None) -> list[RawItem]:
        """Items modified after `since` (ISO-8601 UTC), or all items if None.

        None means the initial full walk. Timestamps compare against each
        item's modification time in UTC.
        """
        ...

    def fetch_content(self, item: RawItem) -> FetchedContent:
        """Fetch an item's bytes and mime type.

        Raises FileNotFoundError if the item vanished between listing and
        fetch; the pipeline decides whether that is an error or a skip.
        """
        ...
