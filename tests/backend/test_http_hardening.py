"""HTTP safeguards that do not require a database."""

from __future__ import annotations

import re

from app.main import app
from fastapi.testclient import TestClient


def test_responses_have_request_id_and_security_headers():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]


def test_safe_upstream_request_id_is_preserved():
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "proxy-123:abc"})

    assert response.headers["x-request-id"] == "proxy-123:abc"


def test_unsafe_upstream_request_id_is_replaced():
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "bad request id"})

    assert response.headers["x-request-id"] != "bad request id"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
