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
