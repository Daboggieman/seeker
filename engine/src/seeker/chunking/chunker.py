"""Document chunker.

Contract (docs/build_docs/04-core-engine-specs.md section 5.2):
- split by paragraph/section boundaries first, never fixed character counts;
- target ~300-500 tokens per chunk, ~50-token overlap between adjacent chunks;
- preserve source metadata per chunk (document id, page, position) so results
  can point back to an exact location.

Token counting is approximate (whitespace-split words); swapping in a
model-specific tokenizer later touches only `count_tokens`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    """A chunk as specified in docs/build_docs/02-data-model.md.

    `embedding_model` and `vector` are set at embed time, never here.
    """

    id: str
    document_id: str
    text: str
    position: int
    page: int | None


def count_tokens(text: str) -> int:
    """Approximate token count: whitespace-separated words.

    The approximation is deliberate for the mock-backend stage; when a real
    embedding backend lands, swap the body of this function only.
    """
    return len(text.split())


def _hard_split_words(text: str, max_tokens: int) -> list[str]:
    """Split a single oversized unit into word groups of at most max_tokens."""
    words = text.split()
    pieces = []
    for i in range(0, len(words), max_tokens):
        piece = " ".join(words[i : i + max_tokens]).strip()
        if piece:
            pieces.append(piece)
    return pieces


def _to_units(paragraphs: list[str], max_tokens: int) -> list[str]:
    """Turn paragraphs into units, each within max_tokens.

    Paragraphs that already fit stay whole (boundary-preserving). An oversized
    paragraph is split at sentence boundaries; a sentence still over the limit
    is hard-split at word boundaries as a last resort.
    """
    units: list[str] = []
    for para in paragraphs:
        if count_tokens(para) <= max_tokens:
            units.append(para)
            continue
        pieces: list[str] = []
        for sentence in _SENTENCE_SPLIT.split(para):
            sentence = sentence.strip()
            if not sentence:
                continue
            if count_tokens(sentence) <= max_tokens:
                pieces.append(sentence)
            else:
                pieces.extend(_hard_split_words(sentence, max_tokens))
        units.extend(pieces)
    return units


def _join(units: list[str]) -> str:
    return "\n\n".join(units)


def chunk_text(
    text: str,
    document_id: str,
    *,
    page: int | None = None,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Split `text` into boundary-respecting chunks of at most max_tokens.

    Splits happen at paragraph boundaries; a paragraph that alone exceeds
    max_tokens is split at sentence boundaries, then at word boundaries as a
    last resort. Adjacent chunks overlap by up to overlap_tokens, taken from
    the tail of the previous chunk (whole units when they fit, otherwise the
    trailing words). Overlap is capped so the max_tokens invariant always holds.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must satisfy 0 <= overlap_tokens < max_tokens")

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text.strip()) if p.strip()]
    units = _to_units(paragraphs, max_tokens)

    chunks: list[Chunk] = []
    carry: list[str] = []

    i = 0
    while i < len(units):
        pending = list(carry)
        while i < len(units) and count_tokens(_join(pending + [units[i]])) <= max_tokens:
            pending.append(units[i])
            i += 1
        # Defensive: an empty carry with no room must never yield an empty chunk.
        if not pending:
            pending.append(units[i])
            i += 1
        chunks.append(
            Chunk(
                id=uuid.uuid4().hex,
                document_id=document_id,
                text=_join(pending).strip(),
                position=len(chunks),
                page=page,
            )
        )
        if i >= len(units):
            break
        # Overlap: carry the tail of this chunk into the next one. Word-level
        # carry (not whole units) — a unit is usually larger than the overlap
        # budget, so unit-granularity carrying would usually carry nothing.
        next_unit_tokens = count_tokens(units[i])
        room = max_tokens - next_unit_tokens
        carry = _word_carry_fallback(_join(pending), min(overlap_tokens, room))

    return chunks


def _word_carry_fallback(prev_text: str, limit: int) -> list[str]:
    words = prev_text.split()
    if limit <= 0 or not words:
        return []
    return [" ".join(words[-limit:])]
