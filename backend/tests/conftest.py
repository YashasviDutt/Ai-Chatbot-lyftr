import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    {
        "LLM_API_KEYS": "fake-key-1,fake-key-2",
        "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
        "ENABLE_FAILURE_SIMULATION": "true",
        "CACHE_TYPE": "local",
        "MOCK_LLM": "true",
        "ALLOWED_ORIGINS": "http://localhost:3000",
    }
)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
