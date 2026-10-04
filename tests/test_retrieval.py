"""Unit tests for dense vector retrieval."""

from unittest.mock import MagicMock
from apps.api.rag.retrieval import vector_search


def test_vector_search_empty_query():
    """Verify empty query returns an empty list without querying the database."""
    mock_db = MagicMock()
    results = vector_search(db=mock_db, query="", k=10)
    assert results == []
    assert not mock_db.execute.called


def test_vector_search_result_formatting():
    """Verify vector search query results are correctly mapped with similarity scores."""
    mock_db = MagicMock()

    # Mock DB row result with distance = 0.15 (similarity score should be 0.85)
    mock_row = MagicMock()
    mock_row.id = "chunk-001"
    mock_row.document_id = "doc-001"
    mock_row.idx = 0
    mock_row.page = None
    mock_row.heading = "架构概览"
    mock_row.content = "EvidenceOS 系统架构介绍"
    mock_row.filename = "architecture.md"
    mock_row.distance = 0.15

    mock_db.execute.return_value.all.return_value = [mock_row]

    results = vector_search(db=mock_db, query="系统架构", k=5)

    assert len(results) == 1
    item = results[0]
    assert item["chunk_id"] == "chunk-001"
    assert item["document_id"] == "doc-001"
    assert item["document"] == "architecture.md"
    assert item["heading"] == "架构概览"
    assert item["content"] == "EvidenceOS 系统架构介绍"
    assert item["score"] == 0.85
