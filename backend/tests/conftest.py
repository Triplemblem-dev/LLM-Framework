"""Real-dependency isolation-test fixtures.

These tests hit the real FastAPI app in-process (TestClient), against the
real development PostgreSQL/pgvector database and the real Ollama server,
without mocks. Every domain created by a test is prefixed and suffixed with a
random id and deleted again in teardown (cascades to its
sub-domains, conversations, messages, documents, and chunks - see
Domain's ondelete="CASCADE" foreign keys in app/models.py), so the suite
never touches or leaves behind real domain data.
"""

import warnings

# starlette.testclient currently warns that its httpx-based TestClient is
# deprecated in favor of a package ("httpx2") not available on PyPI at the
# time this suite was written; the class still works correctly. Must be
# set before the import below, which is what triggers the warning.
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {settings.app_access_token}"})
        yield c


@pytest.fixture
def domain_factory(client):
    """Returns a factory: make(name, prompt="", parent_id=None) -> domain dict.

    Only top-level domain ids are tracked for teardown; sub-domains are
    cascade-deleted with their parent.
    """
    created: list[str] = []

    def make(name: str, prompt: str = "", parent_id: str | None = None) -> dict:
        body = {"name": name, "prompt": prompt}
        if parent_id is None:
            resp = client.post("/domains", json=body)
        else:
            resp = client.post(f"/domains/{parent_id}/subdomains", json=body)
        resp.raise_for_status()
        domain = resp.json()
        if parent_id is None:
            created.append(domain["id"])
        return domain

    yield make

    for domain_id in created:
        client.delete(f"/domains/{domain_id}")
