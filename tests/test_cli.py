"""Unit tests for the CLI interface."""

from unittest.mock import patch, MagicMock
from apps.api.cli import main
import pytest


def test_cli_search_vector_output(capsys):
    """Verify CLI search command with --mode vector executes and prints formatted results."""
    mock_results = [
        {
            "chunk_id": "c1",
            "document": "PRD.md",
            "heading": "技术选型",
            "content": "后端采用 FastAPI + Pydantic + SQLAlchemy",
            "score": 0.88,
        }
    ]

    with patch("apps.api.cli.SessionLocal"), \
         patch("apps.api.cli.vector_search", return_value=mock_results):
        with patch("sys.argv", ["cli.py", "search", "技术选型", "--mode", "vector", "-k", "3"]):
            main()

    captured = capsys.readouterr()
    assert "0.880000" in captured.out
    assert "PRD.md" in captured.out
    assert "技术选型" in captured.out


def test_cli_search_hybrid_output(capsys):
    """Verify CLI search command with default hybrid mode executes and prints RRF ranks."""
    mock_results = [
        {
            "chunk_id": "c2",
            "document": "PRD.md",
            "heading": "混合检索",
            "content": "RRF 融合向量与全文检索",
            "score": 0.0325,
            "vector_rank": 1,
            "fulltext_rank": 2,
        }
    ]

    with patch("apps.api.cli.SessionLocal"), \
         patch("apps.api.cli.hybrid_search", return_value=mock_results):
        with patch("sys.argv", ["cli.py", "search", "混合检索", "-k", "3"]):
            main()

    captured = capsys.readouterr()
    assert "0.032500" in captured.out
    assert "Ranks: [Vec: 1, FT: 2]" in captured.out
    assert "PRD.md" in captured.out


def test_cli_list_output(capsys):
    """Verify CLI list command prints tabular document list."""
    mock_doc = MagicMock()
    mock_doc.id = "doc-12345"
    mock_doc.status = "ready"
    mock_doc.n_chunks = 12
    mock_doc.filename = "manual.pdf"

    mock_db = MagicMock()
    mock_db.query.return_value.order_by.return_value.all.return_value = [mock_doc]

    with patch("apps.api.cli.SessionLocal", return_value=mock_db):
        with patch("sys.argv", ["cli.py", "list"]):
            main()

    captured = capsys.readouterr()
    assert "doc-12345" in captured.out
    assert "ready" in captured.out
    assert "manual.pdf" in captured.out
