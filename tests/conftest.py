"""Pytest configuration and test fixtures.

Ensures all tests run offline and deterministically by setting
EMBEDDING_PROVIDER=fake before application modules are imported.
"""

import os
import pytest

# Enforce fake embedding & LLM provider for offline deterministic testing
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = "postgresql+psycopg://evidence:evidence@localhost:5432/evidenceos"

from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.db.session import SessionLocal, init_db


@pytest.fixture
def client():
    """FastAPI TestClient fixture with mocked startup DB init."""
    with patch("apps.api.main.init_db"):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def db_session():
    """Provides a database session for tests, cleaned up after test completion."""
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

