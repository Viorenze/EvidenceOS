"""Pytest configuration and test fixtures.

Ensures all tests run offline and deterministically by setting
EMBEDDING_PROVIDER=fake before application modules are imported.
"""

import os
import pytest

# Enforce fake embedding provider for offline deterministic testing
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["DATABASE_URL"] = "postgresql+psycopg://evidence:evidence@localhost:5432/evidenceos"

from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import app


@pytest.fixture
def client():
    """FastAPI TestClient fixture with mocked startup DB init."""
    with patch("apps.api.main.init_db"):
        with TestClient(app) as test_client:
            yield test_client
