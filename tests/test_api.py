"""Tests for FastAPI HTTP endpoints: health, validation, and error states."""

import io
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Verify GET /api/health returns 200 and ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client: TestClient):
    """Verify GET / returns API welcome info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "health" in data
    assert data["health"] == "/api/health"


def test_upload_unsupported_file_extension(client: TestClient):
    """Verify POST /api/documents rejects unsupported file formats with 400."""
    file_content = b"Binary executable content"
    files = {"file": ("malicious.exe", io.BytesIO(file_content), "application/octet-stream")}

    response = client.post("/api/documents", files=files)
    assert response.status_code == 400
    assert "Unsupported format" in response.json()["detail"]


def test_upload_empty_file(client: TestClient):
    """Verify POST /api/documents rejects empty files with 400."""
    files = {"file": ("empty.md", io.BytesIO(b""), "text/markdown")}

    response = client.post("/api/documents", files=files)
    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]


def test_list_documents(client: TestClient):
    """Verify GET /api/documents returns list of documents."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone
    from apps.api.db.session import get_db
    from apps.api.main import app
    from apps.api.db.models import Document

    mock_db = MagicMock()
    mock_doc = Document(
        id="doc-test-1",
        filename="test.md",
        status="ready",
        n_chunks=3,
        error=None,
        created_at=datetime.now(timezone.utc),
    )
    mock_db.query.return_value.order_by.return_value.all.return_value = [mock_doc]

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/documents")
        assert response.status_code == 200
        docs = response.json()
        assert len(docs) == 1
        assert docs[0]["id"] == "doc-test-1"
        assert docs[0]["filename"] == "test.md"
        assert docs[0]["status"] == "ready"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_delete_document(client: TestClient):
    """Verify DELETE /api/documents/{id} deletes the document."""
    from unittest.mock import MagicMock
    from apps.api.db.session import get_db
    from apps.api.main import app
    from apps.api.db.models import Document

    mock_db = MagicMock()
    mock_doc = Document(id="doc-test-1", filename="test.md")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_doc

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.delete("/api/documents/doc-test-1")
        assert response.status_code == 200
        assert mock_db.delete.called
        assert mock_db.commit.called
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_chunk_by_id(client: TestClient):
    """Verify GET /api/chunks/{id} returns chunk detail."""
    from unittest.mock import MagicMock
    from apps.api.db.session import get_db
    from apps.api.main import app
    from apps.api.db.models import Chunk, Document

    mock_db = MagicMock()
    mock_chunk = Chunk(
        id="chunk-test-1",
        document_id="doc-test-1",
        idx=0,
        page=1,
        heading="介绍",
        content="这是内容片段",
    )
    mock_chunk.document = Document(id="doc-test-1", filename="guide.md")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_chunk

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/chunks/chunk-test-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "chunk-test-1"
        assert data["document"] == "guide.md"
        assert data["content"] == "这是内容片段"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_search_api_endpoint(client: TestClient):
    """Verify POST /api/search returns vector search results."""
    from unittest.mock import patch, MagicMock
    from apps.api.db.session import get_db
    from apps.api.main import app

    mock_db = MagicMock()
    mock_results = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document": "doc.md",
            "idx": 0,
            "page": None,
            "heading": "H1",
            "content": "测试检索结果",
            "score": 0.92,
        }
    ]

    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("apps.api.routers.search.vector_search", return_value=mock_results):
        try:
            response = client.post("/api/search", json={"query": "测试", "mode": "vector", "k": 5})
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "测试"
            assert data["mode"] == "vector"
            assert len(data["results"]) == 1
            assert data["results"][0]["score"] == 0.92
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_search_api_hybrid_endpoint(client: TestClient):
    """Verify POST /api/search with mode=hybrid executes hybrid search."""
    from unittest.mock import patch, MagicMock
    from apps.api.db.session import get_db
    from apps.api.main import app

    mock_db = MagicMock()
    mock_results = [
        {
            "chunk_id": "c2",
            "document_id": "d2",
            "document": "hybrid.md",
            "idx": 1,
            "page": None,
            "heading": "H2",
            "content": "混合检索结果",
            "score": 0.032,
            "vector_rank": 1,
            "fulltext_rank": 2,
        }
    ]

    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("apps.api.routers.search.hybrid_search", return_value=mock_results):
        try:
            response = client.post("/api/search", json={"query": "混合", "mode": "hybrid", "k": 5})
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "混合"
            assert data["mode"] == "hybrid"
            assert len(data["results"]) == 1
            assert data["results"][0]["score"] == 0.032
            assert data["results"][0]["vector_rank"] == 1
            assert data["results"][0]["fulltext_rank"] == 2
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_get_document_detail_by_id(client: TestClient):
    """Verify GET /api/documents/{id} returns document detail with reconstructed content and ordered chunks."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from apps.api.db.models import Chunk, Document
    from apps.api.db.session import get_db
    from apps.api.main import app

    mock_db = MagicMock()
    mock_doc = Document(
        id="doc-detail-1",
        filename="custom_guide.md",
        status="ready",
        n_chunks=2,
        error=None,
        created_at=datetime.now(timezone.utc),
    )
    chunk_0 = Chunk(
        id="c-0",
        document_id="doc-detail-1",
        idx=0,
        page=None,
        heading="架构总览",
        content="第一部分介绍整体架构。",
    )
    chunk_1 = Chunk(
        id="c-1",
        document_id="doc-detail-1",
        idx=1,
        page=None,
        heading="架构总览 > 检索模块",
        content="第二部分介绍混合检索。",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_doc
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        chunk_0,
        chunk_1,
    ]

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/documents/doc-detail-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "doc-detail-1"
        assert data["filename"] == "custom_guide.md"
        assert data["status"] == "ready"
        assert data["n_chunks"] == 2
        assert "# 架构总览" in data["content"]
        assert "## 检索模块" in data["content"]
        assert "第一部分介绍整体架构。" in data["content"]
        assert "第二部分介绍混合检索。" in data["content"]
        assert len(data["chunks"]) == 2
        assert data["chunks"][0]["idx"] == 0
        assert data["chunks"][1]["idx"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_document_detail_not_found(client: TestClient):
    """Verify GET /api/documents/{id} returns 404 when document does not exist."""
    from unittest.mock import MagicMock
    from apps.api.db.session import get_db
    from apps.api.main import app

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/documents/nonexistent-doc-id")
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_reconstruct_document_content_edge_cases():
    """Verify reconstruct_document_content handles empty chunks, overlap deduplication, short-boundary non-collision, cache, and PDF pages."""
    from apps.api.db.models import Chunk
    from apps.api.routers.documents import (
        _RAW_TEXT_CACHE,
        _cache_raw_text,
        _merge_overlapping_text,
        reconstruct_document_content,
    )

    # 1. Empty chunks returns empty string
    assert reconstruct_document_content("empty.md", []) == ""

    # 2. Overlapping chunks within the same heading are deduplicated
    c1 = Chunk(
        id="c1",
        document_id="d1",
        idx=0,
        heading="H1 > Sub",
        content="这是一段用于测试滑动窗口重叠去重的文本内容，重叠部分在末尾。",
    )
    c2 = Chunk(
        id="c2",
        document_id="d1",
        idx=1,
        heading="H1 > Sub",
        content="重叠部分在末尾。紧接着是后续的新增正文内容。",
    )
    reconstructed = reconstruct_document_content("overlap.md", [c1, c2])
    assert "# H1" in reconstructed
    assert "## Sub" in reconstructed
    assert reconstructed.count("重叠部分在末尾。") == 1
    assert "这是一段用于测试滑动窗口重叠去重的文本内容，重叠部分在末尾。紧接着是后续的新增正文内容。" in reconstructed

    # 3. Short 1-5 character boundary collisions between non-overlapping paragraphs are NOT falsely merged
    assert (
        _merge_overlapping_text("See section A", "All endpoints are async")
        == "See section A\n\nAll endpoints are async"
    )
    assert (
        _merge_overlapping_text("支持向量检索", "检索增强生成系统")
        == "支持向量检索\n\n检索增强生成系统"
    )

    # 4. Newly uploaded raw text cache returns lossless content even while chunks are empty (processing)
    _cache_raw_text("doc-processing-1", "### 原始三级标题\n\n完整保留原始 Markdown 格式。")
    try:
        cached_result = reconstruct_document_content(
            "uploaded.md",
            [],
            document_id="doc-processing-1",
        )
        assert cached_result == "### 原始三级标题\n\n完整保留原始 Markdown 格式。"
    finally:
        _RAW_TEXT_CACHE.pop("doc-processing-1", None)

    # 5. Multi-page PDF chunks include page separators
    p1 = Chunk(id="p1", document_id="d2", idx=0, page=1, heading=None, content="第一页内容")
    p2 = Chunk(id="p2", document_id="d2", idx=1, page=2, heading=None, content="第二页内容")
    pdf_reconstructed = reconstruct_document_content("manual.pdf", [p1, p2])
    assert "--- 第 1 页 ---" in pdf_reconstructed
    assert "--- 第 2 页 ---" in pdf_reconstructed
    assert "第一页内容" in pdf_reconstructed
    assert "第二页内容" in pdf_reconstructed


