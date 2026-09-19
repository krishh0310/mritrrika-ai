"""Shared fixtures for API tests.

These run against the real seeded database rather than mocks: the properties
under test (RBAC, citizen isolation) are properties of the SQL and the session
wiring, and a mocked session would not exercise them.
"""

import functools
import io
import itertools
import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

sys.path.insert(0, str(Path(__file__).parent))

# API tests drive the pipeline with stub OCR pages. Trained handwriting weights,
# when a developer has them on disk, would re-read those stubs and make results
# depend on the machine (CI has no weights). tests/ai covers the models.
os.environ["HANDWRITING_MODELS_ENABLED"] = "false"

from demo_users import DEMO_PASSWORD  # noqa: E402


@functools.cache
def _why_postgres_is_unreachable() -> str | None:
    """A skip reason, or None when the database is up.

    Cached because every integration test asks the same question and a refused
    connection costs the full timeout each time it is asked.
    """
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    from app.config.settings import get_settings

    try:
        psycopg.connect(
            get_settings().sqlalchemy_url.replace("postgresql+psycopg", "postgresql"),
            connect_timeout=3,
        ).close()
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"postgres unavailable ({exc}); run: docker compose up -d"
    return None


@pytest.fixture(scope="session")
def require_postgres():
    """Skip, rather than fail, when the database this test needs is not up.

    Tests that take `client` are already guarded by it. Tests that open
    `SessionLocal()` themselves -- the GIS publication boundary and the job
    recovery sweep -- were not, so on a machine with no container running they
    reported hard failures while their neighbours correctly reported themselves
    skipped for the identical reason.

    Depend on this from the fixture that opens the session, not from the
    `integration` marker. The marker sits at module scope in both files, but
    most of the tests under it are pure -- hashing, phone normalisation,
    template wording -- and skipping those on a missing database would hide 79
    assertions that need nothing but Python.
    """
    if reason := _why_postgres_is_unreachable():
        pytest.skip(reason)


@pytest.fixture(scope="session")
def client():
    if reason := _why_postgres_is_unreachable():
        pytest.skip(reason)

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


#: Unique per test RUN. See `fresh_scan`.
_RUN_SALT = int.from_bytes(os.urandom(3), "big")
_scan_counter = itertools.count()


def fresh_scan(path) -> bytes:
    """A corpus page as bytes no upload has seen before.

    The demo database is seeded from the same corpus these tests draw their
    sample pages from, so posting a page straight off disk is an exact
    duplicate of a document that is already stored -- which upload now refuses
    (§22). That refusal is the point of the feature; it is not something for a
    lifecycle test to work around silently.

    A small block of noise in one corner changes the bytes without changing
    what the page is or how it reads, so OCR, extraction and the quality gate
    all behave exactly as they did. The salt is drawn once per run, because the
    database persists between runs: a fixed salt would pass the first time and
    refuse every time after.
    """
    from PIL import Image

    image = Image.open(path).convert("RGB")
    arr = np.asarray(image).copy()
    seed = _RUN_SALT + next(_scan_counter)
    arr[:12, :12] = np.random.RandomState(seed).randint(
        0, 255, (12, 12, 3), dtype=np.uint8
    )
    buffer = io.BytesIO()
    Image.fromarray(arr).save(buffer, "JPEG", quality=95)
    return buffer.getvalue()
