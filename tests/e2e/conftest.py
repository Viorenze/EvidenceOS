"""Shared fixtures and utilities for EvidenceOS E2E test suite.

Provides:
- Deterministic offline environment setup (fake embedding & LLM)
- Database session and cleanup lifecycle
- FastAPI TestClient integration
- SSE stream parser conforming to EvidenceOS SSE frame specifications
- High-level test helper methods for document management and chat interactions
"""

import io
import json
import os
from typing import Any, Dict, List, Tuple
import pytest
from fastapi.testclient import TestClient

# Enforce deterministic offline providers and PostgreSQL connection
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ["DATABASE_URL"] = (
    os.environ.get("EVIDENCEOS_DATABASE_URL")
    or "postgresql+psycopg://evidence:evidence@127.0.0.1:5432/evidenceos"
)

from apps.api.main import app
from apps.api.db.session import init_db, SessionLocal
from apps.api.db.models import Document


def parse_sse_events(raw_text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Parse raw SSE stream text into a list of (event_type, json_data) tuples.

    Conforms to standard EvidenceOS SSE frame format:
    event: <event_name>\\ndata: <json_string>\\n\\n
    """
    events = []
    lines = raw_text.strip().split("\n")
    current_event = None

    for line in lines:
        line_clean = line.strip()
        if line_clean.startswith("event:"):
            current_event = line_clean[6:].strip()
        elif line_clean.startswith("data:") and current_event:
            data_str = line_clean[5:].strip()
            try:
                data_obj = json.loads(data_str)
                events.append((current_event, data_obj))
            except json.JSONDecodeError:
                events.append((current_event, {"raw": data_str}))
            current_event = None
    return events


@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    """Ensure database schema and extensions exist prior to running E2E tests."""
    init_db()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient instance with full application lifespan."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def managed_document_ids():
    """Tracks created document IDs during a test and guarantees deletion afterwards."""
    created_ids: List[str] = []
    yield created_ids

    # Teardown: Clean up any created documents from database
    if created_ids:
        with SessionLocal() as db:
            for doc_id in created_ids:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    db.delete(doc)
            db.commit()


def upload_test_doc(
    client: TestClient,
    filename: str,
    content: bytes,
    mime_type: str = "text/markdown",
) -> Tuple[int, Dict[str, Any]]:
    """Upload a test document to POST /api/documents and return status code and response body."""
    files = {"file": (filename, io.BytesIO(content), mime_type)}
    resp = client.post("/api/documents", files=files)
    return resp.status_code, resp.json()
