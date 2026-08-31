"""Shared fixtures for API tests.

These run against the real seeded database rather than mocks: the properties
under test (RBAC, citizen isolation) are properties of the SQL and the session
wiring, and a mocked session would not exercise them.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

sys.path.insert(0, str(Path(__file__).parent))

from demo_users import DEMO_PASSWORD  # noqa: E402


@pytest.fixture(scope="session")
def client():
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    from app.config.settings import get_settings

    settings = get_settings()
    try:
        psycopg.connect(
            settings.sqlalchemy_url.replace("postgresql+psycopg", "postgresql"),
            connect_timeout=3,
        ).close()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"postgres unavailable ({exc}); run: docker compose up -d")

    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


def _login(client, email: str, password: str = DEMO_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture(scope="session")
def token_for(client):
    """Cache one access token per demo user."""
    cache: dict[str, str] = {}

    def _get(email: str) -> str:
        if email not in cache:
            response = _login(client, email)
            assert response.status_code == 200, (
                f"login failed for {email}: {response.status_code} {response.text}. "
                "Has scripts/seed_demo.py been run?"
            )
            cache[email] = response.json()["access_token"]
        return cache[email]

    return _get


@pytest.fixture
def auth(token_for):
    """Build an Authorization header for a demo user."""

    def _headers(email: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(email)}"}

    return _headers
