"""Unit tests for the chunker.

The chunker contract (build_docs/04-core-engine-specs.md §5.2):
- Split by paragraph/section boundaries first, not fixed character counts.
- Target ~300-500 tokens per chunk, ~50-token overlap between adjacent chunks.
- Preserve source metadata per chunk (document id, page, position) so results can
  point back to an exact location.
"""

from __future__ import annotations

import pytest

from seeker.chunking.chunker import Chunk, chunk_text, count_tokens


def para(words: int, seed: str = "w") -> str:
    """A paragraph of `words` placeholder words."""
    return " ".join(f"{seed}{i}" for i in range(words))


class TestCountTokens:
    def test_counts_whitespace_separated_words(self) -> None:
        assert count_tokens("one two three") == 3

    def test_collapses_whitespace(self) -> None:
        assert count_tokens("  one\n\ntwo\tthree  ") == 3

    def test_empty_string_is_zero(self) -> None:
        assert count_tokens("") == 0


class TestBasicChunking:
    def test_short_text_yields_single_chunk(self) -> None:
        chunks = chunk_text("a short document body", document_id="doc-1")
        assert len(chunks) == 1
        assert chunks[0].text == "a short document body"
        assert chunks[0].document_id == "doc-1"
        assert chunks[0].position == 0
        assert chunks[0].page is None

    def test_page_metadata_is_preserved(self) -> None:
        chunks = chunk_text("body text", document_id="doc-1", page=3)
        assert chunks[0].page == 3

    def test_positions_are_sequential_from_zero(self) -> None:
        text = "\n\n".join(para(200, seed=s) for s in "abcde")
        chunks = chunk_text(text, document_id="doc-1")
        assert [c.position for c in chunks] == list(range(len(chunks)))

    def test_blank_text_yields_no_chunks(self) -> None:
        assert chunk_text("", document_id="doc-1") == []
        assert chunk_text("   \n\n  \n", document_id="doc-1") == []


class TestParagraphBoundaries:
    def test_chunks_split_on_paragraph_boundaries(self) -> None:
        # Three ~200-token paragraphs: 600 tokens total, over the 500 max.
        text = "\n\n".join(para(200, s) for s in "abc")
        chunks = chunk_text(text, document_id="doc-1")
        assert len(chunks) >= 2
        # No chunk may contain the end of one paragraph and the start of another
        # unless it came in through overlap.
        assert all(para(200, s) in chunks[0].text or s not in chunks[0].text for s in "abc")

    def test_never_exceeds_max_tokens(self) -> None:
        text = "\n\n".join(para(150, f"s{i}") for i in range(10))
        chunks = chunk_text(text, document_id="doc-1", max_tokens=500)
        assert all(count_tokens(c.text) <= 500 for c in chunks)

    def test_two_paragraphs_that_fit_stay_together(self) -> None:
        text = f"{para(200, 'a')}\n\n{para(200, 'b')}"
        chunks = chunk_text(text, document_id="doc-1")
        assert len(chunks) == 1
        assert "a0" in chunks[0].text and "b0" in chunks[0].text


class TestOversizedParagraphs:
    def test_single_huge_paragraph_is_split(self) -> None:
        # One paragraph, no blank lines, far over the max.
        text = para(3000)
        chunks = chunk_text(text, document_id="doc-1", max_tokens=500)
        assert len(chunks) >= 5
        assert all(count_tokens(c.text) <= 500 for c in chunks)

    def test_huge_paragraph_never_yields_empty_chunks(self) -> None:
        text = para(1200)
        chunks = chunk_text(text, document_id="doc-1", max_tokens=500)
        assert chunks
        assert all(c.text.strip() for c in chunks)


class TestOverlap:
    def test_adjacent_chunks_overlap(self) -> None:
        text = "\n\n".join(para(300, f"s{i}") for i in range(4))
        chunks = chunk_text(text, document_id="doc-1", max_tokens=500, overlap_tokens=50)
        assert len(chunks) >= 2
        # Overlapping region: the head of chunk n+1 re-appears in chunk n.
        for prev, nxt in zip(chunks, chunks[1:], strict=False):
            overlap_words = set(prev.text.split()) & set(nxt.text.split())
            assert overlap_words, "adjacent chunks share no overlap"

    def test_no_overlap_between_nonadjacent_chunks_required(self) -> None:
        # Sanity: chunk count with overlap should still be bounded, not quadratic.
        text = "\n\n".join(para(300, f"s{i}") for i in range(6))
        chunks = chunk_text(text, document_id="doc-1", max_tokens=500)
        assert len(chunks) <= 8


class TestChunkShape:
    def test_ids_are_unique(self) -> None:
        text = "\n\n".join(para(300, f"s{i}") for i in range(6))
        chunks = chunk_text(text, document_id="doc-1")
        assert len({c.id for c in chunks}) == len(chunks)

    def test_chunk_is_a_plain_dataclass(self) -> None:
        c = Chunk(id="x", document_id="d", text="t", position=0, page=None)
        assert c.page is None


@pytest.mark.parametrize("bad_max", [0, -5])
def test_invalid_max_tokens_raises(bad_max: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("hello world", document_id="d", max_tokens=bad_max)
