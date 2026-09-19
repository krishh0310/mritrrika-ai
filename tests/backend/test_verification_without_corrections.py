"""A page the AI read perfectly can be verified and submitted.

Only a correction used to move a document to UNDER_VERIFICATION, and
NEEDS_VERIFICATION -> VERIFIED is not a legal transition. So a verifier who
approved every field unchanged -- or opened a page whose fields were all
auto-accepted -- got a 409 on submit, and the only way through was to "correct"
a field to its own value. Beyond blocking the workflow, it meant only pages
with at least one AI error could ever count as reviewed, biasing the live
accuracy figure against the model.
"""

from __future__ import annotations

import pytest
from demo_users import VERIFIER
from staged_documents import Field, delete, extraction, stage

pytestmark = pytest.mark.integration

BASE = "/api/v1/verifications"


@pytest.fixture
def session(client):
    from app.db import SessionLocal

    with SessionLocal() as s:
        yield s


def test_approving_every_field_unchanged_then_submitting(client, auth, session):
    document = stage(session, [Field("VILLAGE", "रामपुर", 0.7), Field("KHASRA", "12", 0.6)])
    try:
        for field in ("VILLAGE", "KHASRA"):
            response = client.post(
                f"{BASE}/extractions/{extraction(session, document, field).id}/approve",
                headers=auth(VERIFIER),
            )
            assert response.status_code == 200, response.text
        response = client.post(f"{BASE}/{document.external_id}/submit", json={},
                               headers=auth(VERIFIER))
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "PENDING_APPROVAL"
    finally:
        delete(session, document)


def test_a_page_with_every_field_auto_accepted_can_be_submitted(client, auth, session):
    document = stage(session, [Field("VILLAGE", "रामपुर", 0.97, status="AUTO_ACCEPTED")])
    try:
        response = client.post(f"{BASE}/{document.external_id}/submit", json={},
                               headers=auth(VERIFIER))
        assert response.status_code == 200, response.text
        session.refresh(document)
        assert document.state == "PENDING_APPROVAL"
    finally:
        delete(session, document)


def test_the_first_approval_puts_the_task_in_the_verifiers_name(client, auth, session):
    from app.models import VerificationTask
    from sqlalchemy import select

    document = stage(session, [Field("VILLAGE", "रामपुर", 0.7)])
    try:
        client.post(f"{BASE}/extractions/{extraction(session, document, 'VILLAGE').id}"
                    "/approve", headers=auth(VERIFIER))
        session.expire_all()
        task = session.execute(select(VerificationTask).where(
            VerificationTask.document_id == document.id)).scalar_one()
        assert task.status == "IN_PROGRESS"
        assert task.started_at is not None
        assert session.merge(document).state == "UNDER_VERIFICATION"
    finally:
        delete(session, document)


def test_a_field_cannot_be_approved_once_verification_is_over(client, auth, session):
    document = stage(session, [Field("VILLAGE", "रामपुर", 0.97, status="AUTO_ACCEPTED")])
    try:
        client.post(f"{BASE}/{document.external_id}/submit", json={}, headers=auth(VERIFIER))
        response = client.post(
            f"{BASE}/extractions/{extraction(session, document, 'VILLAGE').id}/approve",
            headers=auth(VERIFIER),
        )
        assert response.status_code == 409, response.text
        assert "only accepted during verification" in response.json()["detail"]
    finally:
        delete(session, document)
