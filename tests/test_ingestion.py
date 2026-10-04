"""Unit tests for the ingestion pipeline: parsing, jieba segmentation, embedding, and status transitions."""

from unittest.mock import MagicMock
import pytest
from apps.api.db.models import Chunk, Document
from apps.api.rag.ingestion import process_document


def test_process_markdown_document_success():
    """Verify markdown file is chunked, segmented with jieba, embedded, and saved as ready."""
    mock_db = MagicMock()
    doc = Document(id="doc-123", filename="test.md", status="processing", n_chunks=0)
    mock_db.query.return_value.filter.return_value.first.return_value = doc

    md_content = b"""# \xe6\xa0\xb8\xe5\xbf\x83\xe6\x9e\xb6\xe6\x9e\x84

EvidenceOS \xe9\x87\x87\xe7\x94\xa8 LangGraph \xe7\xae\xa1\xe7\x90\x86\xe6\x9c\x89\xe6\x9d\xa1\xe4\xbb\xb6\xe5\xbe\xaa\xe7\x8e\xaf\xe7\x9a\x84 Agent\xe3\x80\x82

## \xe6\xa3\x80\xe7\xb4\xa2\xe8\xae\xbe\xe8\xae\xa1

\xe6\xb7\xb7\xe5\x90\x88\xe6\xa3\x80\xe7\xb4\xa2\xe8\x9e\x8d\xe5\x90\x88\xe4\xba\x86\xe5\x90\x91\xe9\x87\x8f\xe6\xa3\x80\xe7\xb4\xa2\xe4\xb8\x8e PostgreSQL \xe5\x85\xa8\xe6\x96\x87\xe6\xa3\x80\xe7\xb4\xa2\xe3\x80\x82
"""
    processed_doc = process_document(
        db=mock_db,
        document_id="doc-123",
        file_bytes=md_content,
        filename="test.md",
    )

    assert processed_doc.status == "ready"
    assert processed_doc.n_chunks >= 2
    assert processed_doc.error is None
    assert mock_db.commit.called

    # Check added Chunk records
    added_chunks = [call[0][0] for call in mock_db.add.call_args_list if isinstance(call[0][0], Chunk)]
    assert len(added_chunks) == processed_doc.n_chunks

    for chunk in added_chunks:
        assert chunk.document_id == "doc-123"
        assert chunk.content_seg is not None
        # Verify content_seg is space-separated words from jieba
        assert " " in chunk.content_seg
        # Verify embedding exists and is 512 dimensions
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 512


def test_process_unsupported_file_failure():
    """Verify unsupported formats mark the document as failed and record the error."""
    mock_db = MagicMock()
    doc = Document(id="doc-456", filename="test.zip", status="processing", n_chunks=0)
    mock_db.query.return_value.filter.return_value.first.return_value = doc

    with pytest.raises(ValueError, match="Unsupported file format"):
        process_document(
            db=mock_db,
            document_id="doc-456",
            file_bytes=b"PK...",
            filename="test.zip",
        )

    assert doc.status == "failed"
    assert "Unsupported file format" in doc.error
    assert mock_db.rollback.called
    assert mock_db.commit.called
