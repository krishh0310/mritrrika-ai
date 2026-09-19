"""DILRMP / LRMS connectors: mock mode, the approval hook, and the log (§14)."""

from __future__ import annotations

import pytest
from demo_users import CENTRAL_OFFICER, CITIZEN_A, DEO, STATE_OFFICER, TEHSILDAR, VERIFIER
from staged_documents import Field, approve, delete, finish_verification, stage

pytestmark = pytest.mark.integration

FIELDS = [Field("VILLAGE", "मुड़ियाकला", 0.95), Field("KHASRA", "181", 0.9)]


@pytest.fixture
def session(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


def logged(session, record_id):
    from app.models import IntegrationLog

    session.expire_all()
    return session.query(IntegrationLog).filter_by(record_id=record_id).all()


def approved_document(session):
    document = stage(session, FIELDS)
    finish_verification(session, document, VERIFIER)
    return approve(session, document, TEHSILDAR)


def test_approval_pushes_the_record_and_logs_it(session):
    document = approved_document(session)
    try:
        [entry] = logged(session, document.external_id)
        assert (entry.connector, entry.status, entry.error) == ("dilrmp", "mock", None)
    finally:
        delete(session, document)


def test_a_failing_push_does_not_fail_the_approval(session, monkeypatch):
    from app.integrations import dilrmp_connector

    def down(record_id):
        raise ConnectionError("DILRMP is down")

    monkeypatch.setattr(dilrmp_connector, "push_record", down)
    document = approved_document(session)
    try:
        assert document.state == "APPROVED"
        [entry] = logged(session, document.external_id)
        assert entry.status == "failed" and "DILRMP is down" in entry.error
    finally:
        delete(session, document)


def test_mock_mode_builds_the_real_payload_and_sends_nothing(session, monkeypatch):
    import httpx
    from app.integrations import dilrmp_connector

    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("mock mode sent"))
    document = approved_document(session)
    try:
        fields = dilrmp_connector.ror_fields(document.external_id)
        assert set(fields) >= {"khata_number", "khasra_number", "owner_name",
                               "area_hectares", "mutation_number", "tehsil_code",
                               "district_code", "state_code"}
        assert fields["state_code"] == "LOC-STATE-UP"
        receipt = dilrmp_connector.push_record(document.external_id)
        assert receipt["status"] == "mock"
        assert receipt["transaction_id"] == f"MOCK-{document.external_id}"
        assert b"<khasra_number>" in dilrmp_connector.to_xml(fields)
    finally:
        delete(session, document)


def test_live_mode_posts_xml_with_the_key(session, monkeypatch):
    import httpx
    from app.config.settings import get_settings
    from app.integrations import dilrmp_connector

    sent = {}

    def fake_post(url, content, headers, timeout):
        sent.update(url=url, content=content, headers=headers)
        return httpx.Response(201, headers={"X-Transaction-Id": "DL-9"},
                              request=httpx.Request("POST", url))

    document = approved_document(session)
    try:
        monkeypatch.setattr(get_settings(), "dilrmp_endpoint", "https://dilrmp.example")
        monkeypatch.setattr(get_settings(), "dilrmp_api_key", "k")
        monkeypatch.setattr(httpx, "post", fake_post)
        receipt = dilrmp_connector.push_record(document.external_id)
        assert (receipt["status"], receipt["transaction_id"]) == ("delivered", "DL-9")
        assert sent["url"] == "https://dilrmp.example/ror"
        assert sent["headers"]["X-API-Key"] == "k"
        assert dilrmp_connector.health_check()["connected"] is True
    finally:
        delete(session, document)


def test_fetch_cadastre_mock_is_marked():
    from app.integrations import dilrmp_connector

    feature = dilrmp_connector.fetch_cadastre("142/2")
    assert feature["properties"]["mock_data"] is True
    assert feature["geometry"]["type"] == "Polygon"


def test_health_reports_unconfigured():
    from app.integrations import dilrmp_connector, lrms_connector

    assert dilrmp_connector.health_check() == {
        "connected": False, "reason": "DILRMP_ENDPOINT not configured"}
    assert lrms_connector.health_check()["connected"] is False


@pytest.mark.parametrize("email", [TEHSILDAR, STATE_OFFICER, CENTRAL_OFFICER])
def test_status_shape(client, auth, email):
    response = client.get("/api/v1/integrations/status", headers=auth(email))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"dilrmp", "lrms", "asyncapi_url"}
    for connector in ("dilrmp", "lrms"):
        assert set(body[connector]) == {"health", "recent"}
        assert len(body[connector]["recent"]) <= 5
    assert client.get(body["asyncapi_url"]).text.startswith("asyncapi: 2.6.0")


@pytest.mark.parametrize("email", [CITIZEN_A, DEO, VERIFIER])
def test_status_is_role_gated(client, auth, email):
    assert client.get("/api/v1/integrations/status", headers=auth(email)).status_code == 403
