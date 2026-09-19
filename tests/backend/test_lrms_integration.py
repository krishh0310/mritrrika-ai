"""Approved records reach the state LRMS / DILRMP (§14).

The properties that matter:

  * Approval queues the record, in the same transaction -- an approved record
    is never silently left out of the state's system.
  * The same content is queued once; delivery is retried until it succeeds,
    and a failure is recorded, never reported as success.
  * The payload is a Record of Rights built from the system of record, and it
    carries enough provenance (document checksum, approval audit hash) for the
    receiving system to verify it independently.
  * Only the tehsildar can push or pull, and only within their jurisdiction.
"""

from __future__ import annotations

import json

import pytest
from demo_users import CITIZEN_A, DEO, TEHSILDAR, VERIFIER
from staged_documents import Field, approve, delete, finish_verification, stage

pytestmark = pytest.mark.integration

FIELDS = [
    Field("VILLAGE", "मुड़ियाकला", 0.95, (300, 100, 500, 130)),
    Field("KHASRA", "142/2", 0.62, (300, 150, 400, 180)),
    Field("AREA", "2.75", 0.91, (300, 200, 380, 230)),
    Field("OWNER", "राम प्रसाद सिंह", 0.93, (90, 400, 330, 430), row=0),
]


@pytest.fixture
def session(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


@pytest.fixture
def approved(session):
    document = stage(session, FIELDS)
    finish_verification(session, document, VERIFIER, corrections={"AREA": "2.5"})
    approve(session, document, TEHSILDAR)
    yield document
    delete(session, document)


def queued(session, document):
    from app.models import LrmsSyncRecord
    from sqlalchemy import select

    return session.execute(
        select(LrmsSyncRecord).where(LrmsSyncRecord.document_id == document.id)
    ).scalars().all()


class TestQueueing:
    def test_approval_queues_the_record(self, session, approved):
        rows = queued(session, approved)
        assert len(rows) == 1
        assert rows[0].status == "PENDING"
        assert rows[0].attempts == 0

    def test_queueing_is_idempotent(self, session, approved):
        from app.services import lrms_service

        first = queued(session, approved)[0]
        again = lrms_service.enqueue(session, approved)
        session.commit()
        assert again.id == first.id
        assert len(queued(session, approved)) == 1

    def test_the_digest_survives_a_database_round_trip(self, session, approved):
        """Re-reading the record must reproduce the queued digest exactly, or
        every backfill would queue an unchanged record a second time."""
        from app.services import lrms_service
        from app.services.certificate_service import hash_of

        session.expire_all()
        assert hash_of(lrms_service.ror_payload(session, approved)) == \
            queued(session, approved)[0].payload_sha256

    def test_an_unapproved_record_is_not_queued(self, session):
        from app.services import lrms_service

        document = stage(session, FIELDS)
        try:
            assert lrms_service.enqueue(session, document) is None
            with pytest.raises(lrms_service.LrmsError):
                lrms_service.ror_payload(session, document)
        finally:
            delete(session, document)


class TestPayload:
    def test_it_is_a_record_of_rights(self, session, approved):
        payload = queued(session, approved)[0].payload

        assert payload["schema"] == "mrittika.ror/1"
        assert payload["record_id"] == approved.external_id
        assert payload["parcel"]["parcel_code"] == "PARCEL-UP-DEMO-0181"
        assert payload["parcel"]["survey_number"]
        assert payload["parcel"]["area"]["square_metres"] > 0
        assert payload["holders"], "current holders come from the ownership records"
        for level in ("state", "district", "tehsil", "village"):
            assert payload["location"][level]["code"].startswith("LOC-")

    def test_it_carries_the_corrected_value_not_the_ai_value(self, session, approved):
        recorded = {
            f["field"]: f for f in queued(session, approved)[0].payload[
                "source_document"]["as_recorded"]
        }
        assert recorded["AREA"]["value"] == "2.5"
        assert recorded["AREA"]["verified_by_human"] is True

    def test_it_carries_verifiable_provenance(self, session, approved):
        from app.models import AuditEvent
        from sqlalchemy import select

        payload = queued(session, approved)[0].payload
        assert payload["source_document"]["sha256"] == approved.checksum_sha256
        approval = session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "document.approved",
                AuditEvent.entity_id == approved.external_id,
            )
        ).scalar_one()
        assert payload["provenance"]["approval_audit_hash"] == approval.event_hash
        assert payload["provenance"]["is_synthetic"] is True


