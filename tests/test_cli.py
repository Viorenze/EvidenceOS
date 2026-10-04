"""Unit tests for the CLI interface."""

from unittest.mock import patch, MagicMock
from apps.api.cli import main
import pytest


def test_cli_search_output(capsys):
    """Verify CLI search command executes and prints formatted results."""
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
        with patch("sys.argv", ["cli.py", "search", "技术选型", "-k", "3"]):
            main()

    captured = capsys.readouterr()
    assert "Score: 0.8800" in captured.out
    assert "PRD.md" in captured.out
    assert "技术选型" in captured.out


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
