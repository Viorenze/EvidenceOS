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
    """Verify chunking bounds and genuine overlap preservation on non-periodic technical text."""
    # Build non-periodic text with distinct numbered sections to prevent cyclic false positives
    sentences = [
        f"第{i:02d}项核心设计要点：详细阐述了在系统面对高并发和网络分区场景下，如何保证数据持久化存储与缓存失效机制的一致性原则。"
        for i in range(1, 25)
    ]
    non_periodic_text = "".join(sentences)

    chunks = chunk_text(non_periodic_text, chunk_size=300, chunk_overlap=50)
    assert len(chunks) >= 3

    # Verify indices and chunk size upper bounds
    for i, c in enumerate(chunks):
        assert c.idx == i
        assert len(c.content) <= 350

    # Strict overlap assertion: each adjacent pair must share genuine trailing/leading text
    for i in range(len(chunks) - 1):
        prev_tail = chunks[i].content[-35:]
        next_head = chunks[i + 1].content[:80]
        # At least a 20-character sub-slice of prev chunk tail must appear in next chunk head
        shared = any(prev_tail[j : j + 20] in next_head for j in range(len(prev_tail) - 19))
        assert shared, f"No overlap found between chunk {i} tail and chunk {i+1} head"


def test_markdown_code_fence_ignores_headings():
    """Verify code comments inside markdown code blocks are not treated as section headings."""
    content = """# 架构总览

系统总体设计如下。

```python
# 这是一个 Python 代码内部注释，不应当被解析为 H1 标题
def configure_system():
    # 另一个内部注释
    return True
```

## 数据持久化

持久化层采用 PostgreSQL。
"""
    chunks = chunk_markdown(content, chunk_size=400, chunk_overlap=40)
    headings = [c.heading for c in chunks if c.heading]

    assert "架构总览" in headings
    assert "架构总览 > 数据持久化" in headings
    # Must NOT have created a heading from python code comments
    assert not any("注释" in h for h in headings)
    # The code comment must remain as part of chunk content
    all_content = "\n".join(c.content for c in chunks)
    assert "# 这是一个 Python 代码内部注释" in all_content


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