class TestDelivery:
    def test_the_file_adapter_writes_the_record_and_marks_it_delivered(
        self, session, approved, tmp_path
    ):
        from app.integrations.lrms import FileDropAdapter
        from app.services import lrms_service
        from staged_documents import principal

        summary = lrms_service.deliver(
            session, FileDropAdapter(tmp_path), principal(session, TEHSILDAR),
            document_ids=[approved.external_id],
        )
        record = queued(session, approved)[0]
        session.refresh(record)

        assert summary["delivered"] == 1
        assert summary["attempted"] == 1, "a scoped sync must touch nothing else"
        assert record.status == "DELIVERED"
        assert record.delivered_at is not None
        written = tmp_path / record.remote_reference
        assert json.loads(written.read_text()) == record.payload
        # No half-written temporaries are left for a collector to pick up.
        assert not list(tmp_path.glob(".partial-*"))

    def test_a_failed_delivery_is_recorded_not_hidden(self, session, approved):
        from app.integrations.lrms import DisabledAdapter
        from app.services import lrms_service
        from staged_documents import principal

        lrms_service.deliver(session, DisabledAdapter(), principal(session, TEHSILDAR),
                             document_ids=[approved.external_id])
        record = queued(session, approved)[0]
        session.refresh(record)

        assert record.status == "FAILED"
        assert record.attempts == 1
        assert "disabled" in record.last_error

    def test_a_delivered_record_is_not_sent_again(self, session, approved, tmp_path):
        from app.integrations.lrms import FileDropAdapter
        from app.services import lrms_service
        from staged_documents import principal

        tehsildar = principal(session, TEHSILDAR)
        only = [approved.external_id]
        lrms_service.deliver(session, FileDropAdapter(tmp_path), tehsildar, document_ids=only)
        lrms_service.deliver(session, FileDropAdapter(tmp_path), tehsildar, document_ids=only)
        record = queued(session, approved)[0]
        session.refresh(record)
        assert record.attempts == 1

    def test_a_sync_is_audited(self, session, approved, tmp_path):
        from app.integrations.lrms import FileDropAdapter
        from app.models import AuditEvent
        from app.services import lrms_service
        from staged_documents import principal

        before = session.query(AuditEvent).filter(
            AuditEvent.action == lrms_service.LRMS_SYNC).count()
        lrms_service.deliver(session, FileDropAdapter(tmp_path),
                             principal(session, TEHSILDAR),
                             document_ids=[approved.external_id])
        after = session.query(AuditEvent).filter(
            AuditEvent.action == lrms_service.LRMS_SYNC).count()
        assert after == before + 1


class TestAdapters:
    def test_http_adapter_sends_an_idempotency_key(self, monkeypatch):
        import httpx
        from app.integrations.lrms import HttpAdapter

        sent = {}

        def fake_post(url, content, headers, timeout):
            sent.update(url=url, headers=headers, body=json.loads(content))
            return httpx.Response(201, json={"reference": "LRMS-42"},
                                  request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", fake_post)
        receipt = HttpAdapter("https://lrms.example/api/ror", "tok").deliver(
            {"record_id": "DOC-1"}, "abc123"
        )
        assert receipt.remote_reference == "LRMS-42"
        assert sent["headers"]["Idempotency-Key"] == "abc123"
        assert sent["headers"]["Authorization"] == "Bearer tok"

    def test_http_adapter_raises_on_a_rejection(self, monkeypatch):
        import httpx
        from app.integrations.lrms import HttpAdapter, LrmsDeliveryError

        monkeypatch.setattr(httpx, "post", lambda url, **_: httpx.Response(
            503, text="maintenance", request=httpx.Request("POST", url)))
        with pytest.raises(LrmsDeliveryError, match="503"):
            HttpAdapter("https://lrms.example/api/ror", None).deliver({}, "d")

    def test_an_unknown_adapter_fails_loudly(self):
        from types import SimpleNamespace

        from app.integrations.lrms import LrmsDeliveryError, build_adapter

        adapter = build_adapter(SimpleNamespace(lrms_adapter="ftp"))
        with pytest.raises(LrmsDeliveryError, match="unknown LRMS_ADAPTER"):
            adapter.deliver({}, "d")


class TestApi:
    def test_status_reports_counts(self, client, auth, approved):
        body = client.get("/api/v1/integrations/lrms/sync", headers=auth(TEHSILDAR))
        assert body.status_code == 200, body.text
        counts = body.json()["counts"]
        assert set(counts) == {"PENDING", "DELIVERED", "FAILED"}
        assert sum(counts.values()) >= 1

    def test_a_scoped_sync_through_the_api(self, client, auth, approved, monkeypatch,
                                           tmp_path):
        from app.config.settings import get_settings

        monkeypatch.setattr(get_settings(), "lrms_outbox_dir", str(tmp_path))
        response = client.post(
            "/api/v1/integrations/lrms/sync",
            json={"document_ids": [approved.external_id]},
            headers=auth(TEHSILDAR),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["adapter"] == "file"
        assert (body["attempted"], body["delivered"]) == (1, 1)
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_a_record_can_be_pulled(self, client, auth, approved):
        response = client.get(
            f"/api/v1/integrations/lrms/records/{approved.external_id}",
            headers=auth(TEHSILDAR),
        )
        assert response.status_code == 200, response.text
        assert response.json()["payload"]["record_id"] == approved.external_id
        assert len(response.json()["payload_sha256"]) == 64

    def test_an_unapproved_record_cannot_be_pulled(self, client, auth, session):
        document = stage(session, FIELDS)
        try:
            response = client.get(
                f"/api/v1/integrations/lrms/records/{document.external_id}",
                headers=auth(TEHSILDAR),
            )
            assert response.status_code == 409
        finally:
            delete(session, document)

    @pytest.mark.parametrize("email", [CITIZEN_A, DEO, VERIFIER])
    def test_only_the_tehsildar_can_sync(self, client, auth, email):
        assert client.get("/api/v1/integrations/lrms/sync",
                          headers=auth(email)).status_code == 403
        assert client.post("/api/v1/integrations/lrms/sync", json={},
                           headers=auth(email)).status_code == 403
