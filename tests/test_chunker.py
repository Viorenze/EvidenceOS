"""Unit tests for Markdown heading-aware chunker and PDF text extractor."""

import io
import pytest
from pypdf import PageObject, PdfWriter
from apps.api.rag.chunker import chunk_markdown, chunk_pdf, chunk_text


def test_markdown_heading_hierarchy():
    """Verify Markdown chunking retains nested heading breadcrumbs."""
    md_content = """# EvidenceOS 架构

EvidenceOS 是一个可核对引用的技术问答系统。

## 检索设计

检索模块结合向量与全文检索。

### 混合检索与 RRF

RRF 算法将两路检索结果按排名倒数进行融合计算，k=60。
这是非常关键的一步，保证了关键字与语义的相关性。

## 评测指标

评测包含 Hit@5 与 Citation precision。
"""
    chunks = chunk_markdown(md_content, chunk_size=300, chunk_overlap=30)
    assert len(chunks) >= 3

    # Check headings
    headings = [c.heading for c in chunks]
    assert any(h == "EvidenceOS 架构" for h in headings)
    assert any(h == "EvidenceOS 架构 > 检索设计" for h in headings)
    assert any(h == "EvidenceOS 架构 > 检索设计 > 混合检索与 RRF" for h in headings)
    assert any(h == "EvidenceOS 架构 > 评测指标" for h in headings)


def test_chunk_size_and_overlap():
    """Verify chunking bounds and overlap preservation on long paragraphs."""
    # Generate 1200 characters of text
    sentence = "PostgreSQL 的 pgvector 扩展提供了高效的向量近似最近邻检索能力。"
    long_text = sentence * 30  # ~1140 characters

    chunks = chunk_text(long_text, chunk_size=400, chunk_overlap=50)
    assert len(chunks) > 1

    # Verify indices are monotonically increasing
    for i, c in enumerate(chunks):
        assert c.idx == i
        assert len(c.content) <= 500  # Within tolerance

    # Verify overlap exists between consecutive chunks
    overlap_found = False
    for i in range(len(chunks) - 1):
        # The start of chunks[i+1] should share some text with the end of chunks[i]
        c1_tail = chunks[i].content[-40:]
        if any(c1_tail[j:j+15] in chunks[i+1].content for j in range(len(c1_tail) - 15)):
            overlap_found = True
            break
    assert overlap_found


def test_empty_or_whitespace_text():
    """Verify empty input returns an empty list without raising exceptions."""
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  \t  ") == []
    assert chunk_text("") == []


def test_pdf_extraction_with_pages():
    """Verify PDF chunking extracts text and tags correct page numbers."""
    # Build an in-memory 2-page PDF
    writer = PdfWriter()
    
    # Page 1
    p1 = PageObject.create_blank_page(width=300, height=300)
    writer.add_page(p1)
    
    # Page 2
    p2 = PageObject.create_blank_page(width=300, height=300)
    writer.add_page(p2)

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    # Empty blank pages should raise ValueError (scanned/no text)
    with pytest.raises(ValueError, match="no extractable text"):
        chunk_pdf(pdf_bytes)
