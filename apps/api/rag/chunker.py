"""Document chunking and text extraction module.

Why this chunking strategy works (Interview Reference):
1. Markdown Heading Awareness:
   Technical docs rely heavily on hierarchical headings (# H1 > ## H2 > ### H3).
   Carrying heading breadcrumbs preserves semantic context for code snippets and short paragraphs
   that would otherwise become ambiguous when isolated.
2. Sizing (400-500 chars, ~50 overlap):
   - Too small (<150 chars): Loses contextual relationships and cross-sentence explanations.
   - Too large (>1500 chars): Dense vector embedding gets diluted across multiple topics,
     and citation validation becomes too coarse.
   - 400-500 Chinese characters fits roughly 2-3 technical paragraphs, providing both
     precise retrieval relevance and concise verifiable snippets.
3. PDF Text Extraction:
   Extracts text page-by-page, attaching `page` metadata for provenance.
   Scanned PDFs without text layers are rejected with clear error guidance.
"""

from dataclasses import dataclass
import io
import re
from typing import List, Optional
from pypdf import PdfReader


@dataclass
class RawChunk:
    """Represents an extracted chunk prior to database persistence."""

    idx: int
    content: str
    heading: Optional[str] = None
    page: Optional[int] = None


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    heading: Optional[str] = None,
    page: Optional[int] = None,
    start_idx: int = 0,
) -> List[RawChunk]:
    """Slice arbitrary text into overlapping chunks respecting sentence boundaries."""
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [RawChunk(idx=start_idx, content=text, heading=heading, page=page)]

    chunks: List[RawChunk] = []
    current_idx = start_idx
    step = chunk_size - chunk_overlap
    pos = 0

    while pos < len(text):
        end = pos + chunk_size
        if end >= len(text):
            chunk_str = text[pos:].strip()
            if chunk_str:
                chunks.append(RawChunk(idx=current_idx, content=chunk_str, heading=heading, page=page))
                current_idx += 1
            break

        # Try to break at natural Chinese/English punctuation
        slice_candidate = text[pos:end]
        cut_offset = -1
        for punct in ("\n\n", "\n", "。", "！", "？", "；", ". ", "; "):
            last_p = slice_candidate.rfind(punct)
            if last_p > chunk_size // 2:  # Prefer not breaking too early
                cut_offset = last_p + len(punct)
                break

        if cut_offset != -1:
            chunk_str = text[pos : pos + cut_offset].strip()
            pos = pos + cut_offset
        else:
            chunk_str = text[pos:end].strip()
            pos += step

        if chunk_str:
            chunks.append(RawChunk(idx=current_idx, content=chunk_str, heading=heading, page=page))
            current_idx += 1

    return chunks


def chunk_markdown(
    content: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[RawChunk]:
    """Chunk Markdown documents by tracking heading breadcrumbs and section bodies."""
    lines = content.splitlines()
    sections: List[tuple[str, str]] = []  # (heading_breadcrumb, section_text)

    # Active headings stack: [(level, title)]
    heading_stack: List[tuple[int, str]] = []
    current_lines: List[str] = []

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    def current_breadcrumb() -> Optional[str]:
        if not heading_stack:
            return None
        return " > ".join(title for _, title in heading_stack)

    for line in lines:
        match = heading_pattern.match(line)
        if match:
            # Save accumulated lines for previous heading
            if current_lines:
                sec_text = "\n".join(current_lines).strip()
                if sec_text:
                    sections.append((current_breadcrumb() or "", sec_text))
                current_lines = []

            level = len(match.group(1))
            title = match.group(2).strip()

            # Pop headings that are deeper or equal to current level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
        else:
            current_lines.append(line)

    if current_lines:
        sec_text = "\n".join(current_lines).strip()
        if sec_text:
            sections.append((current_breadcrumb() or "", sec_text))

    if not sections and content.strip():
        sections.append(("", content.strip()))

    all_chunks: List[RawChunk] = []
    chunk_idx = 0
    for heading, sec_text in sections:
        sec_chunks = chunk_text(
            text=sec_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            heading=heading if heading else None,
            page=None,
            start_idx=chunk_idx,
        )
        all_chunks.extend(sec_chunks)
        chunk_idx += len(sec_chunks)

    return all_chunks


def chunk_pdf(
    file_bytes: bytes,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[RawChunk]:
    """Extract plain text from PDF pages and split into chunks with page numbers."""
    reader = PdfReader(io.BytesIO(file_bytes))
    all_chunks: List[RawChunk] = []
    chunk_idx = 0

    has_any_text = False
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            has_any_text = True
            page_chunks = chunk_text(
                text=page_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                heading=None,
                page=page_num,
                start_idx=chunk_idx,
            )
            all_chunks.extend(page_chunks)
            chunk_idx += len(page_chunks)

    if not has_any_text:
        raise ValueError("PDF contains no extractable text. Scanned PDFs are not supported.")

    return all_chunks
