"""Text extraction for the index pipeline.

Turns fetched bytes into page-tagged text segments the pipeline can chunk.
Page tags matter: chunks keep the page they came from so a result can point
back to an exact location (docs/build_docs/02-data-model.md).

Phase 1 scope (docs/build_docs/04-core-engine-specs.md section 5.1): text/*
files and text-layer PDFs via PyMuPDF. OCR fallback for scanned PDFs
(Tesseract) is a later addition and deliberately absent here.

Returns `None` for mime types the engine cannot extract — the pipeline
records those as unsupported and moves on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedSegment:
    """One unit of extracted text: a whole file, or one PDF page."""

    page: int | None  # 1-based PDF page number; None for plain text
    text: str


def extract_segments(content: bytes, mime_type: str) -> list[ExtractedSegment] | None:
    """Extract page-tagged text, or None when the mime type is unsupported.

    A text-layer-less PDF yields an empty list (it indexed to nothing) —
    the OCR fallback is a later-phase addition and is not silently attempted.
    """
    if mime_type == "application/pdf":
        return _extract_pdf(content)
    if mime_type.startswith("text/"):
        return [ExtractedSegment(page=None, text=content.decode("utf-8", errors="replace"))]
    return None


def _extract_pdf(content: bytes) -> list[ExtractedSegment]:
    import pymupdf  # imported here: heavy import only when a PDF arrives

    segments: list[ExtractedSegment] = []
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        for number, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if text:
                segments.append(ExtractedSegment(page=number, text=text))
    return segments
