"""Unit tests for dense vector retrieval, full-text retrieval, and RRF fusion."""

from unittest.mock import MagicMock, patch
import pytest
from apps.api.rag.retrieval import (
    fulltext_search,
    hybrid_search,
    rrf_fusion,
    vector_search,
)


def test_vector_search_empty_query():
    """Verify empty query returns an empty list without querying the database."""
    mock_db = MagicMock()
    results = vector_search(db=mock_db, query="", k=10)
    assert results == []
    assert not mock_db.execute.called


def test_vector_search_result_formatting():
    """Verify vector search query results are correctly mapped with similarity scores."""
    mock_db = MagicMock()

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


def test_fulltext_search_empty_query():
    """Verify empty query in full-text search returns an empty list."""
    mock_db = MagicMock()
    assert fulltext_search(db=mock_db, query="") == []
    assert fulltext_search(db=mock_db, query="   \t  ") == []
    assert not mock_db.execute.called


def test_fulltext_search_result_formatting():
    """Verify full-text search correctly queries and maps results."""
    mock_db = MagicMock()

    mock_row = MagicMock()
    mock_row.id = "chunk-002"
    mock_row.document_id = "doc-002"
    mock_row.idx = 1
    mock_row.page = 2
    mock_row.heading = "配置项"
    mock_row.content = "EMBEDDING_PROVIDER 控制 embedding 模型"
    mock_row.filename = "config.md"
    mock_row.rank = 0.25

    mock_db.execute.return_value.all.return_value = [mock_row]

    results = fulltext_search(db=mock_db, query="EMBEDDING_PROVIDER 模型", k=10)

    assert len(results) == 1
    item = results[0]
    assert item["chunk_id"] == "chunk-002"
    assert item["score"] == 0.25
    assert item["content"] == "EMBEDDING_PROVIDER 控制 embedding 模型"


def test_rrf_fusion_mechanics():
    """Verify Reciprocal Rank Fusion ranks mutually agreed documents highest."""
    # Chunk A: rank 1 in vector, not in full-text
    # Chunk B: rank 2 in vector, rank 1 in full-text (agreed on both)
    # Chunk C: rank 2 in full-text, not in vector
    vec_results = [
        {"chunk_id": "chunk-A", "content": "A", "document": "docA.md"},
        {"chunk_id": "chunk-B", "content": "B", "document": "docB.md"},
    ]
    ft_results = [
        {"chunk_id": "chunk-B", "content": "B", "document": "docB.md"},
        {"chunk_id": "chunk-C", "content": "C", "document": "docC.md"},
    ]

    # k=60
    # Score A = 1 / (60 + 1) = 1/61 ≈ 0.016393
    # Score B = 1 / (60 + 2) + 1 / (60 + 1) = 1/62 + 1/61 ≈ 0.016129 + 0.016393 = 0.032522
    # Score C = 1 / (60 + 2) = 1/62 ≈ 0.016129
    fused = rrf_fusion(vec_results, ft_results, rrf_k=60, top_k=5)

    assert len(fused) == 3
    # Chunk B should rank #1 because it was retrieved by both systems
    assert fused[0]["chunk_id"] == "chunk-B"
    assert pytest.approx(fused[0]["score"], abs=1e-5) == (1 / 62 + 1 / 61)
    assert fused[0]["vector_rank"] == 2
    assert fused[0]["fulltext_rank"] == 1

    # Chunk A should rank #2
    assert fused[1]["chunk_id"] == "chunk-A"
    assert pytest.approx(fused[1]["score"], abs=1e-5) == (1 / 61)
    assert fused[1]["vector_rank"] == 1
    assert fused[1]["fulltext_rank"] is None

    # Chunk C should rank #3
    assert fused[2]["chunk_id"] == "chunk-C"
    assert pytest.approx(fused[2]["score"], abs=1e-5) == (1 / 62)
    assert fused[2]["vector_rank"] is None
    assert fused[2]["fulltext_rank"] == 2


def test_rrf_fusion_top_k_truncation():
    """Verify RRF respects top_k limit."""
    vec_results = [{"chunk_id": f"chunk-{i}", "content": str(i)} for i in range(10)]
    ft_results = [{"chunk_id": f"chunk-{i+5}", "content": str(i+5)} for i in range(10)]

    fused = rrf_fusion(vec_results, ft_results, rrf_k=60, top_k=5)
    assert len(fused) == 5


def test_hybrid_search_delegation():
    """Verify hybrid_search calls vector and fulltext searches and fuses them."""
    mock_db = MagicMock()

    mock_vec = [{"chunk_id": "v1", "content": "vector match"}]
    mock_ft = [{"chunk_id": "f1", "content": "fulltext match"}]

    with patch("apps.api.rag.retrieval.vector_search", return_value=mock_vec) as p_vec, \
         patch("apps.api.rag.retrieval.fulltext_search", return_value=mock_ft) as p_ft:

        results = hybrid_search(db=mock_db, query="测试混合", vector_k=15, fulltext_k=15, rrf_k=50, top_k=3)

        assert p_vec.called
        assert p_ft.called
        assert len(results) == 2
        chunk_ids = {r["chunk_id"] for r in results}
        assert chunk_ids == {"v1", "f1"}
