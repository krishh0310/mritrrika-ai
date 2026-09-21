"""HTTP safeguards that do not require a database."""

from __future__ import annotations

import io
import re
from types import SimpleNamespace

import pytest
from app.main import app
from app.services import storage_service
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile


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


@pytest.mark.asyncio
async def test_upload_reader_stops_at_the_configured_limit(monkeypatch):
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: SimpleNamespace(max_upload_bytes=4),
    )
    upload = UploadFile(file=io.BytesIO(b"12345"), filename="large.pdf")

    with pytest.raises(storage_service.UnsupportedFileType, match="4-byte limit"):
        await storage_service.read_upload(upload)

    assert upload.file.tell() == 5
